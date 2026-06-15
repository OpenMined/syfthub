package containermode

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "my-model",
		SynthCodeDir: "/path/to/endpoint",
		Global:       cfg,
		EnvVars:      []string{"KEY=value"},
		InstanceID:   "abc12345",
		Image:        cfg.Image,
	})

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

	// Check mounts: volumes first, then RO bind of synth dir.
	if len(spec.Mounts) != 3 {
		t.Fatalf("expected 3 mounts, got %d", len(spec.Mounts))
	}
	var synth *Mount
	for i := range spec.Mounts {
		if spec.Mounts[i].Target == "/app/synth" {
			synth = &spec.Mounts[i]
			break
		}
	}
	if synth == nil {
		t.Fatal("expected /app/synth mount")
	}
	if !synth.ReadOnly {
		t.Error("expected /app/synth to be read-only")
	}
	if synth.Type != "bind" {
		t.Errorf("expected /app/synth to be a bind mount, got %q", synth.Type)
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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "test-endpoint",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "instance-42",
		Image:        cfg.Image,
	})

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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "secure-ep",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "sec-id",
		Image:        cfg.Image,
	})

	if spec.User != "1000:1000" {
		t.Errorf("User = %q, want %q", spec.User, "1000:1000")
	}
	if !spec.ReadOnlyFS {
		t.Error("expected ReadOnlyFS = true")
	}
	if len(spec.CapDrop) != 1 || spec.CapDrop[0] != "ALL" {
		t.Errorf("CapDrop = %v, want [ALL]", spec.CapDrop)
	}
	// Spec must include no-new-privileges, seccomp=unconfined, and
	// apparmor=unconfined. seccomp+apparmor are required so the
	// in-container bwrap can create a user namespace and remount /
	// slave; Docker's default profiles block both. Defense-in-depth
	// still holds via cap_drop ALL + read-only FS + non-root user +
	// the in-bwrap audit hook.
	gotOpts := map[string]bool{}
	for _, o := range spec.SecurityOpts {
		gotOpts[o] = true
	}
	for _, want := range []string{
		"no-new-privileges",
		"seccomp=unconfined",
		"apparmor=unconfined",
	} {
		if !gotOpts[want] {
			t.Errorf("SecurityOpts missing %q; got %v", want, spec.SecurityOpts)
		}
	}
}

func TestBuildEndpointSpec_MountPaths(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "my-ds",
		SynthCodeDir: "/home/user/endpoints/my-ds",
		Global:       cfg,
		InstanceID:   "mount-id",
		Image:        cfg.Image,
	})

	if len(spec.Mounts) != 3 {
		t.Fatalf("expected 3 mounts, got %d", len(spec.Mounts))
	}

	// Index mounts by target so tests don't depend on order.
	byTarget := map[string]Mount{}
	for _, m := range spec.Mounts {
		byTarget[m.Target] = m
	}

	synth, ok := byTarget["/app/synth"]
	if !ok {
		t.Fatal("expected /app/synth mount")
	}
	if synth.Type != "bind" {
		t.Errorf("/app/synth Type = %q, want bind", synth.Type)
	}
	if synth.Source != "/home/user/endpoints/my-ds" {
		t.Errorf("/app/synth Source = %q", synth.Source)
	}
	if !synth.ReadOnly {
		t.Error("/app/synth should be read-only")
	}

	cache, ok := byTarget["/app/.cache"]
	if !ok {
		t.Fatal("expected /app/.cache mount")
	}
	if cache.Type != "volume" {
		t.Errorf("/app/.cache Type = %q, want volume", cache.Type)
	}
	if cache.Source != "syfthub-my-ds-pip-cache" {
		t.Errorf("/app/.cache Source = %q", cache.Source)
	}

	store, ok := byTarget["/app/.store"]
	if !ok {
		t.Fatal("expected /app/.store mount")
	}
	if store.Type != "volume" {
		t.Errorf("/app/.store Type = %q, want volume", store.Type)
	}
	if store.Source != "syfthub-my-ds-policy-store" {
		t.Errorf("/app/.store Source = %q", store.Source)
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
	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "my-model",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		EnvVars:      envVars,
		InstanceID:   "env-id",
		Image:        cfg.Image,
	})

	// BuildEndpointSpec passes EnvVars through verbatim, optionally appending
	// _SYFT_HANDLER_ENV when HandlerEnvKeys is non-empty. With no
	// HandlerEnvKeys (this test) Env should equal EnvVars exactly.
	if len(spec.Env) != 3 {
		t.Fatalf("expected 3 env vars, got %d (%v)", len(spec.Env), spec.Env)
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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "my-model",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "nil-env-id",
		Image:        cfg.Image,
	})

	// With no EnvVars and no HandlerEnvKeys, the resulting Env may be an
	// empty (non-nil) slice — the implementation pre-allocates. Either
	// nil or [] is acceptable.
	if len(spec.Env) != 0 {
		t.Errorf("expected empty Env, got %v", spec.Env)
	}
}

