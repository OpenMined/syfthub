package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// SearchResource
// ---------------------------------------------------------------------------

func TestNewSearchResource(t *testing.T) {
	httpClient := newHTTPClient("http://localhost", DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	chat := newChatResource(hub, auth, "https://aggregator.example.com/", 30*time.Second)

	search := newSearchResource(chat)

	if search == nil {
		t.Fatal("search should not be nil")
	}
	if search.chat != chat {
		t.Error("chat reference not set correctly")
	}
}

func TestSearchResourceQuery(t *testing.T) {
	// Hub server: endpoint listing + satellite + transaction tokens
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "EPFL News",
					"slug":           "epfl-news",
					"type":           "data_source",
					"owner_username": "epfl",
					"connect": []map[string]interface{}{
						{
							"type":    "syftai_space",
							"enabled": true,
							"config":  map[string]interface{}{"url": "https://syftai.example.com"},
						},
					},
				},
			})
		case "/api/v1/auth/satellite-tokens":
			json.NewEncoder(w).Encode(map[string]string{"epfl": "sat_token_epfl"})
		case "/api/v1/accounting/transaction-tokens":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": map[string]string{"epfl": "tx_token_epfl"},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	// Aggregator server
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("unexpected method: %s", r.Method)
		}

		var body map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode body: %v", err)
		}

		// Must set retrieval_only
		if body["retrieval_only"] != true {
			t.Errorf("retrieval_only = %v, want true", body["retrieval_only"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"response": "",
			"sources": map[string]interface{}{
				"EPFL News #1": map[string]interface{}{
					"slug":    "epfl/epfl-news",
					"content": "First story.",
				},
				"EPFL News #2": map[string]interface{}{
					"slug":    "epfl/epfl-news",
					"content": "Second story.",
				},
			},
			"retrieval_info": []map[string]interface{}{
				{"path": "epfl/epfl-news", "status": "success", "documents_retrieved": 2},
			},
			"metadata": map[string]interface{}{
				"retrieval_time_ms":  120,
				"generation_time_ms": 0,
				"total_time_ms":      120,
			},
		})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)

	search := newSearchResource(newChatResource(hub, auth, aggServer.URL, 30*time.Second))

	resp, err := search.Query(context.Background(), &SearchRequest{
		Prompt:      "What happened at EPFL?",
		DataSources: []string{"epfl/epfl-news"},
	})
	if err != nil {
		t.Fatalf("Query error: %v", err)
	}

	if len(resp.Documents) != 2 {
		t.Errorf("Documents length = %d, want 2", len(resp.Documents))
	}
	if len(resp.RetrievalInfo) != 1 {
		t.Errorf("RetrievalInfo length = %d, want 1", len(resp.RetrievalInfo))
	}
	if resp.RetrievalInfo[0].DocumentsRetrieved != 2 {
		t.Errorf("DocumentsRetrieved = %d, want 2", resp.RetrievalInfo[0].DocumentsRetrieved)
	}
	if resp.Metadata.GenerationTimeMs != 0 {
		t.Errorf("GenerationTimeMs = %d, want 0", resp.Metadata.GenerationTimeMs)
	}
	if resp.Metadata.TotalTimeMs != 120 {
		t.Errorf("TotalTimeMs = %d, want 120", resp.Metadata.TotalTimeMs)
	}
}

// ---------------------------------------------------------------------------
// ChatResource.Retrieve sets retrieval_only and uses empty model
// ---------------------------------------------------------------------------

func TestChatResourceRetrieve(t *testing.T) {
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id":             1,
					"name":           "Docs",
					"slug":           "docs",
					"type":           "data_source",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{
							"type":    "syftai_space",
							"enabled": true,
							"config":  map[string]interface{}{"url": "https://syftai.example.com"},
						},
					},
				},
			})
		case "/api/v1/auth/satellite-tokens":
			json.NewEncoder(w).Encode(map[string]string{"alice": "sat_alice"})
		case "/api/v1/accounting/transaction-tokens":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": map[string]string{"alice": "tx_alice"},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	var capturedBody map[string]interface{}
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&capturedBody)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"sources": map[string]interface{}{
				"Doc A": map[string]interface{}{"slug": "alice/docs", "content": "content A"},
			},
			"retrieval_info": []map[string]interface{}{},
			"metadata":       map[string]interface{}{"retrieval_time_ms": 50},
		})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "tok", RefreshToken: "tok"})
	chat := newChatResource(newHubResource(httpClient), newAuthResource(httpClient), aggServer.URL, 30*time.Second)

	resp, err := chat.Retrieve(context.Background(), &SearchRequest{
		Prompt:      "find docs",
		DataSources: []string{"alice/docs"},
	})
	if err != nil {
		t.Fatalf("Retrieve error: %v", err)
	}
	if len(resp.Documents) != 1 {
		t.Errorf("Documents length = %d, want 1", len(resp.Documents))
	}
	if resp.Documents[0].Content != "content A" {
		t.Errorf("Content = %q", resp.Documents[0].Content)
	}
	if resp.Documents[0].Title != "Doc A" {
		t.Errorf("Title = %q", resp.Documents[0].Title)
	}
	if resp.Documents[0].Slug != "alice/docs" {
		t.Errorf("Slug = %q", resp.Documents[0].Slug)
	}

	// retrieval_only must be set to true in the request body
	if capturedBody["retrieval_only"] != true {
		t.Errorf("retrieval_only = %v, want true", capturedBody["retrieval_only"])
	}

	// model fields should be empty (sentinel)
	if model, ok := capturedBody["model"].(map[string]interface{}); ok {
		if model["url"] != "" || model["slug"] != "" {
			t.Errorf("model should be empty sentinel, got url=%v slug=%v", model["url"], model["slug"])
		}
	}
}

