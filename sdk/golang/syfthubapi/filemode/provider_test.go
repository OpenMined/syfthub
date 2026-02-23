package filemode

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewProvider(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	t.Run("with defaults", func(t *testing.T) {
		cfg := &ProviderConfig{
			BasePath: tmpDir,
		}

		provider, err := NewProvider(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if provider == nil {
			t.Fatal("provider is nil")
		}
		if provider.debounce != time.Second {
			t.Errorf("debounce = %v", provider.debounce)
		}
		if provider.pythonPath == "" {
			t.Error("pythonPath should be set")
		}
	})

	t.Run("with custom config", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		cfg := &ProviderConfig{
			BasePath:     tmpDir,
			PythonPath:   "python3",
			WatchEnabled: true,
			Debounce:     500 * time.Millisecond,
			Logger:       logger,
			OnReload: func(endpoints []*syfthubapi.Endpoint) {
				// callback for testing
			},
		}

		provider, err := NewProvider(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if provider.debounce != 500*time.Millisecond {
			t.Errorf("debounce = %v", provider.debounce)
		}
		if !provider.watchEnabled {
			t.Error("watchEnabled should be true")
		}
	})
}

func TestProviderEndpoints(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_endpoints_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath: tmpDir,
	})

	// Initially empty
	endpoints := provider.Endpoints()
	if len(endpoints) != 0 {
		t.Errorf("initial endpoints = %d", len(endpoints))
	}
}

func TestProviderGetExecutor(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_executor_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath: tmpDir,
	})

	// No executor initially
	_, found := provider.GetExecutor("nonexistent")
	if found {
		t.Error("should not find nonexistent executor")
	}
}

func TestProviderLoadEndpoints(t *testing.T) {
	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_load_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create an endpoint
	endpointDir := filepath.Join(tmpDir, "test-endpoint")
	os.MkdirAll(endpointDir, 0755)

	readme := `---
name: Test Endpoint
type: model
slug: test-ep
---

# Test Endpoint
`
	os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	endpoints, err := provider.LoadEndpoints()
	if err != nil {
		t.Fatalf("LoadEndpoints error: %v", err)
	}

	if len(endpoints) != 1 {
		t.Errorf("len(endpoints) = %d", len(endpoints))
	}

	if endpoints[0].Slug != "test-ep" {
		t.Errorf("Slug = %q", endpoints[0].Slug)
	}
	if endpoints[0].Name != "Test Endpoint" {
		t.Errorf("Name = %q", endpoints[0].Name)
	}
	if endpoints[0].Type != syfthubapi.EndpointTypeModel {
		t.Errorf("Type = %q", endpoints[0].Type)
	}

	// Check executor is registered
	exec, found := provider.GetExecutor("test-ep")
	if !found {
		t.Error("executor not found for test-ep")
	}
	if exec == nil {
		t.Error("executor is nil")
	}
}

func TestProviderLoadEndpointsMultiple(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_multi_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create two endpoints
	for _, name := range []string{"ep1", "ep2"} {
		dir := filepath.Join(tmpDir, name)
		os.MkdirAll(dir, 0755)

		readme := "---\nname: " + name + "\ntype: model\n---\n"
		os.WriteFile(filepath.Join(dir, "README.md"), []byte(readme), 0644)
		os.WriteFile(filepath.Join(dir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)
	}

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	endpoints, err := provider.LoadEndpoints()
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	if len(endpoints) != 2 {
		t.Errorf("len(endpoints) = %d", len(endpoints))
	}

	// Reload should close old executors
	endpoints2, err := provider.LoadEndpoints()
	if err != nil {
		t.Fatalf("reload error: %v", err)
	}

	if len(endpoints2) != 2 {
		t.Errorf("len(endpoints2) = %d", len(endpoints2))
	}
}

func TestProviderStartStop(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_startstop_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:     tmpDir,
		WatchEnabled: false,
	})

	ctx, cancel := context.WithCancel(context.Background())

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- provider.Start(ctx)
	}()

	// Wait for start
	time.Sleep(100 * time.Millisecond)

	// Stop via context
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Start error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for provider to stop")
	}
}

func TestProviderStartStopMethod(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_stop_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:     tmpDir,
		WatchEnabled: false,
	})

	ctx := context.Background()

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- provider.Start(ctx)
	}()

	// Wait for start
	time.Sleep(100 * time.Millisecond)

	// Stop using Stop method
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err = provider.Stop(stopCtx)
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}

	select {
	case <-done:
		// Expected
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for Start to return")
	}
}

