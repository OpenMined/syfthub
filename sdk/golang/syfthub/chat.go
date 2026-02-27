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

const (
	tunnelingPrefix = "tunneling:"
)

// ChatResource provides RAG-augmented chat functionality via the Aggregator.
//
// This resource handles satellite token authentication automatically:
//   - Resolves endpoints and extracts owner information
//   - Exchanges Hub access tokens for satellite tokens (one per unique owner)
//   - Sends tokens to the aggregator for forwarding to SyftAI-Space
//
// Example usage:
//
//	// Simple chat completion
//	response, err := client.Chat().Complete(ctx, &ChatCompleteRequest{
//	    Prompt:      "What are the key features?",
//	    Model:       "alice/gpt-model",
//	    DataSources: []string{"bob/docs-dataset"},
//	})
//	fmt.Println(response.Response)
//
//	// Streaming chat
//	events, errs := client.Chat().Stream(ctx, &ChatCompleteRequest{
//	    Prompt: "Explain machine learning",
//	    Model:  "alice/gpt-model",
//	})
//	for event := range events {
//	    if e, ok := event.(*TokenEvent); ok {
//	        fmt.Print(e.Content)
//	    }
//	}
type ChatResource struct {
	hub           *HubResource
	auth          *AuthResource
	aggregatorURL string
	aggClient     *http.Client
}

// newChatResource creates a new ChatResource.
func newChatResource(hub *HubResource, auth *AuthResource, aggregatorURL string, timeout time.Duration) *ChatResource {
	return &ChatResource{
		hub:           hub,
		auth:          auth,
		aggregatorURL: strings.TrimRight(aggregatorURL, "/"),
		aggClient: &http.Client{
			Timeout: DefaultAggTimeout,
		},
	}
}

// ChatCompleteRequest contains parameters for a chat completion request.
type ChatCompleteRequest struct {
	Prompt              string
	Model               string // Can be path "owner/slug" or EndpointRef
	DataSources         []string
	TopK                int
	MaxTokens           int
	Temperature         float64
	SimilarityThreshold float64
	Messages            []Message
	AggregatorURL       string // Optional custom aggregator URL
}

