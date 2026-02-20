package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMyEndpointsResourceList(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints" {
			t.Errorf("path = %s", r.URL.Path)
		}

		skip := r.URL.Query().Get("skip")
		limit := r.URL.Query().Get("limit")

		if skip != "0" {
			t.Errorf("skip = %s", skip)
		}
		if limit != "20" {
			t.Errorf("limit = %s", limit)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{
			{"id": 1, "name": "Endpoint 1", "slug": "endpoint-1"},
			{"id": 2, "name": "Endpoint 2", "slug": "endpoint-2"},
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	endpoints := newMyEndpointsResource(http)

	iter := endpoints.List(context.Background())

	var collected []Endpoint
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

func TestMyEndpointsResourceListWithOptions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		visibility := r.URL.Query().Get("visibility")
		if visibility != "public" {
			t.Errorf("visibility = %s", visibility)
		}

		limit := r.URL.Query().Get("limit")
		if limit != "10" {
			t.Errorf("limit = %s, want 10", limit)
		}

		json.NewEncoder(w).Encode([]map[string]interface{}{})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	endpoints := newMyEndpointsResource(http)

	iter := endpoints.List(context.Background(),
		WithVisibility(VisibilityPublic),
		WithListPageSize(10),
	)

	for iter.Next(context.Background()) {
	}
}

func TestMyEndpointsResourceCreate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["name"] != "My API" {
			t.Errorf("name = %v", body["name"])
		}
		if body["type"] != "model" {
			t.Errorf("type = %v", body["type"])
		}
		if body["visibility"] != "public" {
			t.Errorf("visibility = %v", body["visibility"])
		}

		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":          1,
			"name":        "My API",
			"slug":        "my-api",
			"type":        "model",
			"visibility":  "public",
			"description": "A cool API",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	endpoints := newMyEndpointsResource(http)

	ep, err := endpoints.Create(context.Background(), &CreateEndpointRequest{
		Name:        "My API",
		Type:        EndpointTypeModel,
		Visibility:  VisibilityPublic,
		Description: "A cool API",
		Readme:      "# My API",
	})

	if err != nil {
		t.Fatalf("Create error: %v", err)
	}
	if ep.Name != "My API" {
		t.Errorf("Name = %q", ep.Name)
	}
	if ep.Slug != "my-api" {
		t.Errorf("Slug = %q", ep.Slug)
	}
}

func TestMyEndpointsResourceCreateWithOptionalFields(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["slug"] != "custom-slug" {
			t.Errorf("slug = %v", body["slug"])
		}
		if _, ok := body["tags"]; !ok {
			t.Error("tags should be present")
		}
		if _, ok := body["policies"]; !ok {
			t.Error("policies should be present")
		}
		if _, ok := body["connect"]; !ok {
			t.Error("connect should be present")
		}

		json.NewEncoder(w).Encode(map[string]interface{}{"id": 1, "name": "Test"})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	endpoints := newMyEndpointsResource(http)

	slug := "custom-slug"
	_, err := endpoints.Create(context.Background(), &CreateEndpointRequest{
		Name:       "Test",
		Type:       EndpointTypeModel,
		Visibility: VisibilityPublic,
		Slug:       &slug,
		Tags:       []string{"tag1", "tag2"},
		Policies:   []Policy{{Type: "allow_list", Enabled: true}},
		Connect:    []Connection{{Type: "syftai_space", Enabled: true}},
	})

	if err != nil {
		t.Fatalf("Create error: %v", err)
	}
}

func TestMyEndpointsResourceGet(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 1, "name": "Other", "slug": "other"},
				{"id": 2, "name": "My API", "slug": "my-api"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		endpoints := newMyEndpointsResource(http)

		ep, err := endpoints.Get(context.Background(), "alice/my-api")
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if ep.Slug != "my-api" {
			t.Errorf("Slug = %q", ep.Slug)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": 1, "name": "Other", "slug": "other"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		endpoints := newMyEndpointsResource(http)

		_, err := endpoints.Get(context.Background(), "alice/nonexistent")
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
		endpoints := newMyEndpointsResource(http)

		_, err := endpoints.Get(context.Background(), "invalid-path")
		if err == nil {
			t.Fatal("expected error for invalid path")
		}
	})
}

func TestMyEndpointsResourceUpdate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints/slug/my-api" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "PATCH" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["name"] != "Updated Name" {
			t.Errorf("name = %v", body["name"])
		}
		if body["description"] != "Updated description" {
			t.Errorf("description = %v", body["description"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":          1,
			"name":        "Updated Name",
			"slug":        "my-api",
			"description": "Updated description",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	endpoints := newMyEndpointsResource(http)

	name := "Updated Name"
	desc := "Updated description"
	ep, err := endpoints.Update(context.Background(), "alice/my-api", &UpdateEndpointRequest{
		Name:        &name,
		Description: &desc,
	})

	if err != nil {
		t.Fatalf("Update error: %v", err)
	}
	if ep.Name != "Updated Name" {
		t.Errorf("Name = %q", ep.Name)
	}
}

func TestMyEndpointsResourceDelete(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/endpoints/slug/my-api" {
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
	endpoints := newMyEndpointsResource(http)

	err := endpoints.Delete(context.Background(), "alice/my-api")
	if err != nil {
		t.Fatalf("Delete error: %v", err)
	}
}

func TestMyEndpointsResourceSync(t *testing.T) {
	t.Run("with endpoints", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/sync" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			endpoints := body["endpoints"].([]interface{})
			if len(endpoints) != 2 {
				t.Errorf("endpoints length = %d", len(endpoints))
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"synced":    2,
				"deleted":   1,
				"endpoints": []map[string]interface{}{},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		endpoints := newMyEndpointsResource(http)

		resp, err := endpoints.Sync(context.Background(), []map[string]interface{}{
			{"name": "Endpoint 1", "type": "model"},
			{"name": "Endpoint 2", "type": "data_source"},
		})

		if err != nil {
			t.Fatalf("Sync error: %v", err)
		}
		if resp.Synced != 2 {
			t.Errorf("Synced = %d", resp.Synced)
		}
		if resp.Deleted != 1 {
			t.Errorf("Deleted = %d", resp.Deleted)
		}
	})

	t.Run("with nil endpoints", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			endpoints := body["endpoints"].([]interface{})
			if len(endpoints) != 0 {
				t.Errorf("endpoints length = %d, want 0", len(endpoints))
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"synced":    0,
				"deleted":   5,
				"endpoints": []map[string]interface{}{},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		endpoints := newMyEndpointsResource(http)

		resp, err := endpoints.Sync(context.Background(), nil)
		if err != nil {
			t.Fatalf("Sync error: %v", err)
		}
		if resp.Deleted != 5 {
			t.Errorf("Deleted = %d", resp.Deleted)
		}
	})
}

func TestMyEndpointsResourceParsePath(t *testing.T) {
	endpoints := &MyEndpointsResource{}

	t.Run("valid path", func(t *testing.T) {
		owner, slug, err := endpoints.parsePath("alice/my-api")
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

	t.Run("with leading slash", func(t *testing.T) {
		owner, slug, err := endpoints.parsePath("/alice/my-api")
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
		_, _, err := endpoints.parsePath("invalid")
		if err == nil {
			t.Error("expected error for invalid path")
		}
	})

	t.Run("too many parts", func(t *testing.T) {
		_, _, err := endpoints.parsePath("alice/my-api/extra")
		if err == nil {
			t.Error("expected error for path with too many parts")
		}
	})
}
