package containermode

import (
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestWaitForHealth_ImmediateSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	err := WaitForHealth(context.Background(), srv.URL, 5*time.Second, slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}
}

func TestWaitForHealth_DelayedSuccess(t *testing.T) {
	var count atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if count.Add(1) < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	err := WaitForHealth(context.Background(), srv.URL, 5*time.Second, slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}
	if c := count.Load(); c < 3 {
		t.Fatalf("expected at least 3 attempts, got %d", c)
	}
}

func TestWaitForHealth_Timeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	err := WaitForHealth(context.Background(), srv.URL, 500*time.Millisecond, slog.Default())
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
}

func TestWaitForHealth_ContextCancelled(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(200 * time.Millisecond)
		cancel()
	}()

	err := WaitForHealth(ctx, srv.URL, 10*time.Second, slog.Default())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
}