func TestChatResourceRetrieveDefaults(t *testing.T) {
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id": 1, "name": "DS", "slug": "ds", "type": "data_source",
					"owner_username": "bob",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
		case "/api/v1/auth/satellite-tokens":
			json.NewEncoder(w).Encode(map[string]string{"bob": "sat_bob"})
		case "/api/v1/accounting/transaction-tokens":
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{"bob": "tx_bob"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	var capturedBody map[string]interface{}
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&capturedBody)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"sources":        map[string]interface{}{},
			"retrieval_info": []map[string]interface{}{},
			"metadata":       map[string]interface{}{"retrieval_time_ms": 10},
		})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "tok", RefreshToken: "tok"})
	chat := newChatResource(newHubResource(httpClient), newAuthResource(httpClient), aggServer.URL, 30*time.Second)

	_, err := chat.Retrieve(context.Background(), &SearchRequest{
		Prompt:      "query",
		DataSources: []string{"bob/ds"},
		// TopK and SimilarityThreshold not set — should use defaults (5, 0.5)
	})
	if err != nil {
		t.Fatalf("Retrieve error: %v", err)
	}

	if topK, _ := capturedBody["top_k"].(float64); topK != 5 {
		t.Errorf("top_k = %v, want 5", capturedBody["top_k"])
	}
	if sim, _ := capturedBody["similarity_threshold"].(float64); sim != 0.5 {
		t.Errorf("similarity_threshold = %v, want 0.5", capturedBody["similarity_threshold"])
	}
}

func TestChatResourceRetrieveCustomAggregatorURL(t *testing.T) {
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id": 1, "name": "DS", "slug": "ds", "type": "data_source",
					"owner_username": "bob",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
		case "/api/v1/auth/satellite-tokens":
			json.NewEncoder(w).Encode(map[string]string{"bob": "sat_bob"})
		case "/api/v1/accounting/transaction-tokens":
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{"bob": "tx_bob"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	customAgg := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"sources":        map[string]interface{}{},
			"retrieval_info": []map[string]interface{}{},
			"metadata":       map[string]interface{}{"retrieval_time_ms": 10},
		})
	}))
	defer customAgg.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "tok", RefreshToken: "tok"})
	chat := newChatResource(newHubResource(httpClient), newAuthResource(httpClient), "http://default-agg/api/v1", 30*time.Second)

	_, err := chat.Retrieve(context.Background(), &SearchRequest{
		Prompt:        "query",
		DataSources:   []string{"bob/ds"},
		AggregatorURL: customAgg.URL,
	})
	if err != nil {
		t.Fatalf("Retrieve with custom aggregator error: %v", err)
	}
}

func TestChatResourceRetrieveAggregatorError(t *testing.T) {
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id": 1, "name": "DS", "slug": "ds", "type": "data_source",
					"owner_username": "bob",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
		case "/api/v1/auth/satellite-tokens":
			json.NewEncoder(w).Encode(map[string]string{"bob": "sat_bob"})
		case "/api/v1/accounting/transaction-tokens":
			json.NewEncoder(w).Encode(map[string]interface{}{"tokens": map[string]string{"bob": "tx_bob"}})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]interface{}{"message": "aggregator overloaded"})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	httpClient.SetTokens(&AuthTokens{AccessToken: "tok", RefreshToken: "tok"})
	chat := newChatResource(newHubResource(httpClient), newAuthResource(httpClient), aggServer.URL, 30*time.Second)

	_, err := chat.Retrieve(context.Background(), &SearchRequest{
		Prompt:      "query",
		DataSources: []string{"bob/ds"},
	})
	if err == nil {
		t.Fatal("expected error from aggregator 500 response")
	}
	aggErr, ok := err.(*AggregatorError)
	if !ok {
		t.Fatalf("expected *AggregatorError, got %T: %v", err, err)
	}
	if aggErr == nil {
		t.Error("AggregatorError should not be nil")
	}
}

