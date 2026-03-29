package containermode

import (
	"encoding/json"
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

	spec := BuildEndpointSpec("my-model", "/path/to/endpoint", cfg, nil, []string{"KEY=value"}, "abc12345")

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

func TestBuildEndpointSpec_WithOverrides(t *testing.T) {
	cfg := syfthubapi.ContainerConfig{
		Image:    "default:latest",
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}
	overrides := &ContainerOverrides{
		Image:    "custom:v2",
		CPUs:     4.0,
		MemoryMB: 2048,
		GPU:      "all",
	}

	spec := BuildEndpointSpec("gpu-model", "/path", cfg, overrides, nil, "xyz")

	if spec.Image != "custom:v2" {
		t.Errorf("override not applied for image: %s", spec.Image)
	}
	if spec.CPUs != 4.0 {
		t.Errorf("override not applied for CPUs: %f", spec.CPUs)
	}
	if spec.MemoryMB != 2048 {
		t.Errorf("override not applied for memory: %d", spec.MemoryMB)
	}
	if spec.GPU != "all" {
		t.Errorf("override not applied for GPU: %s", spec.GPU)
	}
	// Network should fall through to global default since override is empty
	if spec.Network != "bridge" {
		t.Errorf("expected global default network, got: %s", spec.Network)
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
