package syfthubapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewRequestProcessor(t *testing.T) {
	registry := NewEndpointRegistry()
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	cfg := &ProcessorConfig{
		Registry: registry,
		Logger:   logger,
	}

	proc := NewRequestProcessor(cfg)
	if proc == nil {
		t.Fatal("processor is nil")
	}
}

func TestRequestProcessorSetLogHook(t *testing.T) {
	proc := &RequestProcessor{}

	proc.SetLogHook(func(ctx context.Context, log *RequestLog) {
		// hook set for testing
	})

	if proc.logHook == nil {
		t.Error("logHook should be set")
	}
}

func TestRequestProcessorProcess(t *testing.T) {
	setup := func() (*RequestProcessor, *EndpointRegistry) {
		registry := NewEndpointRegistry()
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		// Mock auth server
		authServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(VerifyTokenResponse{
				Valid:    true,
				Sub:      "user-123",
				Username: "testuser",
				Email:    "test@example.com",
				Role:     "user",
			})
		}))
		t.Cleanup(authServer.Close)

		authClient := NewAuthClient(authServer.URL, "test-key", NewSlogLogger(logger))

		proc := NewRequestProcessor(&ProcessorConfig{
			Registry:   registry,
			AuthClient: authClient,
			Logger:     logger,
		})

		return proc, registry
	}

	t.Run("auth fails with no auth client", func(t *testing.T) {
		registry := NewEndpointRegistry()
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		proc := NewRequestProcessor(&ProcessorConfig{
			Registry:   registry,
			AuthClient: nil,
			Logger:     logger,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for missing auth client")
		}
		if resp.Error.Code != TunnelErrorCodeAuthFailed {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("endpoint not found", func(t *testing.T) {
		proc, _ := setup()

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "nonexistent", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for nonexistent endpoint")
		}
		if resp.Error.Code != TunnelErrorCodeEndpointNotFound {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("endpoint disabled", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "disabled-ep",
			Name:    "Disabled",
			Type:    EndpointTypeModel,
			Enabled: false,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "disabled-ep", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for disabled endpoint")
		}
		if resp.Error.Code != TunnelErrorCodeEndpointDisabled {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("data source success", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "ds-ep",
			Name:    "Data Source",
			Type:    EndpointTypeDataSource,
			Enabled: true,
			dataSourceHandler: func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
				return []Document{
					{DocumentID: "doc1", Content: "content1"},
				}, nil
			},
		})

		payload, _ := json.Marshal(DataSourceQueryRequest{Messages: "test query"})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "ds-ep", Type: "data_source"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, err := proc.Process(context.Background(), req)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}
		if resp.Timing == nil {
			t.Error("Timing should not be nil")
		}
	})

	t.Run("model success", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "model-ep",
			Name:    "Model",
			Type:    EndpointTypeModel,
			Enabled: true,
			modelHandler: func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
				return "Hello!", nil
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "model-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, err := proc.Process(context.Background(), req)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}

		// Verify response structure
		var modelResp ModelQueryResponse
		if err := json.Unmarshal(resp.Payload, &modelResp); err != nil {
			t.Fatalf("unmarshal error: %v", err)
		}
		if modelResp.Summary.Message.Content != "Hello!" {
			t.Errorf("content = %q", modelResp.Summary.Message.Content)
		}
	})

	t.Run("handler execution failure", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "failing-ep",
			Name:    "Failing",
			Type:    EndpointTypeModel,
			Enabled: true,
			modelHandler: func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
				return "", errors.New("handler crashed")
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "failing-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for handler failure")
		}
		if resp.Error.Code != TunnelErrorCodeExecutionFailed {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("invalid payload", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "model-ep",
			Name:    "Model",
			Type:    EndpointTypeModel,
			Enabled: true,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "model-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        json.RawMessage(`invalid json`),
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for invalid payload")
		}
	})

	t.Run("unknown endpoint type", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "unknown-ep",
			Name:    "Unknown",
			Type:    "unknown_type",
			Enabled: true,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "unknown-ep", Type: "unknown_type"},
			SatelliteToken: "valid-token",
			Payload:        json.RawMessage(`{}`),
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for unknown type")
		}
	})

	t.Run("log hook called", func(t *testing.T) {
		proc, registry := setup()

		hookCalled := false
		var capturedLog *RequestLog
		proc.SetLogHook(func(ctx context.Context, log *RequestLog) {
			hookCalled = true
			capturedLog = log
		})

		registry.Register(&Endpoint{
			Slug:    "logged-ep",
			Name:    "Logged",
			Type:    EndpointTypeModel,
			Enabled: true,
			modelHandler: func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
				return "response", nil
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "logged-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		proc.Process(context.Background(), req)

		if !hookCalled {
			t.Error("log hook should be called")
		}
		if capturedLog == nil {
			t.Fatal("captured log is nil")
		}
		if capturedLog.CorrelationID != "test-123" {
			t.Errorf("CorrelationID = %q", capturedLog.CorrelationID)
		}
	})
}

func TestRequestProcessorErrorResponse(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	proc := &RequestProcessor{logger: logger}

	req := &TunnelRequest{
		CorrelationID: "err-123",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep"},
	}

	resp := proc.errorResponse(req, TunnelErrorCodeExecutionFailed, "test error")

	if resp.Protocol != "syfthub-tunnel/v1" {
		t.Errorf("Protocol = %q", resp.Protocol)
	}
	if resp.Type != "endpoint_response" {
		t.Errorf("Type = %q", resp.Type)
	}
	if resp.Status != "error" {
		t.Errorf("Status = %q", resp.Status)
	}
	if resp.CorrelationID != "err-123" {
		t.Errorf("CorrelationID = %q", resp.CorrelationID)
	}
	if resp.Error.Code != TunnelErrorCodeExecutionFailed {
		t.Errorf("Error.Code = %q", resp.Error.Code)
	}
	if resp.Error.Message != "test error" {
		t.Errorf("Error.Message = %q", resp.Error.Message)
	}
}

func TestEnrichLogWithRequestContent(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))
	proc := &RequestProcessor{logger: logger}

	t.Run("model request", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hello"}},
		})
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  payload,
		}

		proc.enrichLogWithRequestContent(log, req)

		if len(log.Request.Messages) != 1 {
			t.Errorf("Messages length = %d", len(log.Request.Messages))
		}
	})

	t.Run("data source request", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		payload, _ := json.Marshal(DataSourceQueryRequest{Messages: "test query"})
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "data_source"},
			Payload:  payload,
		}

		proc.enrichLogWithRequestContent(log, req)

		if log.Request.Query != "test query" {
			t.Errorf("Query = %q", log.Request.Query)
		}
	})

	t.Run("nil request in log", func(t *testing.T) {
		log := &RequestLog{}
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  json.RawMessage(`{}`),
		}

		// Should not panic
		proc.enrichLogWithRequestContent(log, req)
	})

	t.Run("invalid json payload", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  json.RawMessage(`invalid`),
		}

		// Should not panic, just not populate messages
		proc.enrichLogWithRequestContent(log, req)
		if log.Request.Messages != nil {
			t.Error("Messages should be nil for invalid JSON")
		}
	})
}
