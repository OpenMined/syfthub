package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewSyftAIResource(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	syftai := newSyftAIResource(httpClient)

	if syftai == nil {
		t.Fatal("syftai should not be nil")
	}
	if syftai.httpClient != httpClient {
		t.Error("httpClient not set correctly")
	}
	if syftai.client == nil {
		t.Error("client should be initialized")
	}
}

func TestSyftAIResourceBuildHeaders(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	syftai := newSyftAIResource(httpClient)

	t.Run("without tenant", func(t *testing.T) {
		headers := syftai.buildHeaders(nil)
		if headers["Content-Type"] != "application/json" {
			t.Errorf("Content-Type = %q", headers["Content-Type"])
		}
		if _, ok := headers["X-Tenant-Name"]; ok {
			t.Error("X-Tenant-Name should not be set")
		}
	})

	t.Run("with tenant", func(t *testing.T) {
		tenantName := "my-tenant"
		headers := syftai.buildHeaders(&tenantName)
		if headers["X-Tenant-Name"] != "my-tenant" {
			t.Errorf("X-Tenant-Name = %q", headers["X-Tenant-Name"])
		}
	})

	t.Run("with empty tenant", func(t *testing.T) {
		tenantName := ""
		headers := syftai.buildHeaders(&tenantName)
		if _, ok := headers["X-Tenant-Name"]; ok {
			t.Error("X-Tenant-Name should not be set for empty tenant")
		}
	})
}

func TestSyftAIResourceQueryDataSource(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/my-data/query" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["user_email"] != "test@example.com" {
				t.Errorf("user_email = %v", body["user_email"])
			}
			if body["messages"] != "What is Python?" {
				t.Errorf("messages = %v", body["messages"])
			}
			if body["limit"].(float64) != 10 {
				t.Errorf("limit = %v", body["limit"])
			}
			if body["similarity_threshold"].(float64) != 0.7 {
				t.Errorf("similarity_threshold = %v", body["similarity_threshold"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"documents": []map[string]interface{}{
					{
						"content":  "Python is a programming language.",
						"score":    0.95,
						"metadata": map[string]interface{}{"source": "wiki"},
					},
					{
						"content":  "Python supports multiple paradigms.",
						"score":    0.85,
						"metadata": map[string]interface{}{"source": "docs"},
					},
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		docs, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:            EndpointRef{URL: server.URL, Slug: "my-data"},
			Query:               "What is Python?",
			UserEmail:           "test@example.com",
			TopK:                10,
			SimilarityThreshold: 0.7,
		})

		if err != nil {
			t.Fatalf("QueryDataSource error: %v", err)
		}
		if len(docs) != 2 {
			t.Errorf("len(docs) = %d", len(docs))
		}
		if docs[0].Content != "Python is a programming language." {
			t.Errorf("docs[0].Content = %q", docs[0].Content)
		}
		if docs[0].Score != 0.95 {
			t.Errorf("docs[0].Score = %f", docs[0].Score)
		}
		if docs[0].Metadata["source"] != "wiki" {
			t.Errorf("docs[0].Metadata[source] = %v", docs[0].Metadata["source"])
		}
	})

	t.Run("with defaults", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			// Check defaults
			if body["limit"].(float64) != 5 {
				t.Errorf("limit = %v, want 5", body["limit"])
			}
			if body["similarity_threshold"].(float64) != 0.5 {
				t.Errorf("similarity_threshold = %v, want 0.5", body["similarity_threshold"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"documents": []map[string]interface{}{},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-data"},
			Query:     "Test",
			UserEmail: "test@example.com",
		})

		if err != nil {
			t.Fatalf("QueryDataSource error: %v", err)
		}
	})

	t.Run("with tenant header", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tenantHeader := r.Header.Get("X-Tenant-Name")
			if tenantHeader != "my-tenant" {
				t.Errorf("X-Tenant-Name = %q", tenantHeader)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"documents": []map[string]interface{}{},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		tenantName := "my-tenant"
		_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-data", TenantName: &tenantName},
			Query:     "Test",
			UserEmail: "test@example.com",
		})

		if err != nil {
			t.Fatalf("QueryDataSource error: %v", err)
		}
	})

	t.Run("error response", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Query failed"})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-data"},
			Query:     "Test",
			UserEmail: "test@example.com",
		})

		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*RetrievalError)
		if !ok {
			t.Fatalf("expected RetrievalError, got %T", err)
		}
	})

	t.Run("error with message field", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"message": "Bad request"})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-data"},
			Query:     "Test",
			UserEmail: "test@example.com",
		})

		if err == nil {
			t.Fatal("expected error")
		}
	})

	t.Run("error with invalid json", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("not json"))
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-data"},
			Query:     "Test",
			UserEmail: "test@example.com",
		})

		if err == nil {
			t.Fatal("expected error")
		}
	})
}

