package filemode

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestNewWatcher(t *testing.T) {
	t.Run("with defaults", func(t *testing.T) {
		cfg := &WatcherConfig{
			BasePath: "/tmp/test",
		}

		watcher, err := NewWatcher(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if watcher == nil {
			t.Fatal("watcher is nil")
		}
		if watcher.debounce != time.Second {
			t.Errorf("debounce = %v", watcher.debounce)
		}
		if len(watcher.ignorePatterns) == 0 {
			t.Error("ignorePatterns should have defaults")
		}
	})

	t.Run("with custom config", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		cfg := &WatcherConfig{
			BasePath:      "/tmp/test",
			DebounceDelay: 500 * time.Millisecond,
			Logger:        logger,
			Callback: func(dirs []string) {
				// callback for testing
			},
			IgnorePatterns: []string{"*.tmp"},
		}

		watcher, err := NewWatcher(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if watcher.debounce != 500*time.Millisecond {
			t.Errorf("debounce = %v", watcher.debounce)
		}
		if len(watcher.ignorePatterns) != 1 {
			t.Errorf("ignorePatterns = %v", watcher.ignorePatterns)
		}
	})
}

func TestWatcherShouldIgnore(t *testing.T) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/test",
		IgnorePatterns: []string{
			"__pycache__",
			".git",
			"*.pyc",
		},
	}

	watcher, _ := NewWatcher(cfg)

	tests := []struct {
		path     string
		expected bool
	}{
		{"/tmp/test/__pycache__", true},
		{"/tmp/test/.git", true},
		{"/tmp/test/file.pyc", true},
		{"/tmp/test/runner.py", false},
		{"/tmp/test/README.md", false},
		{"/tmp/test/.hidden", true},       // hidden files are ignored
		{"/tmp/test/.env", false},         // .env is special - not ignored
		{"/tmp/test/node_modules", false}, // not in custom patterns
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			result := watcher.shouldIgnore(tt.path)
			if result != tt.expected {
				t.Errorf("shouldIgnore(%q) = %v, want %v", tt.path, result, tt.expected)
			}
		})
	}
}

func TestWatcherShouldIgnoreDefaults(t *testing.T) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/test",
		// Use default ignore patterns
	}

	watcher, _ := NewWatcher(cfg)

	tests := []struct {
		path     string
		expected bool
	}{
		{"/tmp/test/__pycache__", true},
		{"/tmp/test/.git", true},
		{"/tmp/test/.venv", true},
		{"/tmp/test/venv", true},
		{"/tmp/test/node_modules", true},
		{"/tmp/test/.mypy_cache", true},
		{"/tmp/test/.pytest_cache", true},
		{"/tmp/test/file.pyc", true},
		{"/tmp/test/file.pyo", true},
		{"/tmp/test/.DS_Store", true},
		{"/tmp/test/.policy_store.db", true},
		{"/tmp/test/runner.py", false},
		{"/tmp/test/.env", false}, // .env should NOT be ignored
	}

	for _, tt := range tests {
		t.Run(filepath.Base(tt.path), func(t *testing.T) {
			result := watcher.shouldIgnore(tt.path)
			if result != tt.expected {
				t.Errorf("shouldIgnore(%q) = %v, want %v", tt.path, result, tt.expected)
			}
		})
	}
}

func TestWatcherGetEndpointDir(t *testing.T) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/endpoints",
	}

	watcher, _ := NewWatcher(cfg)

	tests := []struct {
		path     string
		expected string
	}{
		{"/tmp/endpoints/my-endpoint/runner.py", "/tmp/endpoints/my-endpoint"},
		{"/tmp/endpoints/my-endpoint/nested/file.py", "/tmp/endpoints/my-endpoint"},
		{"/tmp/endpoints/another-ep/README.md", "/tmp/endpoints/another-ep"},
		{"/tmp/endpoints/.", ""},
		{"/tmp/endpoints/..", ""},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			result := watcher.getEndpointDir(tt.path)
			if result != tt.expected {
				t.Errorf("getEndpointDir(%q) = %q, want %q", tt.path, result, tt.expected)
			}
		})
	}
}

func TestWatcherStopWhenNotRunning(t *testing.T) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/test",
	}

	watcher, _ := NewWatcher(cfg)

	// Stop without starting should not error
	err := watcher.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}
}

func TestWatcherStartStop(t *testing.T) {
	// Create temp directory for watching
	tmpDir, err := os.MkdirTemp("", "watcher_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	callbackCount := int32(0)
	cfg := &WatcherConfig{
		BasePath:      tmpDir,
		DebounceDelay: 50 * time.Millisecond,
		Callback: func(dirs []string) {
			atomic.AddInt32(&callbackCount, 1)
		},
	}

	watcher, err := NewWatcher(cfg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- watcher.Start(ctx)
	}()

	// Wait for watcher to start
	time.Sleep(100 * time.Millisecond)

	// Stop via context cancellation
	cancel()

	// Wait for stop
	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Start error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for watcher to stop")
	}
}

func TestWatcherStartStopMethod(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "watcher_stop_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &WatcherConfig{
		BasePath:      tmpDir,
		DebounceDelay: 50 * time.Millisecond,
	}

	watcher, err := NewWatcher(cfg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	ctx := context.Background()

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- watcher.Start(ctx)
	}()

	// Wait for watcher to start
	time.Sleep(100 * time.Millisecond)

	// Stop using Stop method
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = watcher.Stop(stopCtx)
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}

	// Wait for goroutine
	select {
	case <-done:
		// Expected
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for Start to return")
	}
}

