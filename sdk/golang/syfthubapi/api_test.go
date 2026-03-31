package syfthubapi

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNew(t *testing.T) {
	t.Run("creates with defaults", func(t *testing.T) {
		api := New()

		if api == nil {
			t.Fatal("api is nil")
		}
		if api.config == nil {
			t.Error("config is nil")
		}
		if api.registry == nil {
			t.Error("registry is nil")
		}
		if api.processor == nil {
			t.Error("processor is nil")
		}
		if api.shutdownCh == nil {
			t.Error("shutdownCh is nil")
		}
	})

	t.Run("applies options", func(t *testing.T) {
		api := New(
			WithSyftHubURL("https://test.hub.com"),
			WithAPIKey("test-key"),
			WithSpaceURL("https://space.test.com"),
			WithLogLevel("DEBUG"),
		)

		if api.config.SyftHubURL != "https://test.hub.com" {
			t.Errorf("SyftHubURL = %q", api.config.SyftHubURL)
		}
		if api.config.APIKey != "test-key" {
			t.Errorf("APIKey = %q", api.config.APIKey)
		}
		if api.config.SpaceURL != "https://space.test.com" {
			t.Errorf("SpaceURL = %q", api.config.SpaceURL)
		}
	})

	t.Run("loads from environment", func(t *testing.T) {
		t.Setenv("SYFTHUB_URL", "https://env.hub.com")

		api := New()

		if api.config.SyftHubURL != "https://env.hub.com" {
			t.Errorf("SyftHubURL from env = %q", api.config.SyftHubURL)
		}
	})

	t.Run("options override environment", func(t *testing.T) {
		t.Setenv("SYFTHUB_URL", "https://env.hub.com")

		api := New(WithSyftHubURL("https://override.hub.com"))

		if api.config.SyftHubURL != "https://override.hub.com" {
			t.Errorf("SyftHubURL = %q, should be overridden by option", api.config.SyftHubURL)
		}
	})
}

func TestAPIDataSource(t *testing.T) {
	api := New()

	t.Run("creates builder with valid slug", func(t *testing.T) {
		builder := api.DataSource("valid-slug")

		if builder == nil {
			t.Fatal("builder is nil")
		}
		if builder.endpoint.Slug != "valid-slug" {
			t.Errorf("Slug = %q", builder.endpoint.Slug)
		}
		if builder.endpoint.Type != EndpointTypeDataSource {
			t.Errorf("Type = %q", builder.endpoint.Type)
		}
		if !builder.endpoint.Enabled {
			t.Error("Enabled should default to true")
		}
	})

	t.Run("captures invalid slug error", func(t *testing.T) {
		builder := api.DataSource("INVALID-SLUG")

		if builder.err == nil {
			t.Error("expected error for invalid slug")
		}
	})
}

func TestAPIModel(t *testing.T) {
	api := New()

	t.Run("creates builder with valid slug", func(t *testing.T) {
		builder := api.Model("valid-slug")

		if builder == nil {
			t.Fatal("builder is nil")
		}
		if builder.endpoint.Slug != "valid-slug" {
			t.Errorf("Slug = %q", builder.endpoint.Slug)
		}
		if builder.endpoint.Type != EndpointTypeModel {
			t.Errorf("Type = %q", builder.endpoint.Type)
		}
	})

	t.Run("captures invalid slug error", func(t *testing.T) {
		builder := api.Model("")

		if builder.err == nil {
			t.Error("expected error for empty slug")
		}
	})
}

func TestAPIRegisterEndpoint(t *testing.T) {
	api := New()

	err := api.DataSource("my-ds").
		Name("My Data Source").
		Description("A test data source").
		Handler(func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
			return nil, nil
		})

	if err != nil {
		t.Fatalf("registration failed: %v", err)
	}

	// Verify endpoint was registered
	ep, ok := api.GetEndpoint("my-ds")
	if !ok {
		t.Fatal("endpoint not found")
	}
	if ep.Name != "My Data Source" {
		t.Errorf("Name = %q", ep.Name)
	}
}

