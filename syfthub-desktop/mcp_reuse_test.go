package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpbridge"
)

// fakeBridge is a stand-in stdio child: it records start/close counts so tests
// can assert reuse vs respawn without spawning a real process.
type fakeBridge struct {
	starts atomic.Int32
	closes atomic.Int32
}

func (f *fakeBridge) Start(context.Context) error { f.starts.Add(1); return nil }
func (f *fakeBridge) Handler() http.Handler       { return http.NotFoundHandler() }
func (f *fakeBridge) Close() error                { f.closes.Add(1); return nil }

// reuseHost builds an mcpHost whose stdio bridges are fakes, returning the host
// and a func to fetch the (single) fake created per server name.
func reuseHost(t *testing.T, grace time.Duration) (*mcpHost, func(server string) *fakeBridge) {
	t.Helper()
	reg := newMCPRegistry(t.TempDir())
	if err := reg.upsert(mcpServerDef{
		Name: "linear", Transport: mcpTransportStdio,
		Command: []string{"linear-mcp"}, Env: map[string]string{"LINEAR_API_KEY": "sk"}, Enabled: true,
	}); err != nil {
		t.Fatal(err)
	}
	host := newMCPHost(reg, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	host.grace = grace

	var mu sync.Mutex
	fakes := map[string]*fakeBridge{}
	host.factory = func(name string, _ mcpbridge.Config, _ *slog.Logger) (mcpBridge, error) {
		mu.Lock()
		defer mu.Unlock()
		f := &fakeBridge{}
		fakes[name] = f
		return f, nil
	}
	return host, func(server string) *fakeBridge {
		mu.Lock()
		defer mu.Unlock()
		return fakes[server]
	}
}

// TestStdioBridgeReusedOnFullReload: re-Provision (no Deprovision) reuses the
// running child — no second spawn, no close.
func TestStdioBridgeReusedOnFullReload(t *testing.T) {
	host, fake := reuseHost(t, time.Minute)
	defer host.Stop()

	host.Routes("ep", []string{"linear"})
	host.Routes("ep", []string{"linear"}) // full reload: Provision again, no Deprovision

	f := fake("linear")
	if f == nil {
		t.Fatal("bridge never created")
	}
	if got := f.starts.Load(); got != 1 {
		t.Errorf("starts = %d, want 1 (reused across reload)", got)
	}
	if got := f.closes.Load(); got != 0 {
		t.Errorf("closes = %d, want 0", got)
	}
}

// TestStdioBridgeRevivedWithinGrace: Deprovision then Provision inside the grace
// window reuses the child (the scheduled release is voided).
func TestStdioBridgeRevivedWithinGrace(t *testing.T) {
	host, fake := reuseHost(t, time.Minute)
	defer host.Stop()

	host.Routes("ep", []string{"linear"})
	host.ReleaseSlug("ep")                // Deprovision schedules release
	host.Routes("ep", []string{"linear"}) // Provision within grace revives

	f := fake("linear")
	if got := f.starts.Load(); got != 1 {
		t.Errorf("starts = %d, want 1 (revived, not respawned)", got)
	}
	if got := f.closes.Load(); got != 0 {
		t.Errorf("closes = %d, want 0 (revived before grace)", got)
	}
}

// TestStdioBridgeClosedAfterGraceOnRemoval: Deprovision with no following
// Provision closes the child after the grace period.
func TestStdioBridgeClosedAfterGraceOnRemoval(t *testing.T) {
	host, fake := reuseHost(t, 20*time.Millisecond)
	defer host.Stop()

	host.Routes("ep", []string{"linear"})
	host.ReleaseSlug("ep") // removal: no Provision follows

	f := fake("linear")
	waitFor(t, time.Second, func() bool { return f.closes.Load() == 1 })
	if got := f.starts.Load(); got != 1 {
		t.Errorf("starts = %d, want 1", got)
	}
}

// TestStdioBridgeReleasedWhenDroppedFromAllowlist: a server removed from an
// endpoint's expose_mcp is released even on the full-reload path (no
// Deprovision).
func TestStdioBridgeReleasedWhenDroppedFromAllowlist(t *testing.T) {
	host, fake := reuseHost(t, 20*time.Millisecond)
	defer host.Stop()

	host.Routes("ep", []string{"linear"})
	host.Routes("ep", []string{}) // reload with linear removed from the allowlist

	f := fake("linear")
	waitFor(t, time.Second, func() bool { return f.closes.Load() == 1 })
}

// TestStdioBridgeRespawnedOnConfigChange: changing the server's command/env
// retires the old child and spawns a new one.
func TestStdioBridgeRespawnedOnConfigChange(t *testing.T) {
	host, fake := reuseHost(t, time.Minute)
	defer host.Stop()

	host.Routes("ep", []string{"linear"})
	old := fake("linear")

	// Change the registry def, then reload.
	if err := host.registry.upsert(mcpServerDef{
		Name: "linear", Transport: mcpTransportStdio,
		Command: []string{"linear-mcp", "--v2"}, Enabled: true,
	}); err != nil {
		t.Fatal(err)
	}
	host.Routes("ep", []string{"linear"})

	waitFor(t, time.Second, func() bool { return old.closes.Load() == 1 })
	// A fresh bridge was started (the factory replaced the stored fake).
	cur := fake("linear")
	if cur == old {
		t.Fatal("expected a new bridge after config change")
	}
	if got := cur.starts.Load(); got != 1 {
		t.Errorf("new bridge starts = %d, want 1", got)
	}
}

func waitFor(t *testing.T, timeout time.Duration, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(2 * time.Millisecond)
	}
	t.Fatalf("condition not met within %s", timeout)
}
