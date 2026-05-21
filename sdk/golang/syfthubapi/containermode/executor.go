package containermode

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ContainerExecutor implements syfthubapi.Executor by delegating to a running container
// via HTTP. The container runs the Python runner/server.py and exposes /execute.
type ContainerExecutor struct {
	runtime       syfthubapi.ContainerRuntime
	spec          *ContainerSpec
	containerID   string
	baseURL       string
	timeout       time.Duration
	logger        *slog.Logger
	mu            sync.RWMutex
	closed        bool
	httpClient    *http.Client
	policyConfigs []syfthubapi.PolicyConfig
	storeConfig   *syfthubapi.StoreConfig
}

// ContainerExecutorConfig holds all configuration for creating a ContainerExecutor.
type ContainerExecutorConfig struct {
	Runtime      syfthubapi.ContainerRuntime
	Spec         *ContainerSpec
	StartTimeout time.Duration
	Logger       *slog.Logger
	// PolicyConfigs contains the policies to enforce on every request.
	// They are injected into the ExecutorInput sent to the container's /execute endpoint,
	// which passes them to policy_manager.runner inside the container.
	PolicyConfigs []syfthubapi.PolicyConfig
	// StoreConfig is the stateful-policy store configuration from the file loader.
	// The host path is overridden: the container writes to the dedicated policy-store
	// volume mounted at /app/.store, not the read-only bind mount.
	StoreConfig *syfthubapi.StoreConfig
}

// containerStoreDir is the in-container mount point for the per-endpoint
// policy-store Docker volume. containerStoreDB is the SQLite file inside it.
const (
	containerStoreDir = "/app/.store"
	containerStoreDB  = containerStoreDir + "/store.db"
)

// NewContainerExecutor creates a container from the spec, waits for it to become
// healthy, and returns an executor ready for use.
//
// Before any container starts, the image is checked for the
// syfthub.sandbox.bwrap=verified label. Images without it are rejected with
// ErrImageNotVerified — the host SDK refuses to launch an image that has
// not been built from a bwrap-capable Dockerfile (default image) or stamped
// via VerifyImage (custom Dockerfiles). This is the gate that makes "all
// security enforcement happens inside the container via bwrap" a contract
// the host enforces, not a hope.
func NewContainerExecutor(ctx context.Context, cfg *ContainerExecutorConfig) (*ContainerExecutor, error) {
	runtime := cfg.Runtime
	spec := cfg.Spec
	timeout := cfg.StartTimeout
	logger := cfg.Logger

	if err := EnsureImageVerified(ctx, runtime, spec.Image, logger); err != nil {
		return nil, err
	}

	containerID, baseURL, err := startContainer(ctx, runtime, spec, timeout, logger)
	if err != nil {
		return nil, err
	}

	logger.Info("container executor ready",
		"container", containerID[:12],
		"base_url", baseURL,
		"image", spec.Image,
		"policy_count", len(cfg.PolicyConfigs),
	)

	return &ContainerExecutor{
		runtime:       runtime,
		spec:          spec,
		containerID:   containerID,
		baseURL:       baseURL,
		timeout:       timeout,
		logger:        logger,
		httpClient:    &http.Client{Timeout: 30 * time.Second},
		policyConfigs: cfg.PolicyConfigs,
		storeConfig:   cfg.StoreConfig,
	}, nil
}

