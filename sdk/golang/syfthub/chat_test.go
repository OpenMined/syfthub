package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestNewChatResource(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, "https://aggregator.example.com/", 30*time.Second)

	if chat == nil {
		t.Fatal("chat should not be nil")
	}
	if chat.aggregatorURL != "https://aggregator.example.com" {
		t.Errorf("aggregatorURL = %q, trailing slash should be trimmed", chat.aggregatorURL)
	}
	if chat.hub != hub {
		t.Error("hub not set correctly")
	}
	if chat.auth != auth {
		t.Error("auth not set correctly")
	}
	if chat.aggClient == nil {
		t.Error("aggClient should be initialized")
	}
}

func TestChatResourceComplete(t *testing.T) {
	// Setup hub server for endpoint resolution (Browse endpoint returns list)
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints/public" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "My Model",
					"slug":           "my-model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{
							"type":    "syftai_space",
							"enabled": true,
							"config":  map[string]interface{}{"url": "https://syftai.example.com"},
						},
					},
				},
				{
					"id":             2,
					"name":           "My Data",
					"slug":           "my-data",
					"type":           "data_source",
					"owner_username": "bob",
					"connect": []map[string]interface{}{
						{
							"type":    "syftai_space",
							"enabled": true,
							"config":  map[string]interface{}{"url": "https://syftai.example.com"},
						},
					},
				},
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/satellite-tokens" {
			json.NewEncoder(w).Encode(map[string]string{
				"alice": "sat_token_alice",
				"bob":   "sat_token_bob",
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/transaction-tokens" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": map[string]string{
					"alice": "tx_token_alice",
					"bob":   "tx_token_bob",
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hubServer.Close()

	// Setup aggregator server
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		// Verify request body structure
		if body["prompt"] != "What is Python?" {
			t.Errorf("prompt = %v", body["prompt"])
		}
		if body["stream"].(bool) != false {
			t.Error("stream should be false for Complete")
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"response": "Python is a programming language.",
			"sources": map[string]interface{}{
				"Doc 1": map[string]interface{}{
					"slug":    "doc1",
					"content": "Python content",
				},
			},
			"retrieval_info": []map[string]interface{}{
				{"path": "bob/my-data", "status": "success", "documents_retrieved": 3},
			},
			"metadata": map[string]interface{}{
				"retrieval_time_ms":  100,
				"generation_time_ms": 500,
				"total_time_ms":      600,
			},
			"usage": map[string]interface{}{
				"prompt_tokens":     50,
				"completion_tokens": 100,
				"total_tokens":      150,
			},
		})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, aggServer.URL, 30*time.Second)

	resp, err := chat.Complete(context.Background(), &ChatCompleteRequest{
		Prompt:      "What is Python?",
		Model:       "alice/my-model",
		DataSources: []string{"bob/my-data"},
	})

	if err != nil {
		t.Fatalf("Complete error: %v", err)
	}
	if resp.Response != "Python is a programming language." {
		t.Errorf("Response = %q", resp.Response)
	}
	if len(resp.Sources) != 1 {
		t.Errorf("Sources length = %d", len(resp.Sources))
	}
	if resp.Metadata.TotalTimeMs != 600 {
		t.Errorf("TotalTimeMs = %d", resp.Metadata.TotalTimeMs)
	}
	if resp.Usage == nil {
		t.Error("Usage should not be nil")
	} else if resp.Usage.TotalTokens != 150 {
		t.Errorf("TotalTokens = %d", resp.Usage.TotalTokens)
	}
}

func TestChatResourceCompleteWithCustomAggregator(t *testing.T) {
	// Setup hub server
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints/public" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Model",
					"slug":           "model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/satellite-tokens" {
			json.NewEncoder(w).Encode(map[string]string{})
			return
		}
		if r.URL.Path == "/api/v1/auth/transaction-tokens" {
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{}})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hubServer.Close()

	// Setup custom aggregator server
	customAggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"response": "Custom aggregator response",
		})
	}))
	defer customAggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, "https://default-aggregator.example.com", 30*time.Second)

	resp, err := chat.Complete(context.Background(), &ChatCompleteRequest{
		Prompt:        "Test",
		Model:         "alice/model",
		AggregatorURL: customAggServer.URL,
	})

	if err != nil {
		t.Fatalf("Complete error: %v", err)
	}
	if resp.Response != "Custom aggregator response" {
		t.Errorf("Response = %q", resp.Response)
	}
}

