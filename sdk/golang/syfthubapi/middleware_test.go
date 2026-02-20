package syfthubapi

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"
)

func TestMiddlewareChain(t *testing.T) {
	t.Run("NewMiddlewareChain", func(t *testing.T) {
		chain := NewMiddlewareChain()
		if chain == nil {
			t.Fatal("chain is nil")
		}
		if len(chain.middleware) != 0 {
			t.Error("new chain should be empty")
		}
	})

	t.Run("NewMiddlewareChain with middleware", func(t *testing.T) {
		mw1 := func(next RequestHandler) RequestHandler { return next }
		mw2 := func(next RequestHandler) RequestHandler { return next }

		chain := NewMiddlewareChain(mw1, mw2)
		if len(chain.middleware) != 2 {
			t.Errorf("expected 2 middleware, got %d", len(chain.middleware))
		}
	})

	t.Run("Add middleware", func(t *testing.T) {
		chain := NewMiddlewareChain()
		chain.Add(func(next RequestHandler) RequestHandler { return next })
		chain.Add(func(next RequestHandler) RequestHandler { return next })

		if len(chain.middleware) != 2 {
			t.Errorf("expected 2 middleware, got %d", len(chain.middleware))
		}
	})

	t.Run("Then applies middleware in order", func(t *testing.T) {
		var order []string

		mw1 := func(next RequestHandler) RequestHandler {
			return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
				order = append(order, "mw1-before")
				resp, err := next(ctx, req)
				order = append(order, "mw1-after")
				return resp, err
			}
		}

		mw2 := func(next RequestHandler) RequestHandler {
			return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
				order = append(order, "mw2-before")
				resp, err := next(ctx, req)
				order = append(order, "mw2-after")
				return resp, err
			}
		}

		chain := NewMiddlewareChain(mw1, mw2)

		handler := chain.Then(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			order = append(order, "handler")
			return &TunnelResponse{Status: "success"}, nil
		})

		handler(context.Background(), &TunnelRequest{})

		expected := []string{"mw1-before", "mw2-before", "handler", "mw2-after", "mw1-after"}
		if len(order) != len(expected) {
			t.Fatalf("expected %d entries, got %d: %v", len(expected), len(order), order)
		}
		for i, v := range expected {
			if order[i] != v {
				t.Errorf("order[%d] = %q, want %q", i, order[i], v)
			}
		}
	})
}

func TestLoggingMiddleware(t *testing.T) {
	t.Run("logs success", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		mw := LoggingMiddleware(logger)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{
			CorrelationID: "test-123",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
		}
		handler(context.Background(), req)

		output := buf.String()
		if !strings.Contains(output, "request started") {
			t.Error("should log request started")
		}
		if !strings.Contains(output, "request completed") {
			t.Error("should log request completed")
		}
		if !strings.Contains(output, "test-123") {
			t.Error("should include correlation ID")
		}
	})

	t.Run("logs error response", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		mw := LoggingMiddleware(logger)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{
				Status: "error",
				Error:  &TunnelError{Code: TunnelErrorCodeExecutionFailed, Message: "handler failed"},
			}, nil
		})

		req := &TunnelRequest{
			CorrelationID: "test-456",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep"},
		}
		handler(context.Background(), req)

		output := buf.String()
		if !strings.Contains(output, "request error") {
			t.Error("should log request error")
		}
	})

	t.Run("logs handler error", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		mw := LoggingMiddleware(logger)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return nil, errors.New("handler panic")
		})

		req := &TunnelRequest{
			CorrelationID: "test-789",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep"},
		}
		handler(context.Background(), req)

		output := buf.String()
		if !strings.Contains(output, "request failed") {
			t.Error("should log request failed")
		}
	})
}

func TestRecoveryMiddleware(t *testing.T) {
	t.Run("recovers from panic", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		mw := RecoveryMiddleware(logger)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			panic("test panic")
		})

		req := &TunnelRequest{
			CorrelationID: "panic-test",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep"},
		}

		resp, _ := handler(context.Background(), req)

		if resp == nil {
			t.Fatal("response should not be nil after panic recovery")
		}
		if resp.Status != "error" {
			t.Errorf("status = %q, want %q", resp.Status, "error")
		}
		if resp.Error == nil {
			t.Fatal("error should not be nil")
		}
		if resp.Error.Code != TunnelErrorCodeInternalError {
			t.Errorf("error code = %q", resp.Error.Code)
		}
		if !strings.Contains(buf.String(), "handler panic recovered") {
			t.Error("should log panic recovery")
		}
	})

	t.Run("passes through normal response", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		mw := RecoveryMiddleware(logger)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test"}}
		resp, err := handler(context.Background(), req)

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}
	})
}

