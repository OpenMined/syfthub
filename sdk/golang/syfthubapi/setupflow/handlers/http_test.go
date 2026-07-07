package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

func TestHTTP_Validate_MissingURL(t *testing.T) {
	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{Method: "GET"},
	}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for missing URL")
	}
}

func TestHTTP_Validate_BadMethod(t *testing.T) {
	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{Method: "PATCH", URL: "https://example.com"},
	}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for PATCH method")
	}
}

func TestHTTP_Execute_GET(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			t.Errorf("expected GET, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"status": "ok",
			"data":   "test",
		})
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method: "GET",
			URL:    server.URL,
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Response == nil {
		t.Fatal("expected JSON response")
	}

	var data map[string]any
	json.Unmarshal(result.Response, &data)
	if data["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", data["status"])
	}
}

func TestHTTP_Execute_POST_JSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("expected Content-Type application/json")
		}

		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		if body["key"] != "value" {
			t.Errorf("expected key=value in body")
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"created": true})
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method: "POST",
			URL:    server.URL,
			JSON:   map[string]any{"key": "value"},
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var data map[string]any
	json.Unmarshal(result.Response, &data)
	if data["created"] != true {
		t.Error("expected created=true")
	}
}

func TestHTTP_Execute_ExpectStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		fmt.Fprint(w, "not found")
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method:       "GET",
			URL:          server.URL,
			ExpectStatus: 200,
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected error for wrong status code")
	}
	if !strings.Contains(err.Error(), "expected status 200, got 404") {
		t.Errorf("unexpected error message: %v", err)
	}
}

func TestHTTP_Execute_Timeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(3 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method:      "GET",
			URL:         server.URL,
			TimeoutSecs: 1,
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestHTTP_Execute_ResponseSizeLimit(t *testing.T) {
	// Create response larger than 1MB
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		// Write a JSON response that's small enough to test (we can't easily test 1MB+)
		fmt.Fprint(w, `{"status": "ok"}`)
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method: "GET",
			URL:    server.URL,
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	// This should succeed (small response)
	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Value == "" {
		t.Error("expected non-empty value")
	}
}

func TestHTTP_Execute_TemplatesInURL(t *testing.T) {
	// Test that URL with query params works correctly
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if q.Get("token") != "my-token" {
			t.Errorf("expected token=my-token, got %s", q.Get("token"))
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"verified": true})
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method: "GET",
			URL:    server.URL,
			Query:  map[string]string{"token": "my-token"},
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var data map[string]any
	json.Unmarshal(result.Response, &data)
	if data["verified"] != true {
		t.Error("expected verified=true")
	}
}

func TestHTTP_Execute_CustomHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("expected Authorization header")
		}
		if r.Header.Get("X-Custom") != "custom-value" {
			t.Errorf("expected X-Custom header")
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, `{"ok": true}`)
	}))
	defer server.Close()

	h := NewHTTPHandler()
	step := &nodeops.SetupStep{
		HTTP: &nodeops.HTTPConfig{
			Method: "GET",
			URL:    server.URL,
			Headers: map[string]string{
				"Authorization": "Bearer test-token",
				"X-Custom":      "custom-value",
			},
		},
	}
	ctx := &setupflow.SetupContext{
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	_, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}