func TestChatResourceCompleteDefaults(t *testing.T) {
	// Setup hub server
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints/public" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Model",
					"slug":           "model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/satellite-tokens" {
			json.NewEncoder(w).Encode(map[string]string{})
			return
		}
		if r.URL.Path == "/api/v1/auth/transaction-tokens" {
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{}})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hubServer.Close()

	// Setup aggregator to verify defaults
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		// Check defaults
		if body["top_k"].(float64) != 5 {
			t.Errorf("top_k = %v, want 5", body["top_k"])
		}
		if body["max_tokens"].(float64) != 1024 {
			t.Errorf("max_tokens = %v, want 1024", body["max_tokens"])
		}
		if body["temperature"].(float64) != 0.7 {
			t.Errorf("temperature = %v, want 0.7", body["temperature"])
		}
		if body["similarity_threshold"].(float64) != 0.5 {
			t.Errorf("similarity_threshold = %v, want 0.5", body["similarity_threshold"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{"response": "ok"})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, aggServer.URL, 30*time.Second)

	_, err := chat.Complete(context.Background(), &ChatCompleteRequest{
		Prompt: "Test",
		Model:  "alice/model",
	})

	if err != nil {
		t.Fatalf("Complete error: %v", err)
	}
}

func TestChatResourceCompleteAggregatorError(t *testing.T) {
	// Setup hub server
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints/public" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Model",
					"slug":           "model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/satellite-tokens" {
			json.NewEncoder(w).Encode(map[string]string{})
			return
		}
		if r.URL.Path == "/api/v1/auth/transaction-tokens" {
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{}})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hubServer.Close()

	// Setup aggregator that returns error
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "Model unavailable"})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, aggServer.URL, 30*time.Second)

	_, err := chat.Complete(context.Background(), &ChatCompleteRequest{
		Prompt: "Test",
		Model:  "alice/model",
	})

	if err == nil {
		t.Fatal("expected error")
	}
	_, ok := err.(*AggregatorError)
	if !ok {
		t.Fatalf("expected AggregatorError, got %T", err)
	}
}