// Execute sends the input to the container's /execute endpoint and returns the output.
// Implements syfthubapi.Executor.
func (e *ContainerExecutor) Execute(ctx context.Context, input *syfthubapi.ExecutorInput) (*syfthubapi.ExecutorOutput, error) {
	e.mu.RLock()
	if e.closed {
		e.mu.RUnlock()
		return nil, fmt.Errorf("container executor closed")
	}
	baseURL := e.baseURL
	e.mu.RUnlock()

	// Inject policies when configured and the caller hasn't already set them.
	// The host-side policy directory is read-only inside the container, so the
	// store path is always redirected to the dedicated writable volume at /app/.store.
	if len(e.policyConfigs) > 0 && len(input.Policies) == 0 {
		enriched := *input
		enriched.Policies = e.policyConfigs
		storeType := "sqlite"
		if e.storeConfig != nil {
			storeType = e.storeConfig.Type
		}
		enriched.Store = &syfthubapi.StoreConfig{
			Type: storeType,
			Path: containerStoreDB,
		}
		input = &enriched
	}

	var output syfthubapi.ExecutorOutput
	err := syfthubapi.DoJSONRequest(ctx, e.httpClient, http.MethodPost, baseURL+"/execute", nil, input, &output)
	if err != nil {
		// On HTTP-level errors the container is reachable; surface the status
		// code so callers don't have to unwrap. For transport errors, probe
		// whether the container is still running.
		var apiErr *syfthubapi.HubAPIError
		if errors.As(err, &apiErr) {
			return nil, fmt.Errorf("container %s execute failed (HTTP %d): %w", e.containerID, apiErr.StatusCode, err)
		}

		info, inspectErr := e.runtime.Inspect(ctx, e.containerID)
		if inspectErr == nil && !info.Running {
			return nil, fmt.Errorf("container %s is no longer running: %w", e.containerID, err)
		}
		return nil, fmt.Errorf("container %s execute failed: %w", e.containerID, err)
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
	if err := e.runtime.Remove(ctx, e.containerID); err != nil {
		e.logger.Warn("error removing container", "id", e.containerID[:12], "error", err)
	}

	e.logger.Info("container executor closed", "id", e.containerID[:12])
	return nil
}

// Restart stops the current container and creates a new one from the same spec.
func (e *ContainerExecutor) Restart(ctx context.Context, timeout time.Duration) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.closed {
		return fmt.Errorf("container executor closed")
	}

	// Stop old container (best-effort)
	_ = e.runtime.Stop(ctx, e.containerID)

	containerID, baseURL, err := startContainer(ctx, e.runtime, e.spec, timeout, e.logger)
	if err != nil {
		return err
	}

	e.containerID = containerID
	e.baseURL = baseURL

	e.logger.Info("container executor restarted", "id", containerID[:12], "base_url", baseURL)
	return nil
}

// startContainer creates a container, resolves its host port, and waits
// for /health. On any failure after Create succeeds it performs best-effort
// cleanup (Stop + Remove) so callers never see a dangling container.
func startContainer(
	ctx context.Context,
	runtime syfthubapi.ContainerRuntime,
	spec *ContainerSpec,
	timeout time.Duration,
	logger *slog.Logger,
) (string, string, error) {
	containerID, err := runtime.Create(ctx, spec)
	if err != nil {
		return "", "", err
	}

	hostPort, err := runtime.GetHostPort(ctx, containerID, "8080")
	if err != nil {
		_ = runtime.Stop(ctx, containerID)
		_ = runtime.Remove(ctx, containerID)
		return "", "", fmt.Errorf("container %s: failed to get host port: %w", containerID, err)
	}

	baseURL := fmt.Sprintf("http://localhost:%s", hostPort)

	if err := WaitForHealth(ctx, baseURL, timeout, logger); err != nil {
		logs, _ := runtime.Logs(ctx, containerID, 50)
		_ = runtime.Stop(ctx, containerID)
		_ = runtime.Remove(ctx, containerID)
		return "", "", fmt.Errorf("container %s (image %s) failed health check: %w (logs: %s)",
			containerID, spec.Image, err, logs)
	}

	return containerID, baseURL, nil
}

// BaseURL returns the container's base URL.
func (e *ContainerExecutor) BaseURL() string {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.baseURL
}