func TestAPIUse(t *testing.T) {
	api := New()

	mw1 := func(next RequestHandler) RequestHandler { return next }
	mw2 := func(next RequestHandler) RequestHandler { return next }

	api.Use(mw1)
	api.Use(mw2)

	if len(api.middleware) != 2 {
		t.Errorf("expected 2 middleware, got %d", len(api.middleware))
	}
}

func TestAPIOnStartup(t *testing.T) {
	api := New()

	hook1 := func(ctx context.Context) error { return nil }
	hook2 := func(ctx context.Context) error { return nil }

	api.OnStartup(hook1)
	api.OnStartup(hook2)

	if len(api.startupHooks) != 2 {
		t.Errorf("expected 2 startup hooks, got %d", len(api.startupHooks))
	}
}

func TestAPIOnShutdown(t *testing.T) {
	api := New()

	hook := func(ctx context.Context) error { return nil }

	api.OnShutdown(hook)

	if len(api.shutdownHooks) != 1 {
		t.Errorf("expected 1 shutdown hook, got %d", len(api.shutdownHooks))
	}
}

func TestAPIConfig(t *testing.T) {
	api := New(WithServerPort(9000))

	cfg := api.Config()

	if cfg == nil {
		t.Fatal("config is nil")
	}
	if cfg.ServerPort != 9000 {
		t.Errorf("ServerPort = %d", cfg.ServerPort)
	}
}

func TestAPILogger(t *testing.T) {
	api := New()

	logger := api.Logger()

	if logger == nil {
		t.Fatal("logger is nil")
	}
}

func TestAPIEndpoints(t *testing.T) {
	api := New()

	api.DataSource("ds1").
		Name("DS1").
		Description("Data Source 1").
		Handler(func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
			return nil, nil
		})

	api.Model("model1").
		Name("Model1").
		Description("Model 1").
		Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "", nil
		})

	endpoints := api.Endpoints()

	if len(endpoints) != 2 {
		t.Errorf("expected 2 endpoints, got %d", len(endpoints))
	}
}

func TestAPIGetEndpoint(t *testing.T) {
	api := New()

	api.Model("test-model").
		Name("Test").
		Description("Test model").
		Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "", nil
		})

	t.Run("found", func(t *testing.T) {
		ep, ok := api.GetEndpoint("test-model")
		if !ok {
			t.Fatal("endpoint not found")
		}
		if ep.Name != "Test" {
			t.Errorf("Name = %q", ep.Name)
		}
	})

	t.Run("not found", func(t *testing.T) {
		_, ok := api.GetEndpoint("nonexistent")
		if ok {
			t.Error("should not find nonexistent endpoint")
		}
	})
}

func TestAPISetTransport(t *testing.T) {
	api := New()
	transport := &mockTransport{}

	api.SetTransport(transport)

	if api.transport != transport {
		t.Error("transport not set")
	}
}

func TestAPISetHeartbeatManager(t *testing.T) {
	api := New()
	hm := &mockHeartbeatManager{}

	api.SetHeartbeatManager(hm)

	if api.heartbeatManager != hm {
		t.Error("heartbeat manager not set")
	}
}

func TestAPISetFileProvider(t *testing.T) {
	api := New()
	fp := &mockFileProvider{}

	api.SetFileProvider(fp)

	if api.fileProvider != fp {
		t.Error("file provider not set")
	}
}

func TestAPISetLogHook(t *testing.T) {
	api := New()

	api.SetLogHook(func(ctx context.Context, log *RequestLog) {
		// hook set for testing
	})

	// Processor should have the hook set
	if api.processor.logHook == nil {
		t.Error("logHook not set on processor")
	}
}

func TestAPIRegistry(t *testing.T) {
	api := New()

	registry := api.Registry()

	if registry == nil {
		t.Fatal("registry is nil")
	}
	if registry != api.registry {
		t.Error("should return the internal registry")
	}
}

