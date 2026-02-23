package syfthub

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// SyftAIResource provides low-level access to SyftAI-Space endpoints.
//
// This resource provides direct access to SyftAI-Space endpoints without
// going through the aggregator. Use this when you need:
//   - Custom RAG pipelines with specific retrieval strategies
//   - Direct model queries without data source context
//   - Fine-grained control over the query process
//
// For most use cases, prefer the higher-level client.Chat() API instead.
//
// Example usage:
//
//	// Build a custom RAG pipeline
//	// 1. Query data sources
//	docs, err := client.SyftAI().QueryDataSource(ctx, &QueryDataSourceRequest{
//	    Endpoint:   dataSourceRef,
//	    Query:      "What is Python?",
//	    UserEmail:  "alice@example.com",
//	    TopK:       10,
//	})
//
//	// 2. Build custom prompt
//	var context strings.Builder
//	for _, doc := range docs {
//	    context.WriteString(doc.Content + "\n")
//	}
//	messages := []Message{
//	    {Role: "system", Content: "Context:\n" + context.String()},
//	    {Role: "user", Content: "What is Python?"},
//	}
//
//	// 3. Query model
//	response, err := client.SyftAI().QueryModel(ctx, &QueryModelRequest{
//	    Endpoint:  modelRef,
//	    Messages:  messages,
//	    UserEmail: "alice@example.com",
//	})
//	fmt.Println(response)
type SyftAIResource struct {
	httpClient *httpClient
	client     *http.Client
}