// EndpointSpecConfig groups the parameters needed to build a ContainerSpec for
// an endpoint. Using a struct avoids silent argument-order mistakes between
// adjacent string fields (slug/dir, instanceID/image).
//
// Path mounts have been redesigned for the bwrap-in-container security model:
// the raw endpoint dir is NEVER mounted into the container. Instead the host
// loader synthesizes a dir containing only code + declared resources and
// passes its path as SynthCodeDir. The endpoint's workspace pool is mounted
// separately as a writable bind.
type EndpointSpecConfig struct {
	// Slug identifies the endpoint (used for container name + volume names).
	Slug string

	// SynthCodeDir is the absolute host path of the synthesized code dir
	// produced by filemode.MaterializeSandbox. Bound read-only at /app/synth.
	//
	// REQUIRED in the bwrap-in-container model.
	SynthCodeDir string

	// WorkspacePoolDir is the absolute host path of the endpoint's workspace
	// pool (e.g., <endpoint>/workspace/). Bound read-write at /app/ws.
	// May be empty when no workspace is configured.
	WorkspacePoolDir string

	// HandlerEnvKeys is the allowlist of env-var NAMES the handler is
	// permitted to see. server.py reads _SYFT_HANDLER_ENV from the
	// container env to know which vars to forward to bwrap. The values
	// themselves arrive in EnvVars below.
	HandlerEnvKeys []string

	// Global is the SDK-wide container config (CPU, memory, network, GPU,
	// image defaults).
	Global syfthubapi.ContainerConfig

	// EnvVars is the env passed to the container ITSELF (PolicyEnv from
	// the loader). server.py filters this against HandlerEnvKeys when
	// spawning the bwrap child.
	EnvVars []string

	// InstanceID labels the container so orphan cleanup can distinguish
	// this SDK instance from others.
	InstanceID string

	// Image is the resolved image (per-endpoint custom or global default).
	Image string

	// NetworkMode overrides Global.Network for this endpoint.
	// Empty string falls back to Global.Network. Useful for per-endpoint
	// "none" or "bridge" selections from frontmatter.
	NetworkMode string

	// Sandbox carries the per-endpoint bwrap/handler sandbox controls
	// that BuildEndpointSpec translates into SYFT_* container env vars
	// consumed by server.py. Zero value is safe — server.py applies
	// fail-closed defaults.
	Sandbox SandboxRuntimeConfig
}

// WorkspaceScope selects how server.py allocates a workspace dir per
// invocation. Empty string is valid and lets server.py pick its
// type-based default (shared for one-shot, per_session for agent).
type WorkspaceScope string

const (
	WorkspaceScopeShared     WorkspaceScope = "shared"
	WorkspaceScopePerUser    WorkspaceScope = "per_user"
	WorkspaceScopePerSession WorkspaceScope = "per_session"
)

// SandboxNetMode controls the bwrap child's net namespace.
//
//	open      — share container's netns (default when empty)
//	none      — --unshare-net, no egress
//	allowlist — share netns; the host proxy enforces the host list
//	            (proxy not yet implemented; treated as open)
type SandboxNetMode string

const (
	SandboxNetOpen      SandboxNetMode = "open"
	SandboxNetNone      SandboxNetMode = "none"
	SandboxNetAllowlist SandboxNetMode = "allowlist"
)

// SandboxRuntimeConfig groups the per-endpoint flags translated into
// SYFT_* container env vars by BuildEndpointSpec.
type SandboxRuntimeConfig struct {
	// AllowSubprocess flips SYFT_ALLOW_SUBPROC, which in turn makes
	// server.py pass SYFT_ALLOW_SUBPROCESS=1 to the bwrap child. The
	// audit hook honors that env var to let the handler call
	// subprocess.Popen / os.exec — required for endpoints that shell
	// out (e.g. claude-code CLI). Default false.
	AllowSubprocess bool

	// WorkspaceScope is forwarded to server.py via SYFT_WORKSPACE_SCOPE.
	WorkspaceScope WorkspaceScope

	// NetMode is forwarded to server.py via SYFT_SANDBOX_NET.
	NetMode SandboxNetMode

	// SubprocessEnvKeys is the allowlist of env-var names that
	// subprocesses spawned by the handler inherit. Vars not in this
	// list (other than always-essentials like PATH/HOME) are stripped
	// from subprocess.Popen's default env via a monkey-patch installed
	// by _syft_audit.py. runner.py's own os.environ is unaffected.
	SubprocessEnvKeys []string
}