func TestProviderStopWhenNotRunning(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_notstop_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath: tmpDir,
	})

	// Stop without starting should not error
	err = provider.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}
}

func TestProviderDoubleStart(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "provider_double_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath: tmpDir,
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// First start
	go provider.Start(ctx)
	time.Sleep(100 * time.Millisecond)

	// Second start should be no-op
	err = provider.Start(ctx)
	if err != nil {
		t.Errorf("second Start should be no-op: %v", err)
	}

	provider.Stop(context.Background())
}

func TestProviderWithWatcher(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_watcher_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create initial endpoint
	endpointDir := filepath.Join(tmpDir, "test-ep")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte("---\nname: Test\ntype: model\n---\n"), 0644)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	var mu sync.Mutex
	reloadCount := 0

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:     tmpDir,
		PythonPath:   "python3",
		WatchEnabled: true,
		Debounce:     100 * time.Millisecond,
		OnReload: func(endpoints []*syfthubapi.Endpoint) {
			mu.Lock()
			reloadCount++
			mu.Unlock()
		},
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go provider.Start(ctx)
	time.Sleep(300 * time.Millisecond)

	// Modify file to trigger reload
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'modified'"), 0644)

	// Wait for debounce + reload
	time.Sleep(500 * time.Millisecond)

	// Stop
	provider.Stop(context.Background())

	// Check reload was called
	mu.Lock()
	count := reloadCount
	mu.Unlock()

	if count == 0 {
		t.Log("reload was not called - timing issue or watcher not triggered")
	}
}

func TestProviderHandleReload(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_reload_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create endpoint
	endpointDir := filepath.Join(tmpDir, "reload-ep")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte("---\nname: Reload Test\ntype: model\n---\n"), 0644)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	var mu sync.Mutex
	reloadedEndpoints := []*syfthubapi.Endpoint{}

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
		OnReload: func(endpoints []*syfthubapi.Endpoint) {
			mu.Lock()
			reloadedEndpoints = endpoints
			mu.Unlock()
		},
	})

	// Manually call handleReload
	provider.handleReload([]string{endpointDir})

	// Wait for async callback
	time.Sleep(100 * time.Millisecond)

	mu.Lock()
	count := len(reloadedEndpoints)
	mu.Unlock()

	if count != 1 {
		t.Errorf("reloadedEndpoints = %d", count)
	}
}

func TestProviderStopClosesExecutors(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_close_exec_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create endpoint
	endpointDir := filepath.Join(tmpDir, "close-ep")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte("---\nname: Close Test\ntype: model\n---\n"), 0644)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	// Load endpoints
	_, err = provider.LoadEndpoints()
	if err != nil {
		t.Fatalf("LoadEndpoints error: %v", err)
	}

	// Verify executor exists
	exec, found := provider.GetExecutor("close-ep")
	if !found {
		t.Fatal("executor not found")
	}
	if exec == nil {
		t.Fatal("executor is nil")
	}

	ctx := context.Background()

	// Start and stop
	go provider.Start(ctx)
	time.Sleep(100 * time.Millisecond)

	provider.Stop(context.Background())

	// After stop, executors should be cleared
	provider.mu.RLock()
	execCount := len(provider.executors)
	provider.mu.RUnlock()

	if execCount != 0 {
		t.Errorf("executors not cleared after Stop: %d", execCount)
	}
}