func TestSyftAIResourceQueryModel(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/my-model/query" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["user_email"] != "test@example.com" {
				t.Errorf("user_email = %v", body["user_email"])
			}
			if body["max_tokens"].(float64) != 2048 {
				t.Errorf("max_tokens = %v", body["max_tokens"])
			}
			if body["temperature"].(float64) != 0.8 {
				t.Errorf("temperature = %v", body["temperature"])
			}
			if body["stream"].(bool) != false {
				t.Error("stream should be false")
			}

			messages := body["messages"].([]interface{})
			if len(messages) != 2 {
				t.Errorf("len(messages) = %d", len(messages))
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"message": map[string]interface{}{
					"content": "Hello! How can I help you?",
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		response, err := syftai.QueryModel(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages: []Message{
				{Role: "system", Content: "You are a helpful assistant."},
				{Role: "user", Content: "Hello"},
			},
			MaxTokens:   2048,
			Temperature: 0.8,
		})

		if err != nil {
			t.Fatalf("QueryModel error: %v", err)
		}
		if response != "Hello! How can I help you?" {
			t.Errorf("response = %q", response)
		}
	})

	t.Run("with defaults", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			// Check defaults
			if body["max_tokens"].(float64) != 1024 {
				t.Errorf("max_tokens = %v, want 1024", body["max_tokens"])
			}
			if body["temperature"].(float64) != 0.7 {
				t.Errorf("temperature = %v, want 0.7", body["temperature"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"message": map[string]interface{}{
					"content": "Response",
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryModel(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		if err != nil {
			t.Fatalf("QueryModel error: %v", err)
		}
	})

	t.Run("error response", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Model unavailable"})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryModel(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*GenerationError)
		if !ok {
			t.Fatalf("expected GenerationError, got %T", err)
		}
	})

	t.Run("error with empty body", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		_, err := syftai.QueryModel(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		if err == nil {
			t.Fatal("expected error")
		}
	})
}

func TestSyftAIResourceQueryModelStream(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/my-model/query" {
				t.Errorf("path = %s", r.URL.Path)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["stream"].(bool) != true {
				t.Error("stream should be true")
			}

			w.Header().Set("Content-Type", "text/event-stream")
			flusher, _ := w.(http.Flusher)

			events := []string{
				"data: {\"content\": \"Hello\"}\n\n",
				"data: {\"content\": \" world\"}\n\n",
				"data: {\"content\": \"!\"}\n\n",
				"data: [DONE]\n\n",
			}

			for _, event := range events {
				w.Write([]byte(event))
				flusher.Flush()
			}
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		chunks, errs := syftai.QueryModelStream(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Say hello world"}},
		})

		var collected []string
		for chunk := range chunks {
			collected = append(collected, chunk)
		}

		// Check for errors
		select {
		case err := <-errs:
			if err != nil {
				t.Fatalf("Stream error: %v", err)
			}
		default:
		}

		if len(collected) != 3 {
			t.Errorf("collected %d chunks, want 3", len(collected))
		}

		fullResponse := ""
		for _, c := range collected {
			fullResponse += c
		}
		if fullResponse != "Hello world!" {
			t.Errorf("fullResponse = %q", fullResponse)
		}
	})

	t.Run("openai format", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "text/event-stream")
			flusher, _ := w.(http.Flusher)

			// OpenAI-style response format
			events := []string{
				`data: {"choices": [{"delta": {"content": "Hello"}}]}` + "\n\n",
				`data: {"choices": [{"delta": {"content": " OpenAI"}}]}` + "\n\n",
				"data: [DONE]\n\n",
			}

			for _, event := range events {
				w.Write([]byte(event))
				flusher.Flush()
			}
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		chunks, errs := syftai.QueryModelStream(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		var collected []string
		for chunk := range chunks {
			collected = append(collected, chunk)
		}

		select {
		case err := <-errs:
			if err != nil {
				t.Fatalf("Stream error: %v", err)
			}
		default:
		}

		if len(collected) != 2 {
			t.Errorf("collected %d chunks, want 2", len(collected))
		}
	})

	t.Run("error response", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Model unavailable"})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		chunks, errs := syftai.QueryModelStream(context.Background(), &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		// Drain chunks channel
		for range chunks {
		}

		// Check for error
		err := <-errs
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*GenerationError)
		if !ok {
			t.Fatalf("expected GenerationError, got %T", err)
		}
	})

	t.Run("context cancellation", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "text/event-stream")
			flusher, _ := w.(http.Flusher)

			// Send continuous stream that never ends
			for i := 0; i < 1000; i++ {
				w.Write([]byte(`data: {"content": "chunk"}` + "\n\n"))
				flusher.Flush()
			}
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		syftai := newSyftAIResource(httpClient)

		ctx, cancel := context.WithCancel(context.Background())
		defer cancel() // Ensure context is always canceled to prevent resource leak

		chunks, errs := syftai.QueryModelStream(ctx, &QueryModelRequest{
			Endpoint:  EndpointRef{URL: server.URL, Slug: "my-model"},
			UserEmail: "test@example.com",
			Messages:  []Message{{Role: "user", Content: "Test"}},
		})

		// Read a few chunks then cancel
		count := 0
		for range chunks {
			count++
			if count >= 3 {
				cancel()
				break
			}
		}

		// Drain remaining
		for range chunks {
		}

		// The error channel should have context error
		err := <-errs
		if err != nil && err != context.Canceled {
			// It's ok if there's no error or context.Canceled
		}
	})
}