// SyftHandlerEnvEnv is the container env var that carries the
// comma-separated allowlist of handler-visible env var names. server.py
// reads this to know what to --setenv when spawning the bwrap child.
const SyftHandlerEnvEnv = "_SYFT_HANDLER_ENV"

// Container env vars that flip server.py sandbox behavior. Names match
// what server.py looks up via os.environ.get().
const (
	SyftAllowSubprocEnv   = "SYFT_ALLOW_SUBPROC"
	SyftWorkspaceScopeEnv = "SYFT_WORKSPACE_SCOPE"
	SyftSandboxNetEnv     = "SYFT_SANDBOX_NET"
	// SyftSubprocEnvEnv carries the comma-separated allowlist of
	// env-var names that subprocesses spawned by the handler inherit.
	// _syft_audit.py reads it and uses it as the env-pass-through
	// list when monkey-patching subprocess.Popen.
	SyftSubprocEnvEnv = "SYFT_SUBPROC_ENV"
)

// bwrap-child-set env vars (server.py sets them via --setenv when
// spawning the handler subprocess; Go never writes them on the
// container env). Listed here so the protocol drift test pins the
// contract between Go and the Python audit hook.
const (
	SyftAllowSubprocessEnv = "SYFT_ALLOW_SUBPROCESS"
	SyftCodeDirEnv         = "SYFT_CODE_DIR"
	SyftWorkspaceDirEnv    = "SYFT_WORKSPACE_DIR"
)

// In-bwrap mount paths visible to the handler. Part of the host↔handler
// contract — pinned by the protocol drift test.
const (
	GuestCodeDir      = "/app/code"
	GuestWorkspaceDir = "/app/workspace"
)