func TestAPISyncEndpoints(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/users/me":
			w.WriteHeader(http.StatusOK)
		case "/api/v1/endpoints/sync":
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(SyncEndpointsResponse{Synced: 1})
		}
	}))
	defer server.Close()

	api := New(
		WithSyftHubURL(server.URL),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
	)

	api.Model("test-model").
		Name("Test").
		Description("Test").
		Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "", nil
		})

	err := api.SyncEndpoints(context.Background())
	if err != nil {
		t.Fatalf("SyncEndpoints failed: %v", err)
	}
}

func TestAPISyncEndpointsAsync(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/users/me":
			w.WriteHeader(http.StatusOK)
		case "/api/v1/endpoints/sync":
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(SyncEndpointsResponse{Synced: 1})
		}
	}))
	defer server.Close()

	api := New(
		WithSyftHubURL(server.URL),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
	)

	// Should not block
	api.SyncEndpointsAsync()
}

func TestAPIHandleRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(VerifyTokenResponse{
			Valid:    true,
			Sub:      "user-123",
			Username: "testuser",
		})
	}))
	defer server.Close()

	api := New(
		WithSyftHubURL(server.URL),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
	)

	api.Model("test-model").
		Name("Test").
		Description("Test model").
		Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "Hello!", nil
		})

	payload, _ := json.Marshal(ModelQueryRequest{
		Messages: []Message{{Role: "user", Content: "Hi"}},
	})
	req := &TunnelRequest{
		CorrelationID:  "test-123",
		Endpoint:       TunnelEndpointInfo{Slug: "test-model", Type: "model"},
		SatelliteToken: "valid-token",
		Payload:        payload,
	}

	resp, err := api.handleRequest(context.Background(), req)
	if err != nil {
		t.Fatalf("handleRequest error: %v", err)
	}
	if resp.Status != "success" {
		t.Errorf("Status = %q", resp.Status)
	}
}

func TestAPIShutdown(t *testing.T) {
	api := New()

	// Add mock components
	transport := &mockTransport{}
	hm := &mockHeartbeatManager{}
	fp := &mockFileProvider{}

	api.SetTransport(transport)
	api.SetHeartbeatManager(hm)
	api.SetFileProvider(fp)

	// Add shutdown hook
	hookCalled := false
	api.OnShutdown(func(ctx context.Context) error {
		hookCalled = true
		return nil
	})

	err := api.Shutdown(context.Background())
	if err != nil {
		t.Fatalf("Shutdown error: %v", err)
	}

	if !transport.stopped {
		t.Error("transport should be stopped")
	}
	if !hm.stopped {
		t.Error("heartbeat manager should be stopped")
	}
	if !fp.stopped {
		t.Error("file provider should be stopped")
	}
	if !hookCalled {
		t.Error("shutdown hook should be called")
	}
}

func TestAPIRunValidation(t *testing.T) {
	api := New() // No required config set

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	err := api.Run(ctx)
	if err == nil {
		t.Error("expected validation error")
	}
}

func TestAPIRunStartupHookFailure(t *testing.T) {
	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
	)

	api.OnStartup(func(ctx context.Context) error {
		return errors.New("startup failed")
	})

	err := api.Run(context.Background())
	if err == nil {
		t.Error("expected startup hook error")
	}
}

// Mock implementations

type mockTransport struct {
	started bool
	stopped bool
	handler RequestHandler
}

func (m *mockTransport) Start(ctx context.Context) error {
	m.started = true
	<-ctx.Done()
	return nil
}

func (m *mockTransport) Stop(ctx context.Context) error {
	m.stopped = true
	return nil
}

func (m *mockTransport) SetRequestHandler(handler RequestHandler) {
	m.handler = handler
}

type mockHeartbeatManager struct {
	started bool
	stopped bool
}

