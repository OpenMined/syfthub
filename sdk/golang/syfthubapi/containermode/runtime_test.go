package containermode

import (
	"context"
	"strings"
	"testing"
)

func TestBuildRunArgs_BasicSpec(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Name:  "test-container",
		Image: "python:3.11-slim",
		Env:   []string{"FOO=bar", "BAZ=qux"},
		Labels: map[string]string{
			"app": "test",
		},
		Ports: []PortMapping{{HostPort: "0", ContainerPort: "8080"}},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "run -d") {
		t.Error("expected 'run -d'")
	}
	if !strings.Contains(joined, "--name test-container") {
		t.Error("expected --name")
	}
	if !strings.Contains(joined, "-e FOO=bar") {
		t.Error("expected env FOO=bar")
	}
	if !strings.Contains(joined, "-p 0:8080") {
		t.Error("expected port mapping")
	}
	if !strings.Contains(joined, "python:3.11-slim") {
		t.Error("expected image at end")
	}
}

func TestBuildRunArgs_SecurityOptions(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image:        "test:latest",
		User:         "1000:1000",
		ReadOnlyFS:   true,
		CapDrop:      []string{"ALL"},
		SecurityOpts: []string{"no-new-privileges"},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--user 1000:1000") {
		t.Error("expected --user")
	}
	if !strings.Contains(joined, "--read-only") {
		t.Error("expected --read-only")
	}
	if !strings.Contains(joined, "--cap-drop ALL") {
		t.Error("expected --cap-drop ALL")
	}
	if !strings.Contains(joined, "--security-opt no-new-privileges") {
		t.Error("expected --security-opt")
	}
}

func TestBuildRunArgs_DockerGPU(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
		GPU:   "all",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--gpus all") {
		t.Errorf("expected --gpus all for docker, got: %s", joined)
	}
}

func TestBuildRunArgs_PodmanGPU(t *testing.T) {
	rt := &CLIRuntime{binary: "podman"}
	spec := &ContainerSpec{
		Image: "test:latest",
		GPU:   "all",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--device nvidia.com/gpu=all") {
		t.Errorf("expected --device for podman, got: %s", joined)
	}
}

func TestBuildRunArgs_Mounts(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
		Mounts: []Mount{
			{Type: "bind", Source: "/host/path", Target: "/container/path", ReadOnly: true},
			{Type: "volume", Source: "my-vol", Target: "/data"},
		},
		Tmpfs: []string{"/tmp"},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "-v /host/path:/container/path:ro") {
		t.Error("expected read-only bind mount")
	}
	if !strings.Contains(joined, "-v my-vol:/data") {
		t.Error("expected volume mount")
	}
	if !strings.Contains(joined, "--tmpfs /tmp") {
		t.Error("expected tmpfs")
	}
}

func TestBuildRunArgs_Resources(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image:    "test:latest",
		CPUs:     2.5,
		MemoryMB: 1024,
		Network:  "host",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--cpus 2.5") {
		t.Error("expected --cpus")
	}
	if !strings.Contains(joined, "--memory 1024m") {
		t.Error("expected --memory")
	}
	if !strings.Contains(joined, "--network host") {
		t.Error("expected --network")
	}
}

func TestBuildRunArgs_NoNameWhenEmpty(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if strings.Contains(joined, "--name") {
		t.Error("should not include --name when Name is empty")
	}
}

func TestBuildRunArgs_NoResourcesWhenZero(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image:    "test:latest",
		CPUs:     0,
		MemoryMB: 0,
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if strings.Contains(joined, "--cpus") {
		t.Error("should not include --cpus when CPUs is 0")
	}
	if strings.Contains(joined, "--memory") {
		t.Error("should not include --memory when MemoryMB is 0")
	}
}

func TestBuildRunArgs_NoGPUWhenEmpty(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
		GPU:   "",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if strings.Contains(joined, "--gpus") || strings.Contains(joined, "--device nvidia") {
		t.Error("should not include GPU flag when GPU is empty")
	}
}

func TestBuildRunArgs_NoNetworkWhenEmpty(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image:   "test:latest",
		Network: "",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if strings.Contains(joined, "--network") {
		t.Error("should not include --network when Network is empty")
	}
}

func TestBuildRunArgs_CommandArgs(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "python:3.11",
		Cmd:   []string{"python", "-m", "runner"},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	// Image should come before command
	imageIdx := strings.Index(joined, "python:3.11")
	cmdIdx := strings.Index(joined, "python -m runner")
	if imageIdx < 0 || cmdIdx < 0 {
		t.Fatalf("expected image and cmd in args, got: %s", joined)
	}
	if cmdIdx <= imageIdx {
		t.Error("command should come after image")
	}
}

