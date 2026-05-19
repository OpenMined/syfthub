package transport

import (
	"bytes"
	"context"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewNATSTransport(t *testing.T) {
	t.Run("success with credentials", func(t *testing.T) {
		cfg := &Config{
			SpaceURL: "tunneling:testuser",
			NATSCredentials: &syfthubapi.NATSCredentials{
				URL:     "wss://nats.example.com/nats",
				Token:   "test-token-12345678901234567890",
				Subject: "syfthub.space.test",
			},
		}

		transport, err := NewNATSTransport(&NATSConn{}, cfg)
		if err != nil {
			t.Fatalf("NewNATSTransport error: %v", err)
		}

		if transport == nil {
			t.Fatal("transport is nil")
		}
	})

	t.Run("fails without credentials", func(t *testing.T) {
		cfg := &Config{
			SpaceURL: "tunneling:testuser",
			// No NATSCredentials
		}

		_, err := NewNATSTransport(&NATSConn{}, cfg)
		if err == nil {
			t.Fatal("expected error for missing credentials")
		}
		if !strings.Contains(err.Error(), "NATSCredentials") {
			t.Errorf("expected error to mention NATSCredentials, got: %v", err)
		}
	})

	t.Run("with logger", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		cfg := &Config{
			SpaceURL: "tunneling:testuser",
			NATSCredentials: &syfthubapi.NATSCredentials{
				URL:     "wss://nats.example.com/nats",
				Token:   "test-token-12345678901234567890",
				Subject: "syfthub.space.test",
			},
			Logger: logger,
		}

		transport, err := NewNATSTransport(&NATSConn{}, cfg)
		if err != nil {
			t.Fatalf("NewNATSTransport error: %v", err)
		}

		if transport == nil {
			t.Fatal("transport is nil")
		}
	})
}

func TestNATSTransportSetRequestHandler(t *testing.T) {
	cfg := &Config{
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)

	transport.SetRequestHandler(func(ctx context.Context, req *syfthubapi.TunnelRequest) (*syfthubapi.TunnelResponse, error) {
		return &syfthubapi.TunnelResponse{Status: "success"}, nil
	})

	if transport.handler == nil {
		t.Error("handler should be set")
	}
}

func TestNATSTransportStopWhenNotRunning(t *testing.T) {
	cfg := &Config{
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)

	// Stop without starting should not error
	err := transport.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop when not running should not error: %v", err)
	}
}

func TestNATSTransportDoubleStart(t *testing.T) {
	cfg := &Config{
		SpaceURL: "tunneling:testuser",
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)

	// Manually set running to true to simulate already started
	transport.mu.Lock()
	transport.running = true
	transport.mu.Unlock()

	// Second start should error
	err := transport.Start(context.Background())
	if err == nil {
		t.Error("double start should error")
	}
}

func TestNATSTransportStartContextCancel(t *testing.T) {
	// Skip this test if we can't connect (no real NATS server)
	t.Skip("requires NATS server")

	cfg := &Config{
		SpaceURL: "tunneling:testuser",
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://localhost:4222/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	done := make(chan error, 1)
	go func() {
		done <- transport.Start(ctx)
	}()

	select {
	case <-done:
		// Expected - context timeout or connection failure
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for Start to return")
	}
}

// Transport interface test
func TestNATSTransportInterface(t *testing.T) {
	// Verify NATSTransport implements Transport interface
	var _ Transport = (*NATSTransport)(nil)
}

func TestNATSTransportConfigValidation(t *testing.T) {
	tests := []struct {
		name        string
		credentials *syfthubapi.NATSCredentials
		expectError bool
	}{
		{
			name: "valid credentials",
			credentials: &syfthubapi.NATSCredentials{
				URL:     "wss://nats.example.com/nats",
				Token:   "test-token-12345678901234567890",
				Subject: "syfthub.space.test",
			},
			expectError: false,
		},
		{
			name:        "nil credentials",
			credentials: nil,
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &Config{
				NATSCredentials: tt.credentials,
			}

			_, err := NewNATSTransport(&NATSConn{}, cfg)
			if tt.expectError && err == nil {
				t.Error("expected error")
			}
			if !tt.expectError && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}

func TestNATSTransportStopAfterStopCalled(t *testing.T) {
	cfg := &Config{
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)

	// First stop (not running, should be no-op)
	err := transport.Stop(context.Background())
	if err != nil {
		t.Errorf("first Stop error: %v", err)
	}

	// Second stop should also be no-op
	err = transport.Stop(context.Background())
	if err != nil {
		t.Errorf("second Stop error: %v", err)
	}
}

// Benchmarks

func BenchmarkNewNATSTransport(b *testing.B) {
	cfg := &Config{
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	for i := 0; i < b.N; i++ {
		NewNATSTransport(&NATSConn{}, cfg)
	}
}

func BenchmarkSetRequestHandler(b *testing.B) {
	cfg := &Config{
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.space.test",
		},
	}

	transport, _ := NewNATSTransport(&NATSConn{}, cfg)
	handler := func(ctx context.Context, req *syfthubapi.TunnelRequest) (*syfthubapi.TunnelResponse, error) {
		return &syfthubapi.TunnelResponse{Status: "success"}, nil
	}

	for i := 0; i < b.N; i++ {
		transport.SetRequestHandler(handler)
	}
}