func TestChatResourceStream(t *testing.T) {
	// Setup hub server
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints/public" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Model",
					"slug":           "model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
			return
		}
		if r.URL.Path == "/api/v1/auth/satellite-tokens" {
			json.NewEncoder(w).Encode(map[string]string{})
			return
		}
		if r.URL.Path == "/api/v1/auth/transaction-tokens" {
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{}})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hubServer.Close()

	// Setup aggregator for streaming
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/stream" {
			t.Errorf("path = %s", r.URL.Path)
		}

		w.Header().Set("Content-Type", "text/event-stream")
		flusher, _ := w.(http.Flusher)

		events := []string{
			"event: retrieval_start\ndata: {}\n\n",
			"event: source_complete\ndata: {\"path\": \"bob/data\", \"status\": \"success\", \"documents\": 3}\n\n",
			"event: retrieval_complete\ndata: {}\n\n",
			"event: generation_start\ndata: {\"model\": \"gpt-4\"}\n\n",
			"event: token\ndata: {\"content\": \"Hello\"}\n\n",
			"event: token\ndata: {\"content\": \" world\"}\n\n",
			"event: done\ndata: {\"response\": \"Hello world\", \"metadata\": {\"total_time_ms\": 100}}\n\n",
		}

		for _, event := range events {
			w.Write([]byte(event))
			flusher.Flush()
		}
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	chat := newChatResource(hub, auth, aggServer.URL, 30*time.Second)

	events, errs := chat.Stream(context.Background(), &ChatCompleteRequest{
		Prompt: "Test",
		Model:  "alice/model",
	})

	var receivedEvents []ChatEvent
	for event := range events {
		receivedEvents = append(receivedEvents, event)
	}

	// Check for errors
	select {
	case err := <-errs:
		if err != nil {
			t.Fatalf("Stream error: %v", err)
		}
	default:
	}

	if len(receivedEvents) != 7 {
		t.Errorf("received %d events, want 7", len(receivedEvents))
	}

	// Verify event types
	if _, ok := receivedEvents[0].(*RetrievalStartEvent); !ok {
		t.Errorf("event 0 should be RetrievalStartEvent, got %T", receivedEvents[0])
	}
	if sc, ok := receivedEvents[1].(*SourceCompleteEvent); !ok {
		t.Errorf("event 1 should be SourceCompleteEvent, got %T", receivedEvents[1])
	} else if sc.Source.Path != "bob/data" {
		t.Errorf("SourceCompleteEvent.Path = %q", sc.Source.Path)
	}
	if _, ok := receivedEvents[2].(*RetrievalCompleteEvent); !ok {
		t.Errorf("event 2 should be RetrievalCompleteEvent, got %T", receivedEvents[2])
	}
	if gs, ok := receivedEvents[3].(*GenerationStartEvent); !ok {
		t.Errorf("event 3 should be GenerationStartEvent, got %T", receivedEvents[3])
	} else if gs.Model != "gpt-4" {
		t.Errorf("GenerationStartEvent.Model = %q", gs.Model)
	}
	if token, ok := receivedEvents[4].(*TokenEvent); !ok {
		t.Errorf("event 4 should be TokenEvent, got %T", receivedEvents[4])
	} else if token.Content != "Hello" {
		t.Errorf("TokenEvent.Content = %q", token.Content)
	}
	if done, ok := receivedEvents[6].(*DoneEvent); !ok {
		t.Errorf("event 6 should be DoneEvent, got %T", receivedEvents[6])
	} else if done.Response != "Hello world" {
		t.Errorf("DoneEvent.Response = %q", done.Response)
	}
}

func TestChatResourceResolveEndpointRef(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Test Model",
					"slug":           "test-model",
					"type":           "model",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{
							"type":    "syftai_space",
							"enabled": true,
							"config": map[string]interface{}{
								"url":         "https://syftai.example.com",
								"tenant_name": "tenant1",
							},
						},
					},
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(httpClient)
		auth := newAuthResource(httpClient)
		chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

		ref, err := chat.resolveEndpointRef(context.Background(), "alice/test-model", "model")
		if err != nil {
			t.Fatalf("resolveEndpointRef error: %v", err)
		}
		if ref.URL != "https://syftai.example.com" {
			t.Errorf("URL = %q", ref.URL)
		}
		if ref.Slug != "test-model" {
			t.Errorf("Slug = %q", ref.Slug)
		}
		if ref.TenantName == nil || *ref.TenantName != "tenant1" {
			t.Errorf("TenantName = %v", ref.TenantName)
		}
		if ref.OwnerUsername == nil || *ref.OwnerUsername != "alice" {
			t.Errorf("OwnerUsername = %v", ref.OwnerUsername)
		}
	})

	t.Run("no connection url", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Test",
					"slug":           "test",
					"type":           "model",
					"owner_username": "alice",
					"connect":        []map[string]interface{}{},
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(httpClient)
		auth := newAuthResource(httpClient)
		chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

		_, err := chat.resolveEndpointRef(context.Background(), "alice/test", "model")
		if err == nil {
			t.Fatal("expected error for endpoint without URL")
		}
		_, ok := err.(*EndpointResolutionError)
		if !ok {
			t.Fatalf("expected EndpointResolutionError, got %T", err)
		}
	})

	t.Run("type mismatch", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Data Source",
					"slug":           "data-source",
					"type":           "data_source",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
		}))
		defer server.Close()

		httpClient := newHTTPClient(server.URL, DefaultTimeout)
		httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(httpClient)
		auth := newAuthResource(httpClient)
		chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

		_, err := chat.resolveEndpointRef(context.Background(), "alice/data-source", "model")
		if err == nil {
			t.Fatal("expected error for type mismatch")
		}
	})
}

