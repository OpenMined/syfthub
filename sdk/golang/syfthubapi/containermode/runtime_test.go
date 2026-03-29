package containermode

import (
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