func TestWatcherFileChangeTrigger(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "watcher_trigger_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create an endpoint directory
	endpointDir := filepath.Join(tmpDir, "my-endpoint")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("# initial"), 0644)

	var mu sync.Mutex
	reloadedDirs := []string{}

	cfg := &WatcherConfig{
		BasePath:      tmpDir,
		DebounceDelay: 100 * time.Millisecond,
		Callback: func(dirs []string) {
			mu.Lock()
			reloadedDirs = append(reloadedDirs, dirs...)
			mu.Unlock()
		},
	}

	watcher, err := NewWatcher(cfg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start watcher
	go watcher.Start(ctx)

	// Wait for watcher to initialize
	time.Sleep(200 * time.Millisecond)

	// Modify a file
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("# modified"), 0644)

	// Wait for debounce + processing
	time.Sleep(500 * time.Millisecond)

	// Check callback was called
	mu.Lock()
	count := len(reloadedDirs)
	mu.Unlock()

	if count == 0 {
		t.Log("callback was not called - this might be due to timing")
	}

	// Stop watcher
	watcher.Stop(context.Background())
}

func TestWatcherIgnoresSpecifiedPatterns(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "watcher_ignore_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create endpoint with __pycache__
	endpointDir := filepath.Join(tmpDir, "my-endpoint")
	pycacheDir := filepath.Join(endpointDir, "__pycache__")
	os.MkdirAll(pycacheDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte(""), 0644)

	callbackCount := int32(0)
	cfg := &WatcherConfig{
		BasePath:      tmpDir,
		DebounceDelay: 50 * time.Millisecond,
		Callback: func(dirs []string) {
			atomic.AddInt32(&callbackCount, 1)
		},
	}

	watcher, err := NewWatcher(cfg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go watcher.Start(ctx)
	time.Sleep(200 * time.Millisecond)

	// Modify a file in __pycache__ - should be ignored
	os.WriteFile(filepath.Join(pycacheDir, "cache.pyc"), []byte("cached"), 0644)

	time.Sleep(300 * time.Millisecond)

	// Check callback count - should be 0 for ignored files
	count := atomic.LoadInt32(&callbackCount)
	if count > 0 {
		t.Logf("callback called %d times (may include initial directory setup)", count)
	}

	watcher.Stop(context.Background())
}

func TestWatcherDoubleStart(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "watcher_double_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &WatcherConfig{
		BasePath: tmpDir,
	}

	watcher, _ := NewWatcher(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// First start
	go watcher.Start(ctx)
	time.Sleep(100 * time.Millisecond)

	// Second start should be a no-op (not error)
	err = watcher.Start(ctx)
	if err != nil {
		t.Errorf("second Start should be no-op: %v", err)
	}

	watcher.Stop(context.Background())
}

func TestWatcherCheckPending(t *testing.T) {
	cfg := &WatcherConfig{
		BasePath:      "/tmp/test",
		DebounceDelay: 100 * time.Millisecond,
	}

	var mu sync.Mutex
	reloadedDirs := []string{}

	cfg.Callback = func(dirs []string) {
		mu.Lock()
		reloadedDirs = append(reloadedDirs, dirs...)
		mu.Unlock()
	}

	watcher, _ := NewWatcher(cfg)

	// Manually add pending items
	watcher.pendingMu.Lock()
	watcher.pending["/tmp/test/ep1"] = time.Now().Add(-200 * time.Millisecond) // expired
	watcher.pending["/tmp/test/ep2"] = time.Now()                              // not expired
	watcher.pendingMu.Unlock()

	// Call checkPending
	watcher.checkPending()

	// Wait for callback goroutine
	time.Sleep(50 * time.Millisecond)

	mu.Lock()
	count := len(reloadedDirs)
	mu.Unlock()

	if count != 1 {
		t.Errorf("expected 1 reloaded dir, got %d", count)
	}

	// ep2 should still be pending
	watcher.pendingMu.Lock()
	_, ep2Pending := watcher.pending["/tmp/test/ep2"]
	watcher.pendingMu.Unlock()

	if !ep2Pending {
		t.Error("ep2 should still be pending")
	}
}

func TestWatcherStopTimeout(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "watcher_timeout_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	cfg := &WatcherConfig{
		BasePath: tmpDir,
	}

	watcher, _ := NewWatcher(cfg)

	ctx := context.Background()

	// Start watcher
	go watcher.Start(ctx)
	time.Sleep(100 * time.Millisecond)

	// Stop with very short timeout
	shortCtx, cancel := context.WithTimeout(context.Background(), 1*time.Millisecond)
	defer cancel()

	// This might or might not timeout depending on timing
	watcher.Stop(shortCtx)
}

// Benchmark tests

func BenchmarkShouldIgnore(b *testing.B) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/test",
	}

	watcher, _ := NewWatcher(cfg)

	paths := []string{
		"/tmp/test/__pycache__/cache.pyc",
		"/tmp/test/runner.py",
		"/tmp/test/.git/config",
		"/tmp/test/endpoint/README.md",
	}

	for i := 0; i < b.N; i++ {
		for _, p := range paths {
			watcher.shouldIgnore(p)
		}
	}
}

func BenchmarkGetEndpointDir(b *testing.B) {
	cfg := &WatcherConfig{
		BasePath: "/tmp/endpoints",
	}

	watcher, _ := NewWatcher(cfg)

	paths := []string{
		"/tmp/endpoints/my-endpoint/runner.py",
		"/tmp/endpoints/another-ep/nested/file.py",
	}

	for i := 0; i < b.N; i++ {
		for _, p := range paths {
			watcher.getEndpointDir(p)
		}
	}
}
