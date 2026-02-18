package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHubResourceBrowse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints/public" {
			t.Errorf("path = %s", r.URL.Path)
		}

		skip := r.URL.Query().Get("skip")
		limit := r.URL.Query().Get("limit")

		if skip != "0" {
			t.Errorf("skip = %s", skip)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{
			{"name": "Public 1", "slug": "public-1", "owner_username": "alice"},
			{"name": "Public 2", "slug": "public-2", "owner_username": "bob"},
		})

		if limit == "2" {
			// Second page is empty
			if skip == "2" {
				json.NewEncoder(w).Encode([]map[string]interface{}{})
			}
		}
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	hub := newHubResource(http)

	iter := hub.Browse(context.Background())

	var collected []EndpointPublic
	for iter.Next(context.Background()) {
		collected = append(collected, iter.Value())
	}

	if err := iter.Err(); err != nil {
		t.Fatalf("iterator error: %v", err)
	}

	if len(collected) != 2 {
		t.Errorf("collected = %d, want 2", len(collected))
	}
}

func TestHubResourceBrowseWithOptions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		limit := r.URL.Query().Get("limit")
		if limit != "10" {
			t.Errorf("limit = %s, want 10", limit)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	hub := newHubResource(http)

	iter := hub.Browse(context.Background(), WithPageSize(10))
	for iter.Next(context.Background()) {
	}
}

func TestHubResourceTrending(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints/trending" {
			t.Errorf("path = %s", r.URL.Path)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{
			{"name": "Trending 1", "slug": "trending-1", "stars_count": 100},
			{"name": "Trending 2", "slug": "trending-2", "stars_count": 50},
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	hub := newHubResource(http)

	iter := hub.Trending(context.Background())

	var collected []EndpointPublic
	for iter.Next(context.Background()) {
		collected = append(collected, iter.Value())
	}

	if len(collected) != 2 {
		t.Errorf("collected = %d, want 2", len(collected))
	}
}

func TestHubResourceTrendingWithOptions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		minStars := r.URL.Query().Get("min_stars")
		if minStars != "10" {
			t.Errorf("min_stars = %s, want 10", minStars)
		}

		limit := r.URL.Query().Get("limit")
		if limit != "5" {
			t.Errorf("limit = %s, want 5", limit)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	hub := newHubResource(http)

	iter := hub.Trending(context.Background(),
		WithMinStars(10),
		WithTrendingPageSize(5),
	)
	for iter.Next(context.Background()) {
	}
}

func TestHubResourceSearch(t *testing.T) {
	t.Run("successful search", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/search" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["query"] != "machine learning" {
				t.Errorf("query = %v", body["query"])
			}
			if body["top_k"].(float64) != 10 {
				t.Errorf("top_k = %v", body["top_k"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"name": "ML Model", "slug": "ml-model", "relevance_score": 0.9},
					{"name": "AI Helper", "slug": "ai-helper", "relevance_score": 0.7},
				},
				"total": 2,
				"query": "machine learning",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		results, err := hub.Search(context.Background(), "machine learning")
		if err != nil {
			t.Fatalf("Search error: %v", err)
		}

		if len(results) != 2 {
			t.Errorf("results length = %d, want 2", len(results))
		}
		if results[0].RelevanceScore != 0.9 {
			t.Errorf("results[0].RelevanceScore = %f", results[0].RelevanceScore)
		}
	})

	t.Run("with options", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["top_k"].(float64) != 5 {
				t.Errorf("top_k = %v", body["top_k"])
			}
			if body["type"] != "model" {
				t.Errorf("type = %v", body["type"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"name": "Model", "relevance_score": 0.6},
				},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		results, err := hub.Search(context.Background(), "test query",
			WithTopK(5),
			WithEndpointType(EndpointTypeModel),
			WithMinScore(0.5),
		)
		if err != nil {
			t.Fatalf("Search error: %v", err)
		}

		if len(results) != 1 {
			t.Errorf("results length = %d, want 1", len(results))
		}
	})

	t.Run("filters by min score", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"name": "High", "relevance_score": 0.9},
					{"name": "Low", "relevance_score": 0.3},
				},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		results, err := hub.Search(context.Background(), "test", WithMinScore(0.5))
		if err != nil {
			t.Fatalf("Search error: %v", err)
		}

		if len(results) != 1 {
			t.Errorf("results length = %d, want 1 (filtered)", len(results))
		}
		if results[0].RelevanceScore != 0.9 {
			t.Errorf("results[0].RelevanceScore = %f", results[0].RelevanceScore)
		}
	})

	t.Run("short query returns empty", func(t *testing.T) {
		http := newHTTPClient("http://localhost", DefaultTimeout)
		hub := newHubResource(http)

		results, err := hub.Search(context.Background(), "ab")
		if err != nil {
			t.Fatalf("Search error: %v", err)
		}
		if len(results) != 0 {
			t.Errorf("results length = %d, want 0 for short query", len(results))
		}
	})

	t.Run("error returns empty", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		results, err := hub.Search(context.Background(), "test query")
		if err != nil {
			t.Fatalf("Search should not return error: %v", err)
		}
		if len(results) != 0 {
			t.Errorf("results length = %d, want 0 on error", len(results))
		}
	})
}