// newSyftAIResource creates a new SyftAIResource.
func newSyftAIResource(httpCli *httpClient) *SyftAIResource {
	return &SyftAIResource{
		httpClient: httpCli,
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

// buildHeaders builds headers for SyftAI-Space request.
func (s *SyftAIResource) buildHeaders(tenantName *string) map[string]string {
	headers := map[string]string{
		"Content-Type": "application/json",
	}
	if tenantName != nil && *tenantName != "" {
		headers["X-Tenant-Name"] = *tenantName
	}
	return headers
}

// QueryDataSourceRequest contains parameters for querying a data source.
type QueryDataSourceRequest struct {
	// Endpoint is the EndpointRef with URL and slug
	Endpoint EndpointRef

	// Query is the search query
	Query string

	// UserEmail is the user email for visibility/policy checks
	UserEmail string

	// TopK is the number of documents to retrieve (default: 5)
	TopK int

	// SimilarityThreshold is the minimum similarity score (default: 0.5)
	SimilarityThreshold float64
}

// QueryDataSource queries a data source endpoint directly.
//
// Sends a query to a SyftAI-Space data source endpoint and returns
// the retrieved documents.
//
// Errors:
//   - RetrievalError: If the query fails
func (s *SyftAIResource) QueryDataSource(ctx context.Context, req *QueryDataSourceRequest) ([]Document, error) {
	// Set defaults
	topK := req.TopK
	if topK == 0 {
		topK = 5
	}
	threshold := req.SimilarityThreshold
	if threshold == 0 {
		threshold = 0.5
	}

	url := fmt.Sprintf("%s/api/v1/endpoints/%s/query", strings.TrimSuffix(req.Endpoint.URL, "/"), req.Endpoint.Slug)

	requestBody := map[string]interface{}{
		"user_email":           req.UserEmail,
		"messages":             req.Query, // SyftAI-Space expects "messages" for query text
		"limit":                topK,
		"similarity_threshold": threshold,
	}

	jsonBody, err := json.Marshal(requestBody)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, newRetrievalError(
			fmt.Sprintf("Failed to create request for data source '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}

	for key, value := range s.buildHeaders(req.Endpoint.TenantName) {
		httpReq.Header.Set(key, value)
	}

	resp, err := s.client.Do(httpReq)
	if err != nil {
		return nil, newRetrievalError(
			fmt.Sprintf("Failed to connect to data source '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, newRetrievalError(
			fmt.Sprintf("Failed to read response from data source '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}

	if resp.StatusCode >= 400 {
		var message string
		var errorData map[string]interface{}
		if err := json.Unmarshal(body, &errorData); err == nil {
			if d, ok := errorData["detail"].(string); ok {
				message = d
			} else if m, ok := errorData["message"].(string); ok {
				message = m
			} else {
				message = string(body)
			}
		} else {
			message = string(body)
			if message == "" {
				message = fmt.Sprintf("HTTP %d", resp.StatusCode)
			}
		}

		return nil, newRetrievalError(
			fmt.Sprintf("Data source query failed: %s", message),
			req.Endpoint.Slug,
			string(body),
		)
	}

	var data struct {
		Documents []struct {
			Content  string                 `json:"content"`
			Score    float64                `json:"score"`
			Metadata map[string]interface{} `json:"metadata"`
		} `json:"documents"`
	}
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, err
	}

	documents := make([]Document, 0, len(data.Documents))
	for _, doc := range data.Documents {
		documents = append(documents, Document{
			Content:  doc.Content,
			Score:    doc.Score,
			Metadata: doc.Metadata,
		})
	}

	return documents, nil
}

// QueryModelRequest contains parameters for querying a model.
type QueryModelRequest struct {
	// Endpoint is the EndpointRef with URL and slug
	Endpoint EndpointRef

	// Messages is the list of chat messages
	Messages []Message

	// UserEmail is the user email for visibility/policy checks
	UserEmail string

	// MaxTokens is the maximum tokens to generate (default: 1024)
	MaxTokens int

	// Temperature is the generation temperature (default: 0.7)
	Temperature float64
}

// QueryModel queries a model endpoint directly.
//
// Sends messages to a SyftAI-Space model endpoint and returns
// the generated response.
//
// Errors:
//   - GenerationError: If generation fails
func (s *SyftAIResource) QueryModel(ctx context.Context, req *QueryModelRequest) (string, error) {
	// Set defaults
	maxTokens := req.MaxTokens
	if maxTokens == 0 {
		maxTokens = 1024
	}
	temperature := req.Temperature
	if temperature == 0 {
		temperature = 0.7
	}

	url := fmt.Sprintf("%s/api/v1/endpoints/%s/query", strings.TrimSuffix(req.Endpoint.URL, "/"), req.Endpoint.Slug)

	messages := make([]map[string]string, len(req.Messages))
	for i, msg := range req.Messages {
		messages[i] = map[string]string{
			"role":    msg.Role,
			"content": msg.Content,
		}
	}

	requestBody := map[string]interface{}{
		"user_email":  req.UserEmail,
		"messages":    messages,
		"max_tokens":  maxTokens,
		"temperature": temperature,
		"stream":      false,
	}

	jsonBody, err := json.Marshal(requestBody)
	if err != nil {
		return "", err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return "", newGenerationError(
			fmt.Sprintf("Failed to create request for model '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}

	for key, value := range s.buildHeaders(req.Endpoint.TenantName) {
		httpReq.Header.Set(key, value)
	}

	resp, err := s.client.Do(httpReq)
	if err != nil {
		return "", newGenerationError(
			fmt.Sprintf("Failed to connect to model '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", newGenerationError(
			fmt.Sprintf("Failed to read response from model '%s': %v", req.Endpoint.Slug, err),
			req.Endpoint.Slug,
			err.Error(),
		)
	}

	if resp.StatusCode >= 400 {
		var message string
		var errorData map[string]interface{}
		if err := json.Unmarshal(body, &errorData); err == nil {
			if d, ok := errorData["detail"].(string); ok {
				message = d
			} else if m, ok := errorData["message"].(string); ok {
				message = m
			} else {
				message = string(body)
			}
		} else {
			message = string(body)
			if message == "" {
				message = fmt.Sprintf("HTTP %d", resp.StatusCode)
			}
		}

		return "", newGenerationError(
			fmt.Sprintf("Model query failed: %s", message),
			req.Endpoint.Slug,
			string(body),
		)
	}

	var data struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	}
	if err := json.Unmarshal(body, &data); err != nil {
		return "", err
	}

	return data.Message.Content, nil
}

// QueryModelStream streams a model response directly.
//
// Sends messages to a SyftAI-Space model endpoint and streams
// the generated response tokens via a channel.
//
// Errors:
//   - GenerationError: If generation fails
func (s *SyftAIResource) QueryModelStream(ctx context.Context, req *QueryModelRequest) (<-chan string, <-chan error) {
	chunks := make(chan string, 100)
	errChan := make(chan error, 1)

	go func() {
		defer close(chunks)
		defer close(errChan)

		// Set defaults
		maxTokens := req.MaxTokens
		if maxTokens == 0 {
			maxTokens = 1024
		}
		temperature := req.Temperature
		if temperature == 0 {
			temperature = 0.7
		}

		url := fmt.Sprintf("%s/api/v1/endpoints/%s/query", strings.TrimSuffix(req.Endpoint.URL, "/"), req.Endpoint.Slug)

		messages := make([]map[string]string, len(req.Messages))
		for i, msg := range req.Messages {
			messages[i] = map[string]string{
				"role":    msg.Role,
				"content": msg.Content,
			}
		}

		requestBody := map[string]interface{}{
			"user_email":  req.UserEmail,
			"messages":    messages,
			"max_tokens":  maxTokens,
			"temperature": temperature,
			"stream":      true,
		}

		jsonBody, err := json.Marshal(requestBody)
		if err != nil {
			errChan <- err
			return
		}

		httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(jsonBody))
		if err != nil {
			errChan <- newGenerationError(
				fmt.Sprintf("Failed to create request for model '%s': %v", req.Endpoint.Slug, err),
				req.Endpoint.Slug,
				err.Error(),
			)
			return
		}

		for key, value := range s.buildHeaders(req.Endpoint.TenantName) {
			httpReq.Header.Set(key, value)
		}
		httpReq.Header.Set("Accept", "text/event-stream")

		// Use a client without timeout for streaming
		streamClient := &http.Client{}
		resp, err := streamClient.Do(httpReq)
		if err != nil {
			errChan <- newGenerationError(
				fmt.Sprintf("Failed to connect to model '%s': %v", req.Endpoint.Slug, err),
				req.Endpoint.Slug,
				err.Error(),
			)
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode >= 400 {
			body, _ := io.ReadAll(resp.Body)
			var message string
			var errorData map[string]interface{}
			if err := json.Unmarshal(body, &errorData); err == nil {
				if d, ok := errorData["detail"].(string); ok {
					message = d
				} else if m, ok := errorData["message"].(string); ok {
					message = m
				} else {
					message = string(body)
				}
			} else {
				message = string(body)
				if message == "" {
					message = fmt.Sprintf("HTTP %d", resp.StatusCode)
				}
			}

			errChan <- newGenerationError(
				fmt.Sprintf("Model stream failed: %s", message),
				req.Endpoint.Slug,
				string(body),
			)
			return
		}

		// Parse SSE stream
		scanner := bufio.NewScanner(resp.Body)
		for scanner.Scan() {
			select {
			case <-ctx.Done():
				errChan <- ctx.Err()
				return
			default:
			}

			line := strings.TrimSpace(scanner.Text())
			if line == "" || strings.HasPrefix(line, "event:") {
				continue
			}

			if strings.HasPrefix(line, "data:") {
				dataStr := strings.TrimSpace(line[5:])
				if dataStr == "[DONE]" {
					return
				}

				var data map[string]interface{}
				if err := json.Unmarshal([]byte(dataStr), &data); err != nil {
					continue // Skip malformed data
				}

				// Extract content from various response formats
				if content, ok := data["content"].(string); ok {
					chunks <- content
				} else if choices, ok := data["choices"].([]interface{}); ok {
					// OpenAI-style response
					for _, choice := range choices {
						if choiceMap, ok := choice.(map[string]interface{}); ok {
							if delta, ok := choiceMap["delta"].(map[string]interface{}); ok {
								if content, ok := delta["content"].(string); ok {
									chunks <- content
								}
							}
						}
					}
				}
			}
		}

		if err := scanner.Err(); err != nil {
			errChan <- err
		}
	}()

	return chunks, errChan
}