// BuildEndpointSpec creates a hardened ContainerSpec for running an endpoint.
// Resource limits (CPU, memory, network, GPU) come from the global ContainerConfig.
// The image parameter is the resolved image name — either a per-endpoint custom
// image (from ResolveEndpointImage) or the global default.
//
// Security-relevant mount layout (every container, regardless of endpoint type):
//
//	/app/synth   <- bind RO,   SynthCodeDir (host)   — code + declared resources only
//	/app/ws      <- bind RW,   WorkspacePoolDir (host) — workspace pool
//	/app/.cache  <- volume RW, per-endpoint pip cache
//	/app/.store  <- volume RW, per-endpoint policy SQLite (host-side policy
//	                only; included for compatibility with images that still
//	                consult it from inside the container)
//	/tmp         <- tmpfs RW
//
// The raw endpoint dir is intentionally absent — .env, policy/, setup.yaml
// and .setup-state.json can never appear inside the container, even before
// bwrap further narrows the view for the handler subprocess.
func BuildEndpointSpec(cfg EndpointSpecConfig) *ContainerSpec {
	mounts := []Mount{
		{Type: "volume", Source: fmt.Sprintf("syfthub-%s-pip-cache", cfg.Slug), Target: "/app/.cache"},
		{Type: "volume", Source: fmt.Sprintf("syfthub-%s-policy-store", cfg.Slug), Target: containerStoreDir},
	}
	if cfg.SynthCodeDir != "" {
		mounts = append(mounts, Mount{
			Type:     "bind",
			Source:   cfg.SynthCodeDir,
			Target:   "/app/synth",
			ReadOnly: true,
		})
	}
	if cfg.WorkspacePoolDir != "" {
		mounts = append(mounts, Mount{
			Type:     "bind",
			Source:   cfg.WorkspacePoolDir,
			Target:   "/app/ws",
			ReadOnly: false,
		})
	}

	network := cfg.NetworkMode
	if network == "" {
		network = cfg.Global.Network
	}

	// Pass the handler env allowlist + sandbox control flags to server.py
	// via the container env. server.py reads:
	//   _SYFT_HANDLER_ENV      → allowlist of env-var NAMES to forward
	//   SYFT_ALLOW_SUBPROC     → "1" makes server.py forward
	//                            SYFT_ALLOW_SUBPROCESS=1 to the bwrap
	//                            child, which the audit hook honors to
	//                            permit subprocess.Popen / os.exec
	//   SYFT_WORKSPACE_SCOPE   → "shared" | "per_user" | "per_session"
	//   SYFT_SANDBOX_NET       → "open" | "allowlist" | "none"
	sb := cfg.Sandbox
	env := make([]string, 0, len(cfg.EnvVars)+4)
	env = append(env, cfg.EnvVars...)
	if len(cfg.HandlerEnvKeys) > 0 {
		env = append(env, SyftHandlerEnvEnv+"="+strings.Join(cfg.HandlerEnvKeys, ","))
	}
	if sb.AllowSubprocess {
		env = append(env, SyftAllowSubprocEnv+"=1")
	}
	if sb.WorkspaceScope != "" {
		env = append(env, SyftWorkspaceScopeEnv+"="+string(sb.WorkspaceScope))
	}
	if sb.NetMode != "" {
		env = append(env, SyftSandboxNetEnv+"="+string(sb.NetMode))
	}
	if len(sb.SubprocessEnvKeys) > 0 {
		env = append(env, SyftSubprocEnvEnv+"="+strings.Join(sb.SubprocessEnvKeys, ","))
	}

	spec := &ContainerSpec{
		Name:  fmt.Sprintf("syfthub-%s-%s", cfg.Slug, cfg.InstanceID),
		Image: cfg.Image,
		User:  "1000:1000",

		ReadOnlyFS: true,
		CapDrop:    []string{"ALL"},
		// seccomp=unconfined + apparmor=unconfined are BOTH required for
		// the in-container bwrap child to set up its sandbox:
		//   - seccomp blocks unshare(CLONE_NEWUSER) under the default
		//     docker profile → "bwrap: No permissions to create new namespace".
		//   - apparmor's docker-default profile blocks the
		//     `mount --make-slave /` operation bwrap performs after
		//     creating the userns → "bwrap: Failed to make / slave:
		//     Permission denied".
		// Without these, every agent session fails (the synthetic
		// session.failed event surfaces the bwrap stderr).
		//
		// Defense-in-depth remains:
		//   - cap_drop ALL    → container has no Linux capabilities
		//   - no-new-privs    → setuid/setgid bits ignored
		//   - read-only FS    → root filesystem cannot be modified
		//   - user 1000:1000  → not running as root
		//   - bwrap mount NS  → handler subprocess gets its own view
		//                       (only /app/code RO + /app/workspace RW +
		//                       minimal /usr + /lib)
		//   - audit hook      → Python-level deny of .env/policy/subproc
		// Docker-level MAC is relaxed to let bwrap do its job; the
		// kernel-level capability/permission constraints + the in-bwrap
		// layers are what actually enforce the security boundary.
		SecurityOpts: []string{
			"no-new-privileges",
			"seccomp=unconfined",
			"apparmor=unconfined",
		},

		Mounts: mounts,
		Tmpfs:  []string{"/tmp"},

		Labels: map[string]string{
			"syfthub.managed":  "true",
			"syfthub.instance": cfg.InstanceID,
			"syfthub.endpoint": cfg.Slug,
		},

		Ports: []PortMapping{
			{HostPort: "0", ContainerPort: "8080"},
		},

		CPUs:     cfg.Global.CPUs,
		MemoryMB: cfg.Global.MemoryMB,
		Network:  network,
		GPU:      cfg.Global.GPU,

		Env: env,
	}

	return spec
}