func TestTypeMatches(t *testing.T) {
	tests := []struct {
		actualType   string
		expectedType string
		want         bool
	}{
		{"model", "model", true},
		{"data_source", "data_source", true},
		{"model", "data_source", false},
		{"data_source", "model", false},
		{"model_data_source", "model", true},
		{"model_data_source", "data_source", true},
		{"model_data_source", "other", false},
	}

	for _, tt := range tests {
		name := fmt.Sprintf("%s/%s", tt.actualType, tt.expectedType)
		t.Run(name, func(t *testing.T) {
			got := typeMatches(tt.actualType, tt.expectedType)
			if got != tt.want {
				t.Errorf("typeMatches(%q, %q) = %v, want %v", tt.actualType, tt.expectedType, got, tt.want)
			}
		})
	}
}

func TestCollectUniqueOwners(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

	alice := "alice"
	bob := "bob"

	modelRef := &EndpointRef{URL: "https://model.com", OwnerUsername: &alice}
	dsRefs := []EndpointRef{
		{URL: "https://data1.com", OwnerUsername: &bob},
		{URL: "https://data2.com", OwnerUsername: &alice}, // duplicate
	}

	owners := chat.collectUniqueOwners(modelRef, dsRefs)

	if len(owners) != 2 {
		t.Errorf("len(owners) = %d, want 2", len(owners))
	}

	ownerSet := make(map[string]bool)
	for _, o := range owners {
		ownerSet[o] = true
	}
	if !ownerSet["alice"] || !ownerSet["bob"] {
		t.Errorf("owners = %v, should contain alice and bob", owners)
	}
}

func TestCollectTunnelingUsernames(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

	modelRef := &EndpointRef{URL: "tunneling:alice"}
	dsRefs := []EndpointRef{
		{URL: "tunneling:bob"},
		{URL: "https://regular.example.com"},
		{URL: "tunneling:alice"}, // duplicate
	}

	usernames := chat.collectTunnelingUsernames(modelRef, dsRefs)

	if len(usernames) != 2 {
		t.Errorf("len(usernames) = %d, want 2", len(usernames))
	}

	usernameSet := make(map[string]bool)
	for _, u := range usernames {
		usernameSet[u] = true
	}
	if !usernameSet["alice"] || !usernameSet["bob"] {
		t.Errorf("usernames = %v, should contain alice and bob", usernames)
	}
}

func TestBuildRequestBody(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

	alice := "alice"
	tenantName := "tenant1"
	modelRef := &EndpointRef{
		URL:           "https://model.com",
		Slug:          "my-model",
		Name:          "My Model",
		TenantName:    &tenantName,
		OwnerUsername: &alice,
	}

	bob := "bob"
	dsRefs := []EndpointRef{
		{URL: "https://data.com", Slug: "my-data", Name: "My Data", OwnerUsername: &bob},
	}

	endpointTokens := map[string]string{"alice": "token_alice"}
	transactionTokens := map[string]string{"bob": "tx_bob"}
	messages := []Message{{Role: "user", Content: "Hello"}}

	body := chat.buildRequestBody(
		"Test prompt",
		modelRef,
		dsRefs,
		endpointTokens,
		transactionTokens,
		10,
		2048,
		0.8,
		0.7,
		true,
		messages,
		"peer_token",
		"peer_channel",
	)

	if body["prompt"] != "Test prompt" {
		t.Errorf("prompt = %v", body["prompt"])
	}
	if body["top_k"] != 10 {
		t.Errorf("top_k = %v", body["top_k"])
	}
	if body["max_tokens"] != 2048 {
		t.Errorf("max_tokens = %v", body["max_tokens"])
	}
	if body["stream"] != true {
		t.Error("stream should be true")
	}
	if body["peer_token"] != "peer_token" {
		t.Errorf("peer_token = %v", body["peer_token"])
	}
	if body["peer_channel"] != "peer_channel" {
		t.Errorf("peer_channel = %v", body["peer_channel"])
	}

	// Check model
	model := body["model"].(map[string]interface{})
	if model["url"] != "https://model.com" {
		t.Errorf("model.url = %v", model["url"])
	}
	if model["slug"] != "my-model" {
		t.Errorf("model.slug = %v", model["slug"])
	}

	// Check data sources
	dataSources := body["data_sources"].([]map[string]interface{})
	if len(dataSources) != 1 {
		t.Errorf("len(data_sources) = %d", len(dataSources))
	}

	// Check messages
	msgs := body["messages"].([]Message)
	if len(msgs) != 1 {
		t.Errorf("len(messages) = %d", len(msgs))
	}
}

