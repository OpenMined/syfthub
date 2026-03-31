// Package containermode provides container-based endpoint execution using Docker or Podman.
package containermode

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"os/exec"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ContainerSpec defines the full specification for creating a container.
type ContainerSpec struct {
	Name         string
	Image        string
	Env          []string // KEY=VALUE format
	Labels       map[string]string
	Mounts       []Mount
	Ports        []PortMapping
	User         string
	ReadOnlyFS   bool
	CapDrop      []string
	SecurityOpts []string
	CPUs         float64
	MemoryMB     int
	Network      string
	GPU          string
	Tmpfs        []string
	Cmd          []string
}

// Mount represents a container mount.
type Mount struct {
	Type     string // "bind", "volume"
	Source   string
	Target   string
	ReadOnly bool
}

// PortMapping represents a container port mapping.
type PortMapping struct {
	HostPort      string // "0" for auto-assign
	ContainerPort string // e.g. "8080"
}

// ContainerOverrides allows per-endpoint customization of container resources.
type ContainerOverrides struct {
	Image    string  `yaml:"image,omitempty"`
	CPUs     float64 `yaml:"cpus,omitempty"`
	MemoryMB int     `yaml:"memory_mb,omitempty"`
	GPU      string  `yaml:"gpu,omitempty"`
	Network  string  `yaml:"network,omitempty"`
}

// CLIRuntime wraps a Docker or Podman CLI binary.
type CLIRuntime struct {
	binary string // "docker" or "podman"
	logger *slog.Logger
}

// NewCLIRuntime creates a CLIRuntime. If binary is "auto", it tries docker then podman.
func NewCLIRuntime(binary string, logger *slog.Logger) (syfthubapi.ContainerRuntime, error) {
	if binary == "auto" || binary == "" {
		resolved, err := detectRuntime()
		if err != nil {
			return nil, err
		}
		binary = resolved
	}

	rt := &CLIRuntime{binary: binary, logger: logger}
	if err := rt.RuntimeAvailable(context.Background()); err != nil {
		return nil, fmt.Errorf("container runtime %q not available: %w", binary, err)
	}

	logger.Info("container runtime detected", "binary", binary)
	return rt, nil
}

// detectRuntime tries docker then podman, returning the first available.
func detectRuntime() (string, error) {
	for _, bin := range []string{"docker", "podman"} {
		if _, err := exec.LookPath(bin); err == nil {
			return bin, nil
		}
	}
	return "", fmt.Errorf("no container runtime found: install docker or podman")
}

// Create creates and starts a container from the given spec. Satisfies syfthubapi.ContainerRuntime.
func (r *CLIRuntime) Create(ctx context.Context, spec any) (string, error) {
	cs, ok := spec.(*ContainerSpec)
	if !ok {
		return "", fmt.Errorf("expected *ContainerSpec, got %T", spec)
	}

	args := r.buildRunArgs(cs)
	out, err := r.execCommand(ctx, args...)
	if err != nil {
		return "", &syfthubapi.ContainerError{
			Operation: "create",
			Image:     cs.Image,
			Message:   "failed to create container",
			Cause:     err,
		}
	}

	containerID := strings.TrimSpace(out)
	r.logger.Info("container created", "id", containerID[:12], "name", cs.Name, "image", cs.Image)
	return containerID, nil
}

// Start starts a stopped container. Satisfies syfthubapi.ContainerRuntime.
func (r *CLIRuntime) Start(ctx context.Context, containerID string) error {
	_, err := r.execCommand(ctx, "start", containerID)
	return err
}

// Stop stops and removes a container. Satisfies syfthubapi.ContainerRuntime.
func (r *CLIRuntime) Stop(ctx context.Context, containerID string) error {
	// Stop with 10s grace period
	if _, err := r.execCommand(ctx, "stop", "-t", "10", containerID); err != nil {
		r.logger.Debug("stop returned error (may already be stopped)", "id", containerID[:12], "error", err)
	}
	// Force remove (best-effort)
	if _, err := r.execCommand(ctx, "rm", "-f", containerID); err != nil {
		r.logger.Debug("rm returned error", "id", containerID[:12], "error", err)
	}
	return nil
}

// Remove removes a container. Satisfies syfthubapi.ContainerRuntime.
func (r *CLIRuntime) Remove(ctx context.Context, containerID string) error {
	_, err := r.execCommand(ctx, "rm", "-f", containerID)
	return err
}

// List lists container IDs matching the given labels. Satisfies syfthubapi.ContainerRuntime.
func (r *CLIRuntime) List(ctx context.Context, labels map[string]string) ([]string, error) {
	args := []string{"ps", "-a", "-q"}
	for k, v := range labels {
		args = append(args, "--filter", fmt.Sprintf("label=%s=%s", k, v))
	}

	out, err := r.execCommand(ctx, args...)
	if err != nil {
		return nil, err
	}

	out = strings.TrimSpace(out)
	if out == "" {
		return nil, nil
	}
	return strings.Split(out, "\n"), nil
}