// Complete sends a chat request and returns the complete response.
func (c *ChatResource) Complete(ctx context.Context, req *ChatCompleteRequest) (*ChatResponse, error) {
	// Set defaults
	if req.TopK == 0 {
		req.TopK = 5
	}
	if req.MaxTokens == 0 {
		req.MaxTokens = 1024
	}
	if req.Temperature == 0 {
		req.Temperature = 0.7
	}
	if req.SimilarityThreshold == 0 {
		req.SimilarityThreshold = 0.5
	}

	// Use custom aggregator URL if provided
	aggregatorURL := c.aggregatorURL
	if req.AggregatorURL != "" {
		aggregatorURL = strings.TrimRight(req.AggregatorURL, "/")
	}

	// Resolve endpoints
	modelRef, err := c.resolveEndpointRef(ctx, req.Model, "model")
	if err != nil {
		return nil, err
	}

	var dsRefs []EndpointRef
	for _, ds := range req.DataSources {
		ref, err := c.resolveEndpointRef(ctx, ds, "data_source")
		if err != nil {
			return nil, err
		}
		dsRefs = append(dsRefs, *ref)
	}

	// Get satellite tokens and transaction tokens for all unique endpoint owners
	uniqueOwners := c.collectUniqueOwners(modelRef, dsRefs)
	endpointTokens, err := c.auth.GetSatelliteTokens(ctx, uniqueOwners)
	if err != nil {
		// Log but don't fail - some tokens may still work
		endpointTokens = make(map[string]string)
	}
	transactionTokens, err := c.auth.GetTransactionTokens(ctx, uniqueOwners)
	if err != nil {
		transactionTokens = &TransactionTokensResponse{Tokens: make(map[string]string)}
	}

	// Auto-fetch peer token if tunneling endpoints detected
	var peerToken, peerChannel string
	tunnelingUsernames := c.collectTunnelingUsernames(modelRef, dsRefs)
	if len(tunnelingUsernames) > 0 {
		peerResponse, err := c.auth.GetPeerToken(ctx, tunnelingUsernames)
		if err == nil {
			peerToken = peerResponse.PeerToken
			peerChannel = peerResponse.PeerChannel
		}
	}

	// Build request body
	requestBody := c.buildRequestBody(
		req.Prompt,
		modelRef,
		dsRefs,
		endpointTokens,
		transactionTokens.Tokens,
		req.TopK,
		req.MaxTokens,
		req.Temperature,
		req.SimilarityThreshold,
		false, // stream
		req.Messages,
		peerToken,
		peerChannel,
	)

	// Make request
	bodyBytes, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", aggregatorURL+"/chat", bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.aggClient.Do(httpReq)
	if err != nil {
		return nil, &AggregatorError{ChatError: newChatError(fmt.Sprintf("Failed to connect to aggregator: %v", err))}
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, c.handleAggregatorError(resp.StatusCode, body)
	}

	var data struct {
		Response      string                    `json:"response"`
		Sources       map[string]DocumentSource `json:"sources"`
		RetrievalInfo []SourceInfo              `json:"retrieval_info"`
		Metadata      ChatMetadata              `json:"metadata"`
		Usage         *TokenUsage               `json:"usage,omitempty"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &ChatResponse{
		Response:      data.Response,
		Sources:       data.Sources,
		RetrievalInfo: data.RetrievalInfo,
		Metadata:      data.Metadata,
		Usage:         data.Usage,
	}, nil
}

// Stream sends a chat request and streams response events via a channel.
//
// Returns two channels: one for events and one for errors.
// The event channel is closed when streaming is complete.
func (c *ChatResource) Stream(ctx context.Context, req *ChatCompleteRequest) (<-chan ChatEvent, <-chan error) {
	events := make(chan ChatEvent, 100)
	errs := make(chan error, 1)

	go func() {
		defer close(events)
		defer close(errs)

		if err := c.streamInternal(ctx, req, events); err != nil {
			errs <- err
		}
	}()

	return events, errs
}

// streamInternal handles the actual streaming logic.
func (c *ChatResource) streamInternal(ctx context.Context, req *ChatCompleteRequest, events chan<- ChatEvent) error {
	// Set defaults
	if req.TopK == 0 {
		req.TopK = 5
	}
	if req.MaxTokens == 0 {
		req.MaxTokens = 1024
	}
	if req.Temperature == 0 {
		req.Temperature = 0.7
	}
	if req.SimilarityThreshold == 0 {
		req.SimilarityThreshold = 0.5
	}

	// Use custom aggregator URL if provided
	aggregatorURL := c.aggregatorURL
	if req.AggregatorURL != "" {
		aggregatorURL = strings.TrimRight(req.AggregatorURL, "/")
	}

	// Resolve endpoints
	modelRef, err := c.resolveEndpointRef(ctx, req.Model, "model")
	if err != nil {
		return err
	}

	var dsRefs []EndpointRef
	for _, ds := range req.DataSources {
		ref, err := c.resolveEndpointRef(ctx, ds, "data_source")
		if err != nil {
			return err
		}
		dsRefs = append(dsRefs, *ref)
	}

	// Get tokens
	uniqueOwners := c.collectUniqueOwners(modelRef, dsRefs)
	endpointTokens, _ := c.auth.GetSatelliteTokens(ctx, uniqueOwners)
	if endpointTokens == nil {
		endpointTokens = make(map[string]string)
	}
	transactionTokens, _ := c.auth.GetTransactionTokens(ctx, uniqueOwners)
	if transactionTokens == nil {
		transactionTokens = &TransactionTokensResponse{Tokens: make(map[string]string)}
	}

	// Auto-fetch peer token if tunneling endpoints detected
	var peerToken, peerChannel string
	tunnelingUsernames := c.collectTunnelingUsernames(modelRef, dsRefs)
	if len(tunnelingUsernames) > 0 {
		peerResponse, err := c.auth.GetPeerToken(ctx, tunnelingUsernames)
		if err == nil {
			peerToken = peerResponse.PeerToken
			peerChannel = peerResponse.PeerChannel
		}
	}

	// Build request body
	requestBody := c.buildRequestBody(
		req.Prompt,
		modelRef,
		dsRefs,
		endpointTokens,
		transactionTokens.Tokens,
		req.TopK,
		req.MaxTokens,
		req.Temperature,
		req.SimilarityThreshold,
		true, // stream
		req.Messages,
		peerToken,
		peerChannel,
	)

	// Make streaming request
	bodyBytes, err := json.Marshal(requestBody)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", aggregatorURL+"/chat/stream", bytes.NewReader(bodyBytes))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := c.aggClient.Do(httpReq)
	if err != nil {
		return &AggregatorError{ChatError: newChatError(fmt.Sprintf("Failed to connect to aggregator: %v", err))}
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return c.handleAggregatorError(resp.StatusCode, body)
	}

	// Parse SSE stream
	scanner := bufio.NewScanner(resp.Body)
	var currentEvent string
	var currentData string

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		if line == "" {
			// Empty line = end of event
			if currentEvent != "" && currentData != "" {
				event := c.parseSSEEvent(currentEvent, currentData)
				select {
				case events <- event:
				case <-ctx.Done():
					return ctx.Err()
				}
			}
			currentEvent = ""
			currentData = ""
			continue
		}

		if strings.HasPrefix(line, "event:") {
			currentEvent = strings.TrimSpace(line[6:])
		} else if strings.HasPrefix(line, "data:") {
			currentData = strings.TrimSpace(line[5:])
		}
	}

	return scanner.Err()
}

// parseSSEEvent parses an SSE event into a typed ChatEvent.
func (c *ChatResource) parseSSEEvent(eventType, dataStr string) ChatEvent {
	var data map[string]interface{}
	if err := json.Unmarshal([]byte(dataStr), &data); err != nil {
		return &ErrorEvent{Error: fmt.Sprintf("Parse error: %v", err)}
	}

	switch eventType {
	case "retrieval_start":
		return &RetrievalStartEvent{}

	case "source_complete":
		return &SourceCompleteEvent{
			Source: SourceInfo{
				Path:               getString(data, "path"),
				Status:             SourceStatus(getString(data, "status")),
				DocumentsRetrieved: getInt(data, "documents"),
			},
		}

	case "retrieval_complete":
		return &RetrievalCompleteEvent{}

	case "reranking_start":
		return &RerankingStartEvent{
			Documents: getInt(data, "documents"),
		}

	case "reranking_complete":
		return &RerankingCompleteEvent{
			Documents: getInt(data, "documents"),
			TimeMs:    getInt(data, "time_ms"),
		}

	case "generation_start":
		return &GenerationStartEvent{
			Model: getString(data, "model"),
		}

	case "generation_heartbeat":
		return &GenerationHeartbeatEvent{
			ElapsedMs: getInt(data, "elapsed_ms"),
		}

	case "token":
		return &TokenEvent{
			Content: getString(data, "content"),
		}

	case "done":
		// Parse sources
		sources := make(map[string]DocumentSource)
		if sourcesData, ok := data["sources"].(map[string]interface{}); ok {
			for title, sourceData := range sourcesData {
				if sd, ok := sourceData.(map[string]interface{}); ok {
					sources[title] = DocumentSource{
						Slug:    getString(sd, "slug"),
						Content: getString(sd, "content"),
					}
				}
			}
		}

		// Parse metadata
		var metadata ChatMetadata
		if m, ok := data["metadata"].(map[string]interface{}); ok {
			metadata = ChatMetadata{
				RetrievalTimeMs:  getInt(m, "retrieval_time_ms"),
				GenerationTimeMs: getInt(m, "generation_time_ms"),
				TotalTimeMs:      getInt(m, "total_time_ms"),
			}
		}

		// Parse usage
		var usage *TokenUsage
		if u, ok := data["usage"].(map[string]interface{}); ok {
			usage = &TokenUsage{
				PromptTokens:     getInt(u, "prompt_tokens"),
				CompletionTokens: getInt(u, "completion_tokens"),
				TotalTokens:      getInt(u, "total_tokens"),
			}
		}

		return &DoneEvent{
			Response: getString(data, "response"),
			Metadata: metadata,
			Sources:  sources,
			Usage:    usage,
		}

	case "error":
		return &ErrorEvent{
			Error: getString(data, "message"),
		}

	default:
		return &ErrorEvent{Error: fmt.Sprintf("Unknown event type: %s", eventType)}
	}
}

// resolveEndpointRef converts an endpoint path to EndpointRef.
func (c *ChatResource) resolveEndpointRef(ctx context.Context, endpoint string, expectedType string) (*EndpointRef, error) {
	// Fetch from hub
	ep, err := c.hub.Get(ctx, endpoint)
	if err != nil {
		return nil, newEndpointResolutionError(endpoint)
	}

	// Validate type
	if expectedType != "" && !typeMatches(string(ep.Type), expectedType) {
		return nil, fmt.Errorf("expected endpoint type '%s', got '%s' for '%s'", expectedType, ep.Type, endpoint)
	}

	// Find first enabled connection with URL
	for _, conn := range ep.Connect {
		if conn.Enabled {
			if urlVal, ok := conn.Config["url"].(string); ok && urlVal != "" {
				var tenantName *string
				if tn, ok := conn.Config["tenant_name"].(string); ok {
					tenantName = &tn
				}
				return &EndpointRef{
					URL:           urlVal,
					Slug:          ep.Slug,
					Name:          ep.Name,
					TenantName:    tenantName,
					OwnerUsername: &ep.OwnerUsername,
				}, nil
			}
		}
	}

	return nil, &EndpointResolutionError{
		ChatError: newChatError(fmt.Sprintf("Endpoint '%s' has no connection with URL configured", endpoint)),
		Path:      endpoint,
	}
}

// typeMatches checks if an endpoint type matches the expected type.
func typeMatches(actualType, expectedType string) bool {
	if actualType == expectedType {
		return true
	}
	if actualType == string(EndpointTypeModelDataSource) {
		return expectedType == string(EndpointTypeModel) || expectedType == string(EndpointTypeDataSource)
	}
	return false
}

// collectUniqueOwners collects unique owner usernames from all endpoints.
func (c *ChatResource) collectUniqueOwners(modelRef *EndpointRef, dsRefs []EndpointRef) []string {
	seen := make(map[string]bool)
	var owners []string

	if modelRef.OwnerUsername != nil {
		if !seen[*modelRef.OwnerUsername] {
			seen[*modelRef.OwnerUsername] = true
			owners = append(owners, *modelRef.OwnerUsername)
		}
	}

	for _, ds := range dsRefs {
		if ds.OwnerUsername != nil {
			if !seen[*ds.OwnerUsername] {
				seen[*ds.OwnerUsername] = true
				owners = append(owners, *ds.OwnerUsername)
			}
		}
	}

	return owners
}

// collectTunnelingUsernames extracts usernames from tunneling URLs.
func (c *ChatResource) collectTunnelingUsernames(modelRef *EndpointRef, dsRefs []EndpointRef) []string {
	seen := make(map[string]bool)
	var usernames []string

	if strings.HasPrefix(modelRef.URL, tunnelingPrefix) {
		username := modelRef.URL[len(tunnelingPrefix):]
		if !seen[username] {
			seen[username] = true
			usernames = append(usernames, username)
		}
	}

	for _, ds := range dsRefs {
		if strings.HasPrefix(ds.URL, tunnelingPrefix) {
			username := ds.URL[len(tunnelingPrefix):]
			if !seen[username] {
				seen[username] = true
				usernames = append(usernames, username)
			}
		}
	}

	return usernames
}

// buildRequestBody builds the request body for the aggregator.
func (c *ChatResource) buildRequestBody(
	prompt string,
	modelRef *EndpointRef,
	dsRefs []EndpointRef,
	endpointTokens map[string]string,
	transactionTokens map[string]string,
	topK int,
	maxTokens int,
	temperature float64,
	similarityThreshold float64,
	stream bool,
	messages []Message,
	peerToken string,
	peerChannel string,
) map[string]interface{} {
	body := map[string]interface{}{
		"prompt": prompt,
		"model": map[string]interface{}{
			"url":            modelRef.URL,
			"slug":           modelRef.Slug,
			"name":           modelRef.Name,
			"tenant_name":    modelRef.TenantName,
			"owner_username": modelRef.OwnerUsername,
		},
		"data_sources":         make([]map[string]interface{}, 0, len(dsRefs)),
		"endpoint_tokens":      endpointTokens,
		"transaction_tokens":   transactionTokens,
		"top_k":                topK,
		"max_tokens":           maxTokens,
		"temperature":          temperature,
		"similarity_threshold": similarityThreshold,
		"stream":               stream,
	}

	for _, ds := range dsRefs {
		body["data_sources"] = append(body["data_sources"].([]map[string]interface{}), map[string]interface{}{
			"url":            ds.URL,
			"slug":           ds.Slug,
			"name":           ds.Name,
			"tenant_name":    ds.TenantName,
			"owner_username": ds.OwnerUsername,
		})
	}

	if len(messages) > 0 {
		body["messages"] = messages
	}

	if peerToken != "" {
		body["peer_token"] = peerToken
	}
	if peerChannel != "" {
		body["peer_channel"] = peerChannel
	}

	return body
}

// handleAggregatorError converts aggregator errors to SDK errors.
func (c *ChatResource) handleAggregatorError(statusCode int, body []byte) error {
	var data map[string]interface{}
	message := string(body)
	if err := json.Unmarshal(body, &data); err == nil {
		if msg, ok := data["message"].(string); ok {
			message = msg
		} else if msg, ok := data["error"].(string); ok {
			message = msg
		}
	}

	return &AggregatorError{
		ChatError: &ChatError{
			SyftHubError: newSyftHubError(statusCode, fmt.Sprintf("Aggregator error: %s", message)),
		},
	}
}

// GetAvailableModels returns model endpoints that have connection URLs configured.
func (c *ChatResource) GetAvailableModels(ctx context.Context, limit int) ([]*EndpointPublic, error) {
	if limit == 0 {
		limit = 20
	}

	var results []*EndpointPublic
	iter := c.hub.Browse(ctx)
	for iter.Next(ctx) {
		if len(results) >= limit {
			break
		}

		ep := iter.Value()
		if ep.Type != EndpointTypeModel {
			continue
		}

		// Check if has enabled connection with URL
		hasURL := false
		for _, conn := range ep.Connect {
			if conn.Enabled {
				if url, ok := conn.Config["url"].(string); ok && url != "" {
					hasURL = true
					break
				}
			}
		}

		if hasURL {
			epCopy := ep
			results = append(results, &epCopy)
		}
	}

	if err := iter.Err(); err != nil {
		return nil, err
	}

	return results, nil
}

// GetAvailableDataSources returns data source endpoints that have connection URLs configured.
func (c *ChatResource) GetAvailableDataSources(ctx context.Context, limit int) ([]*EndpointPublic, error) {
	if limit == 0 {
		limit = 20
	}

	var results []*EndpointPublic
	iter := c.hub.Browse(ctx)
	for iter.Next(ctx) {
		if len(results) >= limit {
			break
		}

		ep := iter.Value()
		if ep.Type != EndpointTypeDataSource {
			continue
		}

		// Check if has enabled connection with URL
		hasURL := false
		for _, conn := range ep.Connect {
			if conn.Enabled {
				if url, ok := conn.Config["url"].(string); ok && url != "" {
					hasURL = true
					break
				}
			}
		}

		if hasURL {
			epCopy := ep
			results = append(results, &epCopy)
		}
	}

	if err := iter.Err(); err != nil {
		return nil, err
	}

	return results, nil
}

// Helper functions for extracting values from map[string]interface{}
func getString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func getInt(m map[string]interface{}, key string) int {
	if v, ok := m[key].(float64); ok {
		return int(v)
	}
	if v, ok := m[key].(int); ok {
		return v
	}
	return 0
}