func TestParseSSEEvent(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

	tests := []struct {
		eventType string
		data      string
		checkType func(ChatEvent) bool
	}{
		{
			"retrieval_start",
			"{}",
			func(e ChatEvent) bool { _, ok := e.(*RetrievalStartEvent); return ok },
		},
		{
			"source_complete",
			`{"path": "alice/data", "status": "success", "documents": 5}`,
			func(e ChatEvent) bool {
				sc, ok := e.(*SourceCompleteEvent)
				return ok && sc.Source.Path == "alice/data" && sc.Source.DocumentsRetrieved == 5
			},
		},
		{
			"retrieval_complete",
			"{}",
			func(e ChatEvent) bool { _, ok := e.(*RetrievalCompleteEvent); return ok },
		},
		{
			"generation_start",
			`{"model": "gpt-4"}`,
			func(e ChatEvent) bool {
				gs, ok := e.(*GenerationStartEvent)
				return ok && gs.Model == "gpt-4"
			},
		},
		{
			"token",
			`{"content": "Hello"}`,
			func(e ChatEvent) bool {
				token, ok := e.(*TokenEvent)
				return ok && token.Content == "Hello"
			},
		},
		{
			"done",
			`{"response": "Complete", "metadata": {"total_time_ms": 500}}`,
			func(e ChatEvent) bool {
				done, ok := e.(*DoneEvent)
				return ok && done.Response == "Complete" && done.Metadata.TotalTimeMs == 500
			},
		},
		{
			"error",
			`{"message": "Something went wrong"}`,
			func(e ChatEvent) bool {
				errEvent, ok := e.(*ErrorEvent)
				return ok && errEvent.Error == "Something went wrong"
			},
		},
		{
			"unknown",
			"{}",
			func(e ChatEvent) bool {
				errEvent, ok := e.(*ErrorEvent)
				return ok && errEvent.Error == "Unknown event type: unknown"
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.eventType, func(t *testing.T) {
			event := chat.parseSSEEvent(tt.eventType, tt.data)
			if !tt.checkType(event) {
				t.Errorf("parseSSEEvent(%q, %q) returned unexpected event: %+v", tt.eventType, tt.data, event)
			}
		})
	}
}

func TestParseSSEEventInvalidJSON(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://agg.example.com", DefaultTimeout)

	event := chat.parseSSEEvent("token", "invalid json")
	errEvent, ok := event.(*ErrorEvent)
	if !ok {
		t.Fatalf("expected ErrorEvent, got %T", event)
	}
	if errEvent.Error == "" {
		t.Error("error message should not be empty")
	}
}

func TestGetStringAndGetInt(t *testing.T) {
	m := map[string]interface{}{
		"string_val":  "hello",
		"float_val":   42.5,
		"int_val":     100,
		"missing_val": nil,
	}

	if getString(m, "string_val") != "hello" {
		t.Errorf("getString(string_val) failed")
	}
	if getString(m, "float_val") != "" {
		t.Errorf("getString(float_val) should return empty string")
	}
	if getString(m, "nonexistent") != "" {
		t.Errorf("getString(nonexistent) should return empty string")
	}

	if getInt(m, "float_val") != 42 {
		t.Errorf("getInt(float_val) failed")
	}
	if getInt(m, "int_val") != 100 {
		t.Errorf("getInt(int_val) failed")
	}
	if getInt(m, "string_val") != 0 {
		t.Errorf("getInt(string_val) should return 0")
	}
	if getInt(m, "nonexistent") != 0 {
		t.Errorf("getInt(nonexistent) should return 0")
	}
}