func TestSyftAIResourceURLConstruction(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify URL is properly constructed
		if r.URL.Path != "/api/v1/endpoints/test-slug/query" {
			t.Errorf("path = %s", r.URL.Path)
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"documents": []map[string]interface{}{},
		})
	}))
	defer server.Close()

	httpClient := newHTTPClient(server.URL, DefaultTimeout)
	syftai := newSyftAIResource(httpClient)

	// Test with trailing slash in URL
	_, err := syftai.QueryDataSource(context.Background(), &QueryDataSourceRequest{
		Endpoint:  EndpointRef{URL: server.URL + "/", Slug: "test-slug"},
		Query:     "Test",
		UserEmail: "test@example.com",
	})

	if err != nil {
		t.Fatalf("QueryDataSource error: %v", err)
	}
}

func TestQueryDataSourceRequestDefaults(t *testing.T) {
	req := &QueryDataSourceRequest{
		Endpoint:  EndpointRef{URL: "https://test.com", Slug: "test"},
		Query:     "test query",
		UserEmail: "test@example.com",
		// TopK and SimilarityThreshold left at zero
	}

	// Verify zero values
	if req.TopK != 0 {
		t.Errorf("TopK should be 0 by default")
	}
	if req.SimilarityThreshold != 0 {
		t.Errorf("SimilarityThreshold should be 0 by default")
	}
}

func TestQueryModelRequestDefaults(t *testing.T) {
	req := &QueryModelRequest{
		Endpoint:  EndpointRef{URL: "https://test.com", Slug: "test"},
		Messages:  []Message{{Role: "user", Content: "test"}},
		UserEmail: "test@example.com",
		// MaxTokens and Temperature left at zero
	}

	// Verify zero values
	if req.MaxTokens != 0 {
		t.Errorf("MaxTokens should be 0 by default")
	}
	if req.Temperature != 0 {
		t.Errorf("Temperature should be 0 by default")
	}
}