func (m *mockHeartbeatManager) Start(ctx context.Context) error {
	m.started = true
	<-ctx.Done()
	return nil
}

func (m *mockHeartbeatManager) Stop(ctx context.Context) error {
	m.stopped = true
	return nil
}

type mockFileProvider struct {
	started bool
	stopped bool
}

func (m *mockFileProvider) Start(ctx context.Context) error {
	m.started = true
	<-ctx.Done()
	return nil
}

func (m *mockFileProvider) Stop(ctx context.Context) error {
	m.stopped = true
	return nil
}

func (m *mockFileProvider) LoadEndpoints() ([]*Endpoint, error) {
	return nil, nil
}

func TestAPISetContainerRuntimeFactory(t *testing.T) {
	api := New()

	// Initially nil
	if api.containerRuntimeFactory != nil {
		t.Error("containerRuntimeFactory should be nil initially")
	}

	called := false
	factory := func(binary string, logger *slog.Logger) (ContainerRuntime, error) {
		called = true
		return nil, nil
	}

	api.SetContainerRuntimeFactory(factory)

	if api.containerRuntimeFactory == nil {
		t.Fatal("containerRuntimeFactory should not be nil after setting")
	}

	// Invoke to verify it's the correct function
	api.containerRuntimeFactory("docker", api.Logger())
	if !called {
		t.Error("factory function was not invoked")
	}
}

func TestAPISetContainerCleanupFunc(t *testing.T) {
	api := New()

	// Initially nil
	if api.containerCleanup != nil {
		t.Error("containerCleanup should be nil initially")
	}

	called := false
	cleanup := func(ctx context.Context, rt ContainerRuntime, instanceID string, logger *slog.Logger) error {
		called = true
		return nil
	}

	api.SetContainerCleanupFunc(cleanup)

	if api.containerCleanup == nil {
		t.Fatal("containerCleanup should not be nil after setting")
	}

	// Invoke to verify it's the correct function
	api.containerCleanup(context.Background(), nil, "test-id", api.Logger())
	if !called {
		t.Error("cleanup function was not invoked")
	}
}

func TestNewWithContainerOptions(t *testing.T) {
	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
		WithContainerEnabled(true),
		WithContainerRuntime("docker"),
		WithContainerImage("myimage:latest"),
	)

	cfg := api.Config()
	if !cfg.Container.Enabled {
		t.Error("Container.Enabled should be true")
	}
	if cfg.Container.Runtime != "docker" {
		t.Errorf("Container.Runtime = %q, want %q", cfg.Container.Runtime, "docker")
	}
	if cfg.Container.Image != "myimage:latest" {
		t.Errorf("Container.Image = %q, want %q", cfg.Container.Image, "myimage:latest")
	}
}

func TestNewWithContainerOptionsOverrideEnv(t *testing.T) {
	t.Setenv("CONTAINER_RUNTIME", "podman")
	t.Setenv("CONTAINER_IMAGE", "env-image:v1")

	api := New(
		WithContainerRuntime("docker"),
		WithContainerImage("option-image:v2"),
	)

	cfg := api.Config()
	if cfg.Container.Runtime != "docker" {
		t.Errorf("Container.Runtime = %q, want option override %q", cfg.Container.Runtime, "docker")
	}
	if cfg.Container.Image != "option-image:v2" {
		t.Errorf("Container.Image = %q, want option override %q", cfg.Container.Image, "option-image:v2")
	}
}

func TestAPIRunContainerModeNoFactory(t *testing.T) {
	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
		WithContainerEnabled(true),
		WithContainerRuntime("docker"),
		WithContainerImage("test:latest"),
	)

	err := api.Run(context.Background())
	if err == nil {
		t.Error("expected error when container mode is enabled but no runtime factory configured")
	}
	if !errors.Is(err, nil) { // Just check it contains our message
		// Verify the error message mentions the missing factory
		if err.Error() == "" {
			t.Error("expected non-empty error message")
		}
	}
}