// ---------------------------------------------------------------------------
// SearchDocument and SearchRequest types
// ---------------------------------------------------------------------------

func TestSearchDocumentFields(t *testing.T) {
	doc := SearchDocument{
		Title:   "My Title",
		Slug:    "owner/my-slug",
		Content: "Some content here.",
	}
	if doc.Title != "My Title" {
		t.Errorf("Title = %q", doc.Title)
	}
	if doc.Slug != "owner/my-slug" {
		t.Errorf("Slug = %q", doc.Slug)
	}
	if doc.Content != "Some content here." {
		t.Errorf("Content = %q", doc.Content)
	}
}

func TestSearchRequestDefaults(t *testing.T) {
	req := &SearchRequest{
		Prompt:      "test",
		DataSources: []string{"owner/slug"},
	}
	// Zero values (defaults applied in Retrieve)
	if req.TopK != 0 {
		t.Errorf("TopK default = %d, want 0", req.TopK)
	}
	if req.SimilarityThreshold != 0 {
		t.Errorf("SimilarityThreshold default = %v, want 0", req.SimilarityThreshold)
	}
	if req.GuestMode {
		t.Error("GuestMode default should be false")
	}
}

func TestSearchResponseStructure(t *testing.T) {
	resp := &SearchResponse{
		Documents: []SearchDocument{
			{Title: "Doc 1", Slug: "a/b", Content: "content"},
		},
		RetrievalInfo: []SourceInfo{
			{Path: "a/b", DocumentsRetrieved: 1, Status: "success"},
		},
		Metadata: ChatMetadata{TotalTimeMs: 100},
	}
	if len(resp.Documents) != 1 {
		t.Errorf("Documents length = %d", len(resp.Documents))
	}
	if len(resp.RetrievalInfo) != 1 {
		t.Errorf("RetrievalInfo length = %d", len(resp.RetrievalInfo))
	}
	if resp.Metadata.TotalTimeMs != 100 {
		t.Errorf("TotalTimeMs = %d", resp.Metadata.TotalTimeMs)
	}
}

// ---------------------------------------------------------------------------
// Client lazy-init: Search and Aggregators
// ---------------------------------------------------------------------------

func TestClientSearchLazyInit(t *testing.T) {
	client, err := NewClient(WithBaseURL("https://hub.example.com"))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	defer client.Close()

	t.Run("Search resource is not nil", func(t *testing.T) {
		search := client.Search()
		if search == nil {
			t.Error("Search() should not return nil")
		}
	})

	t.Run("Search returns same instance", func(t *testing.T) {
		s1 := client.Search()
		s2 := client.Search()
		if s1 != s2 {
			t.Error("Search() should return the same cached instance")
		}
	})
}

func TestClientAggregatorsLazyInit(t *testing.T) {
	client, err := NewClient(WithBaseURL("https://hub.example.com"))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	defer client.Close()

	t.Run("Aggregators resource is not nil", func(t *testing.T) {
		agg := client.Aggregators()
		if agg == nil {
			t.Error("Aggregators() should not return nil")
		}
	})

	t.Run("Aggregators returns same instance", func(t *testing.T) {
		a1 := client.Aggregators()
		a2 := client.Aggregators()
		if a1 != a2 {
			t.Error("Aggregators() should return the same cached instance")
		}
	})
}

func TestClientSearchGuestMode(t *testing.T) {
	// Guest mode: hub endpoints browsable without auth, guest satellite tokens used
	hubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/endpoints/public":
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{
					"id": 1, "name": "DS", "slug": "ds", "type": "data_source",
					"owner_username": "alice",
					"connect": []map[string]interface{}{
						{"type": "syftai_space", "enabled": true, "config": map[string]interface{}{"url": "https://syftai.example.com"}},
					},
				},
			})
		case "/api/v1/token/guest":
			json.NewEncoder(w).Encode(map[string]interface{}{"target_token": "guest-tok", "expires_in": 3600})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer hubServer.Close()

	var capturedBody map[string]interface{}
	aggServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&capturedBody)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"sources":        map[string]interface{}{},
			"retrieval_info": []map[string]interface{}{},
			"metadata":       map[string]interface{}{"retrieval_time_ms": 5},
		})
	}))
	defer aggServer.Close()

	httpClient := newHTTPClient(hubServer.URL, DefaultTimeout)
	hub := newHubResource(httpClient)
	auth := newAuthResource(httpClient)
	search := newSearchResource(newChatResource(hub, auth, aggServer.URL, 30*time.Second))

	_, err := search.Query(context.Background(), &SearchRequest{
		Prompt:      "hello",
		DataSources: []string{"alice/ds"},
		GuestMode:   true,
	})
	if err != nil {
		t.Fatalf("Query (guest mode) error: %v", err)
	}

	if capturedBody["retrieval_only"] != true {
		t.Errorf("retrieval_only = %v, want true", capturedBody["retrieval_only"])
	}
}