func TestTimeoutMiddleware(t *testing.T) {
	t.Run("completes before timeout", func(t *testing.T) {
		mw := TimeoutMiddleware(100 * time.Millisecond)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test"}}
		resp, err := handler(context.Background(), req)

		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}
	})

	t.Run("returns timeout error when exceeded", func(t *testing.T) {
		mw := TimeoutMiddleware(10 * time.Millisecond)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			time.Sleep(100 * time.Millisecond)
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{
			CorrelationID: "timeout-test",
			Endpoint:      TunnelEndpointInfo{Slug: "test"},
		}
		resp, err := handler(context.Background(), req)

		if err != nil {
			t.Errorf("should not return error, got: %v", err)
		}
		if resp == nil {
			t.Fatal("response should not be nil")
		}
		if resp.Status != "error" {
			t.Errorf("status = %q, want %q", resp.Status, "error")
		}
		if resp.Error == nil || resp.Error.Code != TunnelErrorCodeTimeout {
			t.Error("should be timeout error")
		}
	})

	t.Run("respects context cancellation", func(t *testing.T) {
		mw := TimeoutMiddleware(1 * time.Second)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			<-ctx.Done()
			return nil, ctx.Err()
		})

		ctx, cancel := context.WithCancel(context.Background())
		go func() {
			time.Sleep(10 * time.Millisecond)
			cancel()
		}()

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test"}}
		resp, _ := handler(ctx, req)

		if resp == nil {
			t.Fatal("response should not be nil")
		}
		if resp.Status != "error" {
			t.Errorf("status = %q", resp.Status)
		}
	})
}

// mockMetricsCollector implements MetricsCollector for testing
type mockMetricsCollector struct {
	records []struct {
		endpoint string
		duration time.Duration
		status   string
	}
}

func (m *mockMetricsCollector) RecordRequest(endpoint string, duration time.Duration, status string) {
	m.records = append(m.records, struct {
		endpoint string
		duration time.Duration
		status   string
	}{endpoint, duration, status})
}

func TestMetricsMiddleware(t *testing.T) {
	t.Run("records success", func(t *testing.T) {
		collector := &mockMetricsCollector{}
		mw := MetricsMiddleware(collector)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test-ep"}}
		handler(context.Background(), req)

		if len(collector.records) != 1 {
			t.Fatalf("expected 1 record, got %d", len(collector.records))
		}
		if collector.records[0].endpoint != "test-ep" {
			t.Errorf("endpoint = %q", collector.records[0].endpoint)
		}
		if collector.records[0].status != "success" {
			t.Errorf("status = %q", collector.records[0].status)
		}
	})

	t.Run("records error response", func(t *testing.T) {
		collector := &mockMetricsCollector{}
		mw := MetricsMiddleware(collector)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return &TunnelResponse{Status: "error"}, nil
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test-ep"}}
		handler(context.Background(), req)

		if collector.records[0].status != "error" {
			t.Errorf("status = %q", collector.records[0].status)
		}
	})

	t.Run("records handler error", func(t *testing.T) {
		collector := &mockMetricsCollector{}
		mw := MetricsMiddleware(collector)
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			return nil, errors.New("handler error")
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test-ep"}}
		handler(context.Background(), req)

		if collector.records[0].status != "error" {
			t.Errorf("status = %q", collector.records[0].status)
		}
	})
}

func TestCorrelationIDMiddleware(t *testing.T) {
	t.Run("generates ID when missing", func(t *testing.T) {
		mw := CorrelationIDMiddleware()
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			if req.CorrelationID == "" {
				t.Error("CorrelationID should be set")
			}
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test"}}
		handler(context.Background(), req)
	})

	t.Run("preserves existing ID", func(t *testing.T) {
		mw := CorrelationIDMiddleware()
		handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			if req.CorrelationID != "existing-id" {
				t.Errorf("CorrelationID = %q, want %q", req.CorrelationID, "existing-id")
			}
			return &TunnelResponse{Status: "success"}, nil
		})

		req := &TunnelRequest{
			CorrelationID: "existing-id",
			Endpoint:      TunnelEndpointInfo{Slug: "test"},
		}
		handler(context.Background(), req)
	})
}

func TestRequestIDMiddleware(t *testing.T) {
	// RequestIDMiddleware is an alias for CorrelationIDMiddleware
	mw := RequestIDMiddleware()
	handler := mw(func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
		if req.CorrelationID == "" {
			t.Error("CorrelationID should be set")
		}
		return &TunnelResponse{Status: "success"}, nil
	})

	req := &TunnelRequest{Endpoint: TunnelEndpointInfo{Slug: "test"}}
	handler(context.Background(), req)
}

func TestGenerateRequestID(t *testing.T) {
	id1 := generateRequestID()
	time.Sleep(1 * time.Millisecond)
	id2 := generateRequestID()

	if id1 == "" {
		t.Error("ID should not be empty")
	}
	if id1 == id2 {
		t.Error("IDs should be unique")
	}
	// ID format: YYYYMMDDHHmmss.nnnnnnnnn
	if len(id1) < 15 {
		t.Errorf("ID too short: %q", id1)
	}
}

func TestSlogLogger(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug}))
	sl := NewSlogLogger(logger)

	sl.Debug("debug message", "key", "value")
	if !strings.Contains(buf.String(), "debug message") {
		t.Error("Debug should log")
	}

	buf.Reset()
	sl.Info("info message")
	if !strings.Contains(buf.String(), "info message") {
		t.Error("Info should log")
	}

	buf.Reset()
	sl.Warn("warn message")
	if !strings.Contains(buf.String(), "warn message") {
		t.Error("Warn should log")
	}

	buf.Reset()
	sl.Error("error message")
	if !strings.Contains(buf.String(), "error message") {
		t.Error("Error should log")
	}
}

func TestLoggerInterface(t *testing.T) {
	// Verify SlogLogger implements Logger interface
	var _ Logger = (*SlogLogger)(nil)
}