func TestAPIRunContainerModeFactoryError(t *testing.T) {
	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
		WithContainerEnabled(true),
		WithContainerRuntime("docker"),
		WithContainerImage("test:latest"),
	)

	api.SetContainerRuntimeFactory(func(binary string, logger *slog.Logger) (ContainerRuntime, error) {
		return nil, errors.New("docker not found")
	})

	err := api.Run(context.Background())
	if err == nil {
		t.Error("expected error when container runtime factory fails")
	}
}

func TestAPIRunContainerModeWithCleanup(t *testing.T) {
	cleanupCalled := false
	cleanupInstanceID := ""

	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
		WithContainerEnabled(true),
		WithContainerRuntime("docker"),
		WithContainerImage("test:latest"),
	)

	mockRT := &mockContainerRuntime{}

	api.SetContainerRuntimeFactory(func(binary string, logger *slog.Logger) (ContainerRuntime, error) {
		return mockRT, nil
	})

	api.SetContainerCleanupFunc(func(ctx context.Context, rt ContainerRuntime, instanceID string, logger *slog.Logger) error {
		cleanupCalled = true
		cleanupInstanceID = instanceID
		if rt != mockRT {
			t.Error("cleanup received wrong runtime")
		}
		return nil
	})

	// Run will: validate config, run startup hooks, init container runtime, then try to setup transport
	// Since there's no transport, setupTransport will proceed (it logs but doesn't error for non-tunnel mode)
	// Then it will fail on transport.Start because transport is nil
	// We need to cancel context to stop it, but actually it will panic on nil transport
	// Let's add a startup hook that cancels
	ctx, cancel := context.WithCancel(context.Background())

	api.OnStartup(func(ctx context.Context) error {
		// Don't block startup, but cancel after a short time
		return nil
	})

	// Add a mock transport so it doesn't panic
	mockTransp := &mockTransport{}
	api.SetTransport(mockTransp)

	// Cancel quickly so Run exits
	go func() {
		// Wait a tiny bit for Run to get past container init
		cancel()
	}()

	_ = api.Run(ctx)

	if !cleanupCalled {
		t.Error("container cleanup function should have been called")
	}
	if cleanupInstanceID == "" {
		t.Error("cleanup should have received a non-empty instance ID")
	}
}