func TestBuildRunArgs_MultipleLabels(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
		Labels: map[string]string{
			"syfthub.managed":  "true",
			"syfthub.instance": "abc123",
			"syfthub.endpoint": "my-model",
		},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--label syfthub.managed=true") {
		t.Error("expected managed label")
	}
	if !strings.Contains(joined, "--label syfthub.instance=abc123") {
		t.Error("expected instance label")
	}
	if !strings.Contains(joined, "--label syfthub.endpoint=my-model") {
		t.Error("expected endpoint label")
	}
}

func TestBuildRunArgs_MultiplePortMappings(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Image: "test:latest",
		Ports: []PortMapping{
			{HostPort: "0", ContainerPort: "8080"},
			{HostPort: "9090", ContainerPort: "9090"},
		},
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "-p 0:8080") {
		t.Error("expected first port mapping")
	}
	if !strings.Contains(joined, "-p 9090:9090") {
		t.Error("expected second port mapping")
	}
}

func TestBuildRunArgs_PodmanGPUDeviceSpec(t *testing.T) {
	rt := &CLIRuntime{binary: "podman"}
	spec := &ContainerSpec{
		Image: "test:latest",
		GPU:   "device=0",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "--device nvidia.com/gpu=device=0") {
		t.Errorf("expected podman --device format, got: %s", joined)
	}
}

func TestBuildRunArgs_FullSpec(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}
	spec := &ContainerSpec{
		Name:         "syfthub-my-model-abc123",
		Image:        "syfthub/endpoint-runner:latest",
		User:         "1000:1000",
		ReadOnlyFS:   true,
		CapDrop:      []string{"ALL"},
		SecurityOpts: []string{"no-new-privileges"},
		Env:          []string{"SYFTHUB_API_KEY=secret", "LOG_LEVEL=DEBUG"},
		Labels:       map[string]string{"syfthub.managed": "true", "syfthub.instance": "abc123"},
		Mounts: []Mount{
			{Type: "bind", Source: "/app/endpoint", Target: "/app/endpoint", ReadOnly: true},
		},
		Tmpfs:    []string{"/tmp"},
		Ports:    []PortMapping{{HostPort: "0", ContainerPort: "8080"}},
		CPUs:     1.0,
		MemoryMB: 512,
		Network:  "bridge",
	}

	args := rt.buildRunArgs(spec)
	joined := strings.Join(args, " ")

	expected := []string{
		"run -d",
		"--name syfthub-my-model-abc123",
		"--user 1000:1000",
		"--read-only",
		"--cap-drop ALL",
		"--security-opt no-new-privileges",
		"-e SYFTHUB_API_KEY=secret",
		"-e LOG_LEVEL=DEBUG",
		"--tmpfs /tmp",
		"--cpus 1.0",
		"--memory 512m",
		"--network bridge",
		"-p 0:8080",
		"syfthub/endpoint-runner:latest",
	}

	for _, exp := range expected {
		if !strings.Contains(joined, exp) {
			t.Errorf("expected %q in args, got: %s", exp, joined)
		}
	}
}

func TestCLIRuntime_CreateRejectsBadSpecType(t *testing.T) {
	rt := &CLIRuntime{binary: "docker"}

	_, err := rt.Create(context.Background(), "not-a-spec")
	if err == nil {
		t.Fatal("expected error for non-*ContainerSpec argument")
	}
	if !strings.Contains(err.Error(), "expected *ContainerSpec") {
		t.Errorf("error message should mention expected type, got: %v", err)
	}
}

func TestContainerOverrides_Fields(t *testing.T) {
	o := ContainerOverrides{
		Image:    "custom:v3",
		CPUs:     8.0,
		MemoryMB: 4096,
		GPU:      "device=1",
		Network:  "host",
	}

	if o.Image != "custom:v3" {
		t.Errorf("Image = %q", o.Image)
	}
	if o.CPUs != 8.0 {
		t.Errorf("CPUs = %f", o.CPUs)
	}
	if o.MemoryMB != 4096 {
		t.Errorf("MemoryMB = %d", o.MemoryMB)
	}
	if o.GPU != "device=1" {
		t.Errorf("GPU = %q", o.GPU)
	}
	if o.Network != "host" {
		t.Errorf("Network = %q", o.Network)
	}
}