func TestHubResourceGet(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/public" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"name": "Other", "slug": "other", "owner_username": "bob"},
				{"name": "Target", "slug": "target", "owner_username": "alice"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		ep, err := hub.Get(context.Background(), "alice/target")
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if ep.Slug != "target" {
			t.Errorf("Slug = %q", ep.Slug)
		}
		if ep.OwnerUsername != "alice" {
			t.Errorf("OwnerUsername = %q", ep.OwnerUsername)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"name": "Other", "slug": "other", "owner_username": "bob"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		hub := newHubResource(http)

		_, err := hub.Get(context.Background(), "alice/nonexistent")
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})

	t.Run("invalid path", func(t *testing.T) {
		http := newHTTPClient("http://localhost", DefaultTimeout)
		hub := newHubResource(http)

		_, err := hub.Get(context.Background(), "invalid-path")
		if err == nil {
			t.Fatal("expected error for invalid path")
		}
	})
}

func TestHubResourceStar(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 123, "slug": "my-api"},
			})
			return
		}

		if r.URL.Path != "/api/v1/endpoints/123/star" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(http)

	err := hub.Star(context.Background(), "alice/my-api")
	if err != nil {
		t.Fatalf("Star error: %v", err)
	}
}

func TestHubResourceUnstar(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/endpoints" {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 123, "slug": "my-api"},
			})
			return
		}

		if r.URL.Path != "/api/v1/endpoints/123/star" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "DELETE" {
			t.Errorf("method = %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	hub := newHubResource(http)

	err := hub.Unstar(context.Background(), "alice/my-api")
	if err != nil {
		t.Fatalf("Unstar error: %v", err)
	}
}

func TestHubResourceIsStarred(t *testing.T) {
	t.Run("starred", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/api/v1/endpoints" {
				json.NewEncoder(w).Encode([]map[string]interface{}{
					{"id": 123, "slug": "my-api"},
				})
				return
			}

			if r.URL.Path != "/api/v1/endpoints/123/starred" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode(map[string]bool{"starred": true})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(http)

		starred, err := hub.IsStarred(context.Background(), "alice/my-api")
		if err != nil {
			t.Fatalf("IsStarred error: %v", err)
		}
		if !starred {
			t.Error("should be starred")
		}
	})

	t.Run("not starred", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/api/v1/endpoints" {
				json.NewEncoder(w).Encode([]map[string]interface{}{
					{"id": 123, "slug": "my-api"},
				})
				return
			}

			json.NewEncoder(w).Encode(map[string]bool{"starred": false})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(http)

		starred, err := hub.IsStarred(context.Background(), "alice/my-api")
		if err != nil {
			t.Fatalf("IsStarred error: %v", err)
		}
		if starred {
			t.Error("should not be starred")
		}
	})
}

func TestHubResourceResolveEndpointID(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 1, "slug": "other"},
				{"id": 42, "slug": "target"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(http)

		id, err := hub.resolveEndpointID(context.Background(), "alice/target")
		if err != nil {
			t.Fatalf("resolveEndpointID error: %v", err)
		}
		if id != 42 {
			t.Errorf("id = %d, want 42", id)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 1, "slug": "other"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		hub := newHubResource(http)

		_, err := hub.resolveEndpointID(context.Background(), "alice/nonexistent")
		if err == nil {
			t.Fatal("expected error")
		}
	})
}

func TestHubResourceParsePath(t *testing.T) {
	hub := &HubResource{}

	t.Run("valid path", func(t *testing.T) {
		owner, slug, err := hub.parsePath("alice/my-api")
		if err != nil {
			t.Fatalf("parsePath error: %v", err)
		}
		if owner != "alice" {
			t.Errorf("owner = %q", owner)
		}
		if slug != "my-api" {
			t.Errorf("slug = %q", slug)
		}
	})

	t.Run("with leading/trailing slashes", func(t *testing.T) {
		owner, slug, err := hub.parsePath("/alice/my-api/")
		if err != nil {
			t.Fatalf("parsePath error: %v", err)
		}
		if owner != "alice" {
			t.Errorf("owner = %q", owner)
		}
		if slug != "my-api" {
			t.Errorf("slug = %q", slug)
		}
	})

	t.Run("invalid path", func(t *testing.T) {
		_, _, err := hub.parsePath("invalid")
		if err == nil {
			t.Error("expected error for invalid path")
		}
	})
}