// GetHostPort returns the host port mapped to the given container port.
func (r *CLIRuntime) GetHostPort(ctx context.Context, containerID string, containerPort string) (string, error) {
	out, err := r.execCommand(ctx, "port", containerID, containerPort)
	if err != nil {
		return "", fmt.Errorf("failed to get port mapping: %w", err)
	}

	// Output format: "0.0.0.0:49152" or ":::49152" or "0.0.0.0:49152\n:::49152"
	// Take the first line and extract port after last colon
	line := strings.Split(strings.TrimSpace(out), "\n")[0]
	idx := strings.LastIndex(line, ":")
	if idx < 0 {
		return "", fmt.Errorf("unexpected port output: %q", line)
	}
	return line[idx+1:], nil
}

// Inspect returns information about a container.
func (r *CLIRuntime) Inspect(ctx context.Context, containerID string) (*syfthubapi.ContainerInfo, error) {
	out, err := r.execCommand(ctx, "inspect", "--format",
		"{{.ID}}|{{.Name}}|{{.State.Status}}|{{.State.Running}}", containerID)
	if err != nil {
		return nil, fmt.Errorf("failed to inspect container: %w", err)
	}

	parts := strings.SplitN(strings.TrimSpace(out), "|", 4)
	if len(parts) < 4 {
		return nil, fmt.Errorf("unexpected inspect output: %q", out)
	}

	return &syfthubapi.ContainerInfo{
		ID:      parts[0],
		Name:    strings.TrimPrefix(parts[1], "/"),
		Status:  parts[2],
		Running: parts[3] == "true",
	}, nil
}

// Logs returns the last N lines of container logs.
func (r *CLIRuntime) Logs(ctx context.Context, containerID string, tail int) (string, error) {
	out, err := r.execCommand(ctx, "logs", "--tail", fmt.Sprintf("%d", tail), containerID)
	if err != nil {
		return "", err
	}
	return out, nil
}

// PullImage pulls a container image.
func (r *CLIRuntime) PullImage(ctx context.Context, image string) error {
	_, err := r.execCommand(ctx, "pull", image)
	return err
}

// RuntimeAvailable checks if the container runtime is available.
func (r *CLIRuntime) RuntimeAvailable(ctx context.Context) error {
	_, err := r.execCommand(ctx, "info")
	return err
}

// buildRunArgs converts a ContainerSpec to docker/podman run arguments.
func (r *CLIRuntime) buildRunArgs(spec *ContainerSpec) []string {
	args := []string{"run", "-d"}

	if spec.Name != "" {
		args = append(args, "--name", spec.Name)
	}

	// Environment variables
	for _, env := range spec.Env {
		args = append(args, "-e", env)
	}

	// Labels
	for k, v := range spec.Labels {
		args = append(args, "--label", fmt.Sprintf("%s=%s", k, v))
	}

	// Security
	if spec.User != "" {
		args = append(args, "--user", spec.User)
	}
	if spec.ReadOnlyFS {
		args = append(args, "--read-only")
	}
	for _, cap := range spec.CapDrop {
		args = append(args, "--cap-drop", cap)
	}
	for _, opt := range spec.SecurityOpts {
		args = append(args, "--security-opt", opt)
	}

	// Mounts
	for _, m := range spec.Mounts {
		switch m.Type {
		case "bind":
			opt := fmt.Sprintf("%s:%s", m.Source, m.Target)
			if m.ReadOnly {
				opt += ":ro"
			}
			args = append(args, "-v", opt)
		case "volume":
			opt := fmt.Sprintf("%s:%s", m.Source, m.Target)
			if m.ReadOnly {
				opt += ":ro"
			}
			args = append(args, "-v", opt)
		}
	}

	// Tmpfs
	for _, t := range spec.Tmpfs {
		args = append(args, "--tmpfs", t)
	}

	// Resources
	if spec.CPUs > 0 {
		args = append(args, "--cpus", fmt.Sprintf("%.1f", spec.CPUs))
	}
	if spec.MemoryMB > 0 {
		args = append(args, "--memory", fmt.Sprintf("%dm", spec.MemoryMB))
	}

	// Network
	if spec.Network != "" {
		args = append(args, "--network", spec.Network)
	}

	// GPU (Docker vs Podman divergence)
	if spec.GPU != "" {
		if r.binary == "podman" {
			args = append(args, "--device", fmt.Sprintf("nvidia.com/gpu=%s", spec.GPU))
		} else {
			args = append(args, "--gpus", spec.GPU)
		}
	}

	// Port mappings
	for _, p := range spec.Ports {
		args = append(args, "-p", fmt.Sprintf("%s:%s", p.HostPort, p.ContainerPort))
	}

	// Image
	args = append(args, spec.Image)

	// Command
	args = append(args, spec.Cmd...)

	return args
}

// execCommand runs a CLI command and returns its stdout.
func (r *CLIRuntime) execCommand(ctx context.Context, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, r.binary, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("%s %s: %w: %s", r.binary, strings.Join(args, " "), err, strings.TrimSpace(stderr.String()))
	}

	return stdout.String(), nil
}
