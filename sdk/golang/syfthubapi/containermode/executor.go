package containermode

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ContainerExecutor implements syfthubapi.Executor by delegating to a running container
// via HTTP. The container runs the Python runner/server.py and exposes /execute.
type ContainerExecutor struct {
	runtime     syfthubapi.ContainerRuntime
	spec        *ContainerSpec
	containerID string
	baseURL     string
	timeout     time.Duration
	logger      *slog.Logger
	mu          sync.RWMutex
	closed      bool
	httpClient  *http.Client
}

// NewContainerExecutor creates a container from the spec, waits for it to become
// healthy, and returns an executor ready for use.
func NewContainerExecutor(ctx context.Context, runtime syfthubapi.ContainerRuntime, spec *ContainerSpec, timeout time.Duration, logger *slog.Logger) (*ContainerExecutor, error) {
	containerID, err := runtime.Create(ctx, spec)
	if err != nil {
		return nil, err
	}

	hostPort, err := runtime.GetHostPort(ctx, containerID, "8080")
	if err != nil {
		// Cleanup on failure
		_ = runtime.Stop(ctx, containerID)
		_ = runtime.Remove(ctx, containerID)
		return nil, &syfthubapi.ContainerError{
			Operation: "create",
			Container: containerID,
			Message:   "failed to get host port",
			Cause:     err,
		}
	}

	baseURL := fmt.Sprintf("http://localhost:%s", hostPort)

	if err := WaitForHealth(ctx, baseURL, timeout, logger); err != nil {
		// Capture logs for diagnostics
		logs, _ := runtime.Logs(ctx, containerID, 50)
		_ = runtime.Stop(ctx, containerID)
		_ = runtime.Remove(ctx, containerID)
		return nil, &syfthubapi.ContainerError{
			Operation: "health_check",
			Container: containerID,
			Image:     spec.Image,
			Message:   "container failed health check",
			Cause:     err,
			Logs:      logs,
		}
	}

	logger.Info("container executor ready",
		"container", containerID[:12],
		"base_url", baseURL,
		"image", spec.Image,
	)

	return &ContainerExecutor{
		runtime:     runtime,
		spec:        spec,
		containerID: containerID,
		baseURL:     baseURL,
		timeout:     timeout,
		logger:      logger,
		httpClient:  &http.Client{Timeout: 30 * time.Second},
	}, nil
}

// Execute sends the input to the container's /execute endpoint and returns the output.
// Implements syfthubapi.Executor.
func (e *ContainerExecutor) Execute(ctx context.Context, input *syfthubapi.ExecutorInput) (*syfthubapi.ExecutorOutput, error) {
	e.mu.RLock()
	if e.closed {
		e.mu.RUnlock()
		return nil, &syfthubapi.ContainerError{Operation: "execute", Message: "executor is closed"}
	}
	baseURL := e.baseURL
	e.mu.RUnlock()

	body, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal executor input: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/execute", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.httpClient.Do(req)
	if err != nil {
		// Check if container is still running
		info, inspectErr := e.runtime.Inspect(ctx, e.containerID)
		if inspectErr == nil && !info.Running {
			return nil, &syfthubapi.ContainerError{
				Operation: "execute",
				Container: e.containerID,
				Message:   "container is no longer running",
				Cause:     err,
			}
		}
		return nil, &syfthubapi.ContainerError{
			Operation: "execute",
			Container: e.containerID,
			Message:   "request failed",
			Cause:     err,
		}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	var output syfthubapi.ExecutorOutput
	if err := json.Unmarshal(respBody, &output); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w (body: %s)", err, string(respBody[:min(len(respBody), 200)]))
	}

	return &output, nil
}

// Close stops and removes the container. Implements syfthubapi.Executor.
func (e *ContainerExecutor) Close() error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.closed {
		return nil
	}
	e.closed = true

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := e.runtime.Stop(ctx, e.containerID); err != nil {
		e.logger.Warn("error stopping container", "id", e.containerID[:12], "error", err)
	}

	e.logger.Info("container executor closed", "id", e.containerID[:12])
	return nil
}

// Restart stops the current container and creates a new one from the same spec.
func (e *ContainerExecutor) Restart(ctx context.Context, timeout time.Duration) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.closed {
		return &syfthubapi.ContainerError{Operation: "restart", Message: "executor is closed"}
	}

	// Stop old container (best-effort)
	_ = e.runtime.Stop(ctx, e.containerID)

	// Create new container from stored spec
	containerID, err := e.runtime.Create(ctx, e.spec)
	if err != nil {
		return err
	}

	hostPort, err := e.runtime.GetHostPort(ctx, containerID, "8080")
	if err != nil {
		_ = e.runtime.Stop(ctx, containerID)
		return &syfthubapi.ContainerError{
			Operation: "restart",
			Container: containerID,
			Message:   "failed to get host port",
			Cause:     err,
		}
	}

	baseURL := fmt.Sprintf("http://localhost:%s", hostPort)
	if err := WaitForHealth(ctx, baseURL, timeout, e.logger); err != nil {
		logs, _ := e.runtime.Logs(ctx, containerID, 50)
		_ = e.runtime.Stop(ctx, containerID)
		return &syfthubapi.ContainerError{
			Operation: "restart",
			Container: containerID,
			Message:   "restarted container failed health check",
			Cause:     err,
			Logs:      logs,
		}
	}

	e.containerID = containerID
	e.baseURL = baseURL

	e.logger.Info("container executor restarted", "id", containerID[:12], "base_url", baseURL)
	return nil
}

// BaseURL returns the container's base URL.
func (e *ContainerExecutor) BaseURL() string {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.baseURL
}

// BuildEndpointSpec creates a hardened ContainerSpec for running an endpoint.
func BuildEndpointSpec(slug, dir string, globalCfg syfthubapi.ContainerConfig, overrides *ContainerOverrides, envVars []string, instanceID string) *ContainerSpec {
	image := globalCfg.Image
	cpus := globalCfg.CPUs
	memoryMB := globalCfg.MemoryMB
	network := globalCfg.Network
	gpu := globalCfg.GPU

	if overrides != nil {
		if overrides.Image != "" {
			image = overrides.Image
		}
		if overrides.CPUs > 0 {
			cpus = overrides.CPUs
		}
		if overrides.MemoryMB > 0 {
			memoryMB = overrides.MemoryMB
		}
		if overrides.Network != "" {
			network = overrides.Network
		}
		if overrides.GPU != "" {
			gpu = overrides.GPU
		}
	}

	spec := &ContainerSpec{
		Name:  fmt.Sprintf("syfthub-%s-%s", slug, instanceID),
		Image: image,
		User:  "1000:1000",

		ReadOnlyFS:   true,
		CapDrop:      []string{"ALL"},
		SecurityOpts: []string{"no-new-privileges"},

		Mounts: []Mount{
			{Type: "bind", Source: dir, Target: "/app/endpoint", ReadOnly: true},
			{Type: "volume", Source: fmt.Sprintf("syfthub-%s-pip-cache", slug), Target: "/app/.cache"},
			{Type: "volume", Source: fmt.Sprintf("syfthub-%s-policy-store", slug), Target: "/app/.store"},
		},
		Tmpfs: []string{"/tmp"},

		Labels: map[string]string{
			"syfthub.managed":  "true",
			"syfthub.instance": instanceID,
			"syfthub.endpoint": slug,
		},

		Ports: []PortMapping{
			{HostPort: "0", ContainerPort: "8080"},
		},

		CPUs:     cpus,
		MemoryMB: memoryMB,
		Network:  network,
		GPU:      gpu,

		Env: envVars,
	}

	return spec
}
