package containermode

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestBuildEndpointSpec_Defaults(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "syfthub/endpoint-runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("my-model", "/path/to/endpoint", cfg, []string{"KEY=value"}, "abc12345")

	if spec.Name != "syfthub-my-model-abc12345" {
		t.Errorf("unexpected name: %s", spec.Name)
	}
	if spec.Image != "syfthub/endpoint-runner:latest" {
		t.Errorf("unexpected image: %s", spec.Image)
	}
	if spec.User != "1000:1000" {
		t.Errorf("unexpected user: %s", spec.User)
	}
	if !spec.ReadOnlyFS {
		t.Error("expected read-only filesystem")
	}
	if len(spec.CapDrop) != 1 || spec.CapDrop[0] != "ALL" {
		t.Errorf("unexpected cap drop: %v", spec.CapDrop)
	}
	if spec.CPUs != 1.0 {
		t.Errorf("unexpected CPUs: %f", spec.CPUs)
	}
	if spec.MemoryMB != 512 {
		t.Errorf("unexpected memory: %d", spec.MemoryMB)
	}
	if spec.Labels["syfthub.managed"] != "true" {
		t.Error("expected managed label")
	}
	if spec.Labels["syfthub.instance"] != "abc12345" {
		t.Error("expected instance label")
	}

	// Check mounts
	if len(spec.Mounts) != 3 {
		t.Fatalf("expected 3 mounts, got %d", len(spec.Mounts))
	}
	if spec.Mounts[0].Target != "/app/endpoint" || !spec.Mounts[0].ReadOnly {
		t.Error("expected read-only /app/endpoint bind mount")
	}
}

func TestContainerExecutor_ExecuteRoundTrip(t *testing.T) {
	// Create a mock container HTTP server
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/execute" {
			w.WriteHeader(http.StatusNotFound)
			return
		}

		output := syfthubapi.ExecutorOutput{
			Success: true,
			Result:  json.RawMessage(`"hello world"`),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(output)
	}))
	defer srv.Close()

	// Create executor pointing at our test server (bypass container creation)
	executor := &ContainerExecutor{
		baseURL:     srv.URL,
		containerID: "test1234567890",
		httpClient:  http.DefaultClient,
	}

	input := &syfthubapi.ExecutorInput{
		Type: "model",
	}
	output, err := executor.Execute(t.Context(), input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !output.Success {
		t.Error("expected success=true")
	}
}

func TestContainerExecutor_ClosedRejectsExecute(t *testing.T) {
	executor := &ContainerExecutor{
		baseURL:     "http://localhost:99999",
		containerID: "test1234567890",
		httpClient:  http.DefaultClient,
		closed:      true,
	}

	_, err := executor.Execute(t.Context(), &syfthubapi.ExecutorInput{})
	if err == nil {
		t.Fatal("expected error from closed executor")
	}
}

func TestBuildEndpointSpec_Labels(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("test-endpoint", "/tmp/ep", cfg, nil, "instance-42")

	expectedLabels := map[string]string{
		"syfthub.managed":  "true",
		"syfthub.instance": "instance-42",
		"syfthub.endpoint": "test-endpoint",
	}

	for key, want := range expectedLabels {
		got, ok := spec.Labels[key]
		if !ok {
			t.Errorf("missing label %q", key)
			continue
		}
		if got != want {
			t.Errorf("label %q = %q, want %q", key, got, want)
		}
	}
}

func TestBuildEndpointSpec_Security(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 256,
		Network:  "none",
	}

	spec := BuildEndpointSpec("secure-ep", "/tmp/ep", cfg, nil, "sec-id")

	if spec.User != "1000:1000" {
		t.Errorf("User = %q, want %q", spec.User, "1000:1000")
	}
	if !spec.ReadOnlyFS {
		t.Error("expected ReadOnlyFS = true")
	}
	if len(spec.CapDrop) != 1 || spec.CapDrop[0] != "ALL" {
		t.Errorf("CapDrop = %v, want [ALL]", spec.CapDrop)
	}
	if len(spec.SecurityOpts) != 1 || spec.SecurityOpts[0] != "no-new-privileges" {
		t.Errorf("SecurityOpts = %v, want [no-new-privileges]", spec.SecurityOpts)
	}
}

func TestBuildEndpointSpec_MountPaths(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("my-ds", "/home/user/endpoints/my-ds", cfg, nil, "mount-id")

	if len(spec.Mounts) != 3 {
		t.Fatalf("expected 3 mounts, got %d", len(spec.Mounts))
	}

	// First mount: endpoint directory (read-only bind)
	m0 := spec.Mounts[0]
	if m0.Type != "bind" {
		t.Errorf("mount[0].Type = %q, want bind", m0.Type)
	}
	if m0.Source != "/home/user/endpoints/my-ds" {
		t.Errorf("mount[0].Source = %q", m0.Source)
	}
	if m0.Target != "/app/endpoint" {
		t.Errorf("mount[0].Target = %q", m0.Target)
	}
	if !m0.ReadOnly {
		t.Error("mount[0] should be read-only")
	}

	// Second mount: pip cache (volume)
	m1 := spec.Mounts[1]
	if m1.Type != "volume" {
		t.Errorf("mount[1].Type = %q, want volume", m1.Type)
	}
	if m1.Source != "syfthub-my-ds-pip-cache" {
		t.Errorf("mount[1].Source = %q, want syfthub-my-ds-pip-cache", m1.Source)
	}

	// Third mount: policy store (volume)
	m2 := spec.Mounts[2]
	if m2.Type != "volume" {
		t.Errorf("mount[2].Type = %q, want volume", m2.Type)
	}
	if m2.Source != "syfthub-my-ds-policy-store" {
		t.Errorf("mount[2].Source = %q, want syfthub-my-ds-policy-store", m2.Source)
	}
}

