package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAggregatorsResourceList(t *testing.T) {
	t.Run("with aggregators", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/aggregators" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "GET" {
				t.Errorf("method = %s", r.Method)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"aggregators": []map[string]interface{}{
					{"id": 1, "name": "Aggregator 1", "url": "https://agg1.example.com", "is_default": true},
					{"id": 2, "name": "Aggregator 2", "url": "https://agg2.example.com", "is_default": false},
				},
				"default_aggregator_id": 1,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		result, err := aggregators.List(context.Background())
		if err != nil {
			t.Fatalf("List error: %v", err)
		}
		if len(result) != 2 {
			t.Errorf("len(result) = %d, want 2", len(result))
		}
		if result[0].Name != "Aggregator 1" {
			t.Errorf("Name = %q", result[0].Name)
		}
		if !result[0].IsDefault {
			t.Error("first aggregator should be default")
		}
	})

	t.Run("empty list", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"aggregators":           []interface{}{},
				"default_aggregator_id": nil,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		result, err := aggregators.List(context.Background())
		if err != nil {
			t.Fatalf("List error: %v", err)
		}
		if result == nil {
			t.Error("result should not be nil")
		}
		if len(result) != 0 {
			t.Errorf("len(result) = %d, want 0", len(result))
		}
	})
}

func TestAggregatorsResourceGet(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/aggregators/1" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":         1,
				"name":       "My Aggregator",
				"url":        "https://agg.example.com",
				"is_default": true,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		agg, err := aggregators.Get(context.Background(), 1)
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if agg.Name != "My Aggregator" {
			t.Errorf("Name = %q", agg.Name)
		}
		if agg.URL != "https://agg.example.com" {
			t.Errorf("URL = %q", agg.URL)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Aggregator not found"})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		_, err := aggregators.Get(context.Background(), 999)
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestAggregatorsResourceCreate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/users/me/aggregators" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["name"] != "New Aggregator" {
			t.Errorf("name = %v", body["name"])
		}
		if body["url"] != "https://new-agg.example.com" {
			t.Errorf("url = %v", body["url"])
		}

		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":         1,
			"name":       "New Aggregator",
			"url":        "https://new-agg.example.com",
			"is_default": true,
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	aggregators := newAggregatorsResource(http)

	agg, err := aggregators.Create(context.Background(), "New Aggregator", "https://new-agg.example.com")
	if err != nil {
		t.Fatalf("Create error: %v", err)
	}
	if agg.Name != "New Aggregator" {
		t.Errorf("Name = %q", agg.Name)
	}
	if !agg.IsDefault {
		t.Error("first aggregator should be default")
	}
}

func TestAggregatorsResourceUpdate(t *testing.T) {
	t.Run("update name", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/aggregators/1" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "PUT" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["name"] != "Updated Name" {
				t.Errorf("name = %v", body["name"])
			}
			if _, ok := body["url"]; ok {
				t.Error("url should not be present")
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":   1,
				"name": "Updated Name",
				"url":  "https://agg.example.com",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		name := "Updated Name"
		agg, err := aggregators.Update(context.Background(), 1, &UpdateAggregatorRequest{
			Name: &name,
		})
		if err != nil {
			t.Fatalf("Update error: %v", err)
		}
		if agg.Name != "Updated Name" {
			t.Errorf("Name = %q", agg.Name)
		}
	})

	t.Run("update url", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["url"] != "https://new-url.example.com" {
				t.Errorf("url = %v", body["url"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":   1,
				"name": "Aggregator",
				"url":  "https://new-url.example.com",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		url := "https://new-url.example.com"
		agg, err := aggregators.Update(context.Background(), 1, &UpdateAggregatorRequest{
			URL: &url,
		})
		if err != nil {
			t.Fatalf("Update error: %v", err)
		}
		if agg.URL != "https://new-url.example.com" {
			t.Errorf("URL = %q", agg.URL)
		}
	})

	t.Run("update both", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["name"] != "New Name" {
				t.Errorf("name = %v", body["name"])
			}
			if body["url"] != "https://new.example.com" {
				t.Errorf("url = %v", body["url"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":   1,
				"name": "New Name",
				"url":  "https://new.example.com",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		name := "New Name"
		url := "https://new.example.com"
		_, err := aggregators.Update(context.Background(), 1, &UpdateAggregatorRequest{
			Name: &name,
			URL:  &url,
		})
		if err != nil {
			t.Fatalf("Update error: %v", err)
		}
	})
}

func TestAggregatorsResourceDelete(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/aggregators/1" {
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
		aggregators := newAggregatorsResource(http)

		err := aggregators.Delete(context.Background(), 1)
		if err != nil {
			t.Fatalf("Delete error: %v", err)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Aggregator not found"})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		err := aggregators.Delete(context.Background(), 999)
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestAggregatorsResourceSetDefault(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/aggregators/2/default" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "PATCH" {
				t.Errorf("method = %s", r.Method)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":         2,
				"name":       "Aggregator 2",
				"url":        "https://agg2.example.com",
				"is_default": true,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		agg, err := aggregators.SetDefault(context.Background(), 2)
		if err != nil {
			t.Fatalf("SetDefault error: %v", err)
		}
		if !agg.IsDefault {
			t.Error("should be default")
		}
		if agg.ID != 2 {
			t.Errorf("ID = %d", agg.ID)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Aggregator not found"})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		aggregators := newAggregatorsResource(http)

		_, err := aggregators.SetDefault(context.Background(), 999)
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestNewAggregatorsResource(t *testing.T) {
	http := newHTTPClient("http://localhost", DefaultTimeout)
	aggregators := newAggregatorsResource(http)

	if aggregators == nil {
		t.Fatal("aggregators should not be nil")
	}
	if aggregators.http != http {
		t.Error("http client not set correctly")
	}
}