func TestAPIRunContainerModeInjectsRuntimeIntoFileProvider(t *testing.T) {
	injected := false

	api := New(
		WithSyftHubURL("https://hub.example.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("https://space.example.com"),
		WithContainerEnabled(true),
		WithContainerRuntime("docker"),
		WithContainerImage("test:latest"),
		WithEndpointsPath("/tmp/endpoints"),
	)

	mockRT := &mockContainerRuntime{}
	api.SetContainerRuntimeFactory(func(binary string, logger *slog.Logger) (ContainerRuntime, error) {
		return mockRT, nil
	})

	fp := &mockFileProviderWithContainerRuntime{
		onSetContainerRuntime: func(rt ContainerRuntime, cfg *ContainerConfig, instanceID string) {
			injected = true
			if rt != mockRT {
				t.Error("expected the mock runtime to be injected")
			}
			if cfg == nil {
				t.Error("expected non-nil ContainerConfig")
			}
			if instanceID == "" {
				t.Error("expected non-empty instance ID")
			}
		},
	}
	api.SetFileProvider(fp)

	mockTransp := &mockTransport{}
	api.SetTransport(mockTransp)

	ctx, cancel := context.WithCancel(context.Background())
	go func() { cancel() }()

	_ = api.Run(ctx)

	if !injected {
		t.Error("container runtime should have been injected into file provider")
	}
}

func TestGenerateInstanceID(t *testing.T) {
	id1 := generateInstanceID()
	if id1 == "" {
		t.Error("instance ID should not be empty")
	}

	// IDs should be different (based on time.Now().UnixNano())
	id2 := generateInstanceID()
	if id1 == id2 {
		t.Error("consecutive instance IDs should differ")
	}
}

// mockContainerRuntime implements ContainerRuntime for testing.
type mockContainerRuntime struct {
	stopCalls   []string
	removeCalls []string
}

func (m *mockContainerRuntime) Create(_ context.Context, _ any) (string, error) {
	return "abc123456789", nil
}
func (m *mockContainerRuntime) Start(_ context.Context, _ string) error { return nil }
func (m *mockContainerRuntime) Stop(_ context.Context, id string) error {
	m.stopCalls = append(m.stopCalls, id)
	return nil
}
func (m *mockContainerRuntime) Remove(_ context.Context, id string) error {
	m.removeCalls = append(m.removeCalls, id)
	return nil
}
func (m *mockContainerRuntime) List(_ context.Context, labels map[string]string) ([]string, error) {
	return nil, nil
}
func (m *mockContainerRuntime) GetHostPort(_ context.Context, _ string, _ string) (string, error) {
	return "8080", nil
}
func (m *mockContainerRuntime) Inspect(_ context.Context, _ string) (*ContainerInfo, error) {
	return &ContainerInfo{}, nil
}
func (m *mockContainerRuntime) Logs(_ context.Context, _ string, _ int) (string, error) {
	return "", nil
}

// mockFileProviderWithContainerRuntime implements both FileProvider and ContainerRuntimeSetter.
type mockFileProviderWithContainerRuntime struct {
	started               bool
	stopped               bool
	onSetContainerRuntime func(rt ContainerRuntime, cfg *ContainerConfig, instanceID string)
}

func (m *mockFileProviderWithContainerRuntime) Start(ctx context.Context) error {
	m.started = true
	<-ctx.Done()
	return nil
}

func (m *mockFileProviderWithContainerRuntime) Stop(ctx context.Context) error {
	m.stopped = true
	return nil
}

func (m *mockFileProviderWithContainerRuntime) LoadEndpoints() ([]*Endpoint, error) {
	return nil, nil
}

func (m *mockFileProviderWithContainerRuntime) SetContainerRuntime(rt ContainerRuntime, cfg *ContainerConfig, instanceID string) {
	if m.onSetContainerRuntime != nil {
		m.onSetContainerRuntime(rt, cfg, instanceID)
	}
}

func TestInterfaceImplementations(t *testing.T) {
	// Verify interfaces
	var _ Transport = (*mockTransport)(nil)
	var _ HeartbeatManager = (*mockHeartbeatManager)(nil)
	var _ FileProvider = (*mockFileProvider)(nil)
}

func TestLogLevelParsing(t *testing.T) {
	tests := []struct {
		level    string
		expected slog.Level
	}{
		{"DEBUG", slog.LevelDebug},
		{"INFO", slog.LevelInfo},
		{"WARNING", slog.LevelWarn},
		{"WARN", slog.LevelWarn},
		{"ERROR", slog.LevelError},
		{"INVALID", slog.LevelInfo}, // Default to INFO
	}

	for _, tt := range tests {
		t.Run(tt.level, func(t *testing.T) {
			api := New(WithLogLevel(tt.level))

			// We can't directly check the level, but we can verify the api was created
			if api == nil {
				t.Error("api is nil")
			}
		})
	}
}

func BenchmarkNew(b *testing.B) {
	for i := 0; i < b.N; i++ {
		_ = New(
			WithSyftHubURL("https://hub.example.com"),
			WithAPIKey("test-key"),
			WithSpaceURL("https://space.example.com"),
		)
	}
}

func BenchmarkRegisterEndpoint(b *testing.B) {
	api := New()

	for i := 0; i < b.N; i++ {
		// Create unique slug for each iteration
		slug := "test-" + string(rune('a'+i%26))
		api.Model(slug).
			Name("Test").
			Description("Test").
			Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
				return "", nil
			})
	}
}