func TestBuildEndpointSpec_EnvVars(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	envVars := []string{"API_KEY=test123", "LOG_LEVEL=DEBUG", "ENDPOINT_SLUG=my-model"}
	spec := BuildEndpointSpec("my-model", "/tmp/ep", cfg, envVars, "env-id")

	if len(spec.Env) != 3 {
		t.Fatalf("expected 3 env vars, got %d", len(spec.Env))
	}
	if spec.Env[0] != "API_KEY=test123" {
		t.Errorf("Env[0] = %q", spec.Env[0])
	}
	if spec.Env[1] != "LOG_LEVEL=DEBUG" {
		t.Errorf("Env[1] = %q", spec.Env[1])
	}
}

func TestBuildEndpointSpec_NilEnvVars(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("my-model", "/tmp/ep", cfg, nil, "nil-env-id")

	if spec.Env != nil {
		t.Errorf("expected nil Env, got %v", spec.Env)
	}
}

func TestBuildEndpointSpec_PortMapping(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("port-test", "/tmp/ep", cfg, nil, "port-id")

	if len(spec.Ports) != 1 {
		t.Fatalf("expected 1 port mapping, got %d", len(spec.Ports))
	}
	if spec.Ports[0].HostPort != "0" {
		t.Errorf("HostPort = %q, want %q (auto-assign)", spec.Ports[0].HostPort, "0")
	}
	if spec.Ports[0].ContainerPort != "8080" {
		t.Errorf("ContainerPort = %q, want %q", spec.Ports[0].ContainerPort, "8080")
	}
}

func TestBuildEndpointSpec_GPUFromGlobalConfig(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
		GPU:      "device=0",
	}

	spec := BuildEndpointSpec("gpu-global", "/tmp/ep", cfg, nil, "gpu-id")

	if spec.GPU != "device=0" {
		t.Errorf("GPU = %q, should use global config", spec.GPU)
	}
}

func TestBuildEndpointSpec_Tmpfs(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec("tmpfs-test", "/tmp/ep", cfg, nil, "tmp-id")

	if len(spec.Tmpfs) != 1 || spec.Tmpfs[0] != "/tmp" {
		t.Errorf("Tmpfs = %v, want [/tmp]", spec.Tmpfs)
	}
}

func TestBuildEndpointSpec_ContainerName(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	tests := []struct {
		slug       string
		instanceID string
		wantName   string
	}{
		{"my-model", "abc123", "syfthub-my-model-abc123"},
		{"data-source", "xyz789", "syfthub-data-source-xyz789"},
		{"a", "1", "syfthub-a-1"},
	}

	for _, tt := range tests {
		spec := BuildEndpointSpec(tt.slug, "/tmp/ep", cfg, nil, tt.instanceID)
		if spec.Name != tt.wantName {
			t.Errorf("slug=%q, instanceID=%q: Name = %q, want %q", tt.slug, tt.instanceID, spec.Name, tt.wantName)
		}
	}
}

func TestContainerExecutor_CloseIsIdempotent(t *testing.T) {
	rt := &idempotentMockRuntime{}
	executor := &ContainerExecutor{
		runtime:     rt,
		containerID: "test1234567890",
		baseURL:     "http://localhost:8080",
		httpClient:  http.DefaultClient,
		logger:      slog.Default(),
	}

	// First close
	err := executor.Close()
	if err != nil {
		t.Fatalf("first Close() error: %v", err)
	}

	// Second close should be a no-op
	err = executor.Close()
	if err != nil {
		t.Fatalf("second Close() error: %v", err)
	}

	if rt.stopCount != 1 {
		t.Errorf("expected 1 stop call, got %d", rt.stopCount)
	}
}

func TestContainerExecutor_BaseURL(t *testing.T) {
	executor := &ContainerExecutor{
		baseURL:     "http://localhost:12345",
		containerID: "test1234567890",
	}

	if executor.BaseURL() != "http://localhost:12345" {
		t.Errorf("BaseURL() = %q, want %q", executor.BaseURL(), "http://localhost:12345")
	}
}

type idempotentMockRuntime struct {
	stopCount int
}

func (m *idempotentMockRuntime) Create(_ context.Context, _ any) (string, error) { return "", nil }
func (m *idempotentMockRuntime) Start(_ context.Context, _ string) error         { return nil }
func (m *idempotentMockRuntime) Stop(_ context.Context, _ string) error {
	m.stopCount++
	return nil
}
func (m *idempotentMockRuntime) Remove(_ context.Context, _ string) error { return nil }
func (m *idempotentMockRuntime) List(_ context.Context, _ map[string]string) ([]string, error) {
	return nil, nil
}
func (m *idempotentMockRuntime) GetHostPort(_ context.Context, _ string, _ string) (string, error) {
	return "0", nil
}
func (m *idempotentMockRuntime) Inspect(_ context.Context, _ string) (*syfthubapi.ContainerInfo, error) {
	return &syfthubapi.ContainerInfo{}, nil
}
func (m *idempotentMockRuntime) Logs(_ context.Context, _ string, _ int) (string, error) {
	return "", nil
}