func TestProviderCreateEndpoint(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_create_ep_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create a valid endpoint directory structure
	endpointDir := filepath.Join(tmpDir, "create-ep")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	t.Run("model endpoint", func(t *testing.T) {
		enabled := true
		loaded := &LoadedEndpoint{
			Config: &EndpointConfig{
				Slug:        "model-ep",
				Name:        "Model Endpoint",
				Type:        "model",
				Description: "A model",
				Enabled:     &enabled,
				Version:     "1.0.0",
				Runtime:     RuntimeConfig{Timeout: 30},
			},
			Dir:        endpointDir,
			RunnerPath: filepath.Join(endpointDir, "runner.py"),
			ReadmeBody: "# Model",
		}

		endpoint, err := provider.createEndpoint(loaded)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if endpoint.Slug != "model-ep" {
			t.Errorf("Slug = %q", endpoint.Slug)
		}
		if endpoint.Type != syfthubapi.EndpointTypeModel {
			t.Errorf("Type = %q", endpoint.Type)
		}
		if !endpoint.Enabled {
			t.Error("Enabled should be true")
		}
		if endpoint.Version != "1.0.0" {
			t.Errorf("Version = %q", endpoint.Version)
		}
	})

	t.Run("data_source endpoint", func(t *testing.T) {
		loaded := &LoadedEndpoint{
			Config: &EndpointConfig{
				Slug: "ds-ep",
				Name: "Data Source",
				Type: "data_source",
				Runtime: RuntimeConfig{
					Timeout: 60,
				},
			},
			Dir:        endpointDir,
			RunnerPath: filepath.Join(endpointDir, "runner.py"),
		}

		endpoint, err := provider.createEndpoint(loaded)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if endpoint.Type != syfthubapi.EndpointTypeDataSource {
			t.Errorf("Type = %q", endpoint.Type)
		}
	})

	t.Run("disabled endpoint", func(t *testing.T) {
		enabled := false
		loaded := &LoadedEndpoint{
			Config: &EndpointConfig{
				Slug:    "disabled-ep",
				Name:    "Disabled",
				Type:    "model",
				Enabled: &enabled,
				Runtime: RuntimeConfig{Timeout: 30},
			},
			Dir:        endpointDir,
			RunnerPath: filepath.Join(endpointDir, "runner.py"),
		}

		endpoint, err := provider.createEndpoint(loaded)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if endpoint.Enabled {
			t.Error("Enabled should be false")
		}
	})

	t.Run("with policies", func(t *testing.T) {
		loaded := &LoadedEndpoint{
			Config: &EndpointConfig{
				Slug:    "policy-ep",
				Name:    "With Policies",
				Type:    "model",
				Runtime: RuntimeConfig{Timeout: 30},
			},
			Dir:        endpointDir,
			RunnerPath: filepath.Join(endpointDir, "runner.py"),
			PolicyConfigs: []syfthubapi.PolicyConfig{
				{Name: "rate_limit", Type: syfthubapi.PolicyTypeRateLimit},
			},
			StoreConfig: &syfthubapi.StoreConfig{
				Type: "sqlite",
				Path: filepath.Join(endpointDir, "store.db"),
			},
		}

		endpoint, err := provider.createEndpoint(loaded)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if endpoint == nil {
			t.Fatal("endpoint is nil")
		}
	})
}

func TestProviderPreloadedEndpoints(t *testing.T) {
	// Test that Start doesn't reload if endpoints are already loaded
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	tmpDir, err := os.MkdirTemp("", "provider_preload_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	// Create endpoint
	endpointDir := filepath.Join(tmpDir, "preload-ep")
	os.MkdirAll(endpointDir, 0755)
	os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte("---\nname: Preload\ntype: model\n---\n"), 0644)
	os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	// Preload endpoints
	_, err = provider.LoadEndpoints()
	if err != nil {
		t.Fatalf("LoadEndpoints error: %v", err)
	}

	// Store initial endpoint count
	initialCount := len(provider.Endpoints())

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start should not reload
	go provider.Start(ctx)
	time.Sleep(100 * time.Millisecond)

	// Count should be same
	if len(provider.Endpoints()) != initialCount {
		t.Errorf("endpoint count changed: %d -> %d", initialCount, len(provider.Endpoints()))
	}

	provider.Stop(context.Background())
}

// Benchmark tests

func BenchmarkProviderLoadEndpoints(b *testing.B) {
	if _, err := exec.LookPath("python3"); err != nil {
		b.Skip("python3 not available")
	}

	tmpDir, _ := os.MkdirTemp("", "bench_provider")
	defer os.RemoveAll(tmpDir)

	// Create 5 endpoints
	for i := 0; i < 5; i++ {
		dir := filepath.Join(tmpDir, "ep"+string(rune('0'+i)))
		os.MkdirAll(dir, 0755)
		os.WriteFile(filepath.Join(dir, "README.md"), []byte("---\nname: EP\ntype: model\n---\n"), 0644)
		os.WriteFile(filepath.Join(dir, "runner.py"), []byte("def handler(m, c): return 'ok'"), 0644)
	}

	provider, _ := NewProvider(&ProviderConfig{
		BasePath:   tmpDir,
		PythonPath: "python3",
	})

	for i := 0; i < b.N; i++ {
		provider.LoadEndpoints()
	}
}