func TestBuildEndpointSpec_PortMapping(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "port-test",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "port-id",
		Image:        cfg.Image,
	})

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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "gpu-global",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "gpu-id",
		Image:        cfg.Image,
	})

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

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "tmpfs-test",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "tmp-id",
		Image:        cfg.Image,
	})

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
		spec := BuildEndpointSpec(EndpointSpecConfig{
			Slug:         tt.slug,
			SynthCodeDir: "/tmp/ep",
			Global:       cfg,
			InstanceID:   tt.instanceID,
			Image:        cfg.Image,
		})
		if spec.Name != tt.wantName {
			t.Errorf("slug=%q, instanceID=%q: Name = %q, want %q", tt.slug, tt.instanceID, spec.Name, tt.wantName)
		}
	}
}

func TestBuildEndpointSpec_CustomImage(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "syfthub/endpoint-runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	customImage := "myorg/custom-runner:v2"
	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "custom-ep",
		SynthCodeDir: "/tmp/ep",
		Global:       cfg,
		InstanceID:   "test-id",
		Image:        customImage,
	})

	if spec.Image != customImage {
		t.Errorf("Image = %q, want %q", spec.Image, customImage)
	}
	// Verify other fields still come from global config
	if spec.CPUs != 1.0 {
		t.Errorf("CPUs = %f, want 1.0", spec.CPUs)
	}
	if spec.MemoryMB != 512 {
		t.Errorf("MemoryMB = %d, want 512", spec.MemoryMB)
	}
}

func TestBuildEndpointSpec_HandlerEnvAllowlist(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "runner:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:           "policy-aware",
		SynthCodeDir:   "/tmp/synth",
		Global:         cfg,
		EnvVars:        []string{"OPENAI_API_KEY=sk-x", "BILLING_TOKEN=tok", "LOG_LEVEL=INFO"},
		HandlerEnvKeys: []string{"OPENAI_API_KEY", "LOG_LEVEL"},
		InstanceID:     "h1",
		Image:          cfg.Image,
	})

	var found bool
	for _, kv := range spec.Env {
		if kv == SyftHandlerEnvEnv+"=OPENAI_API_KEY,LOG_LEVEL" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected %s=OPENAI_API_KEY,LOG_LEVEL in Env, got %v",
			SyftHandlerEnvEnv, spec.Env)
	}
}

func TestBuildEndpointSpec_WorkspacePool(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{Image: "runner:latest", Network: "bridge"}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:             "ws-test",
		SynthCodeDir:     "/tmp/synth",
		WorkspacePoolDir: "/host/workspaces/ws-test",
		Global:           cfg,
		InstanceID:       "w1",
		Image:            cfg.Image,
	})

	var ws *Mount
	for i := range spec.Mounts {
		if spec.Mounts[i].Target == "/app/ws" {
			ws = &spec.Mounts[i]
			break
		}
	}
	if ws == nil {
		t.Fatal("expected /app/ws bind mount")
	}
	if ws.ReadOnly {
		t.Error("/app/ws must be read-write")
	}
	if ws.Source != "/host/workspaces/ws-test" {
		t.Errorf("/app/ws Source = %q", ws.Source)
	}
}

func TestBuildEndpointSpec_NoRawEndpointDirMount(t *testing.T) {
	// The whole point of the synth-dir refactor: /app/endpoint must NEVER
	// appear in the mount list. Regression guard.
	cfg := syfthubapi.ContainerConfig{Image: "runner:latest", Network: "bridge"}
	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "no-raw",
		SynthCodeDir: "/tmp/synth",
		Global:       cfg,
		InstanceID:   "r1",
		Image:        cfg.Image,
	})
	for _, m := range spec.Mounts {
		if m.Target == "/app/endpoint" {
			t.Errorf("/app/endpoint must not be mounted (raw endpoint dir leaks secrets); got %+v", m)
		}
	}
}

func TestBuildEndpointSpec_SandboxControlEnv(t *testing.T) {
	// WorkspaceScope + SandboxNetMode must surface as container env vars
	// so server.py picks them up at startup.
	cfg := syfthubapi.ContainerConfig{Image: "runner:latest", Network: "bridge"}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "control-env",
		SynthCodeDir: "/tmp/synth",
		Global:       cfg,
		InstanceID:   "c1",
		Image:        cfg.Image,
		Sandbox: SandboxRuntimeConfig{
			WorkspaceScope: WorkspaceScopePerSession,
			NetMode:        SandboxNetAllowlist,
		},
	})

	want := map[string]string{
		SyftWorkspaceScopeEnv: "per_session",
		SyftSandboxNetEnv:     "allowlist",
	}
	got := map[string]string{}
	for _, kv := range spec.Env {
		if k, v, ok := strings.Cut(kv, "="); ok {
			got[k] = v
		}
	}
	for k, v := range want {
		if got[k] != v {
			t.Errorf("env %s = %q, want %q", k, got[k], v)
		}
	}
}

func TestBuildEndpointSpec_NetworkOverride(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{Image: "runner:latest", Network: "bridge"}

	spec := BuildEndpointSpec(EndpointSpecConfig{
		Slug:         "no-net",
		SynthCodeDir: "/tmp/synth",
		Global:       cfg,
		NetworkMode:  "none",
		InstanceID:   "n1",
		Image:        cfg.Image,
	})
	if spec.Network != "none" {
		t.Errorf("NetworkMode override ignored: got %q, want none", spec.Network)
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
