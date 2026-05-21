package filemode

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// loadParallelism caps concurrent container endpoint builds during LoadAll.
// Docker daemon handles concurrent builds and creates fine; the cap stops
// us from saturating CPU on large endpoint sets (each augmented build
// copies the endpoint dir + injects the runtime).
func loadParallelism() int {
	n := runtime.NumCPU()
	if n > 4 {
		return 4
	}
	if n < 1 {
		return 1
	}
	return n
}

// noopPolicyHandler is the Python noop handler used by agent endpoints with
// policies. The policy_manager.runner evaluates policies and then invokes this
// handler which simply returns an empty string, since the real work is done by
// the agent's long-lived subprocess — not by the policy executor.
const noopPolicyHandler = "def handler(messages, context):\n    return \"\"\n"

// Provider manages file-based endpoints with hot-reload support.
type Provider struct {
	basePath     string
	pythonPath   string
	watchEnabled bool
	debounce     time.Duration
	logger       *slog.Logger

	loader         *Loader
	watcher        *Watcher
	venvManager    *VenvManager
	embeddedPython *EmbeddedPythonManager

	containerRuntime syfthubapi.ContainerRuntime
	containerConfig  *syfthubapi.ContainerConfig
	instanceID       string

	endpoints        []*syfthubapi.Endpoint
	executors        map[string]syfthubapi.Executor
	noopHandlerPaths map[string]string // slug -> temp file path for noop policy handlers

	// routingRecorderFactory, when non-nil, builds a manualreview.RoutingRecorder
	// per agent endpoint that has policies configured. Set by the embedder
	// (typically the desktop) which holds the SQLite driver dependency the
	// SDK intentionally avoids. routingRecorders maps slug -> recorder for
	// cleanup on endpoint removal and provider shutdown.
	routingRecorderFactory manualreview.RoutingRecorderFactory
	routingRecorders       map[string]manualreview.RoutingRecorder

	mu sync.RWMutex

	onReload   func([]*syfthubapi.Endpoint)
	onProgress LoadProgressCallback
	running    bool
	stopCh     chan struct{}
	stoppedCh  chan struct{}
}

// ProviderConfig holds provider configuration.
type ProviderConfig struct {
	BasePath           string
	PythonPath         string
	WatchEnabled       bool
	Debounce           time.Duration
	Logger             *slog.Logger
	OnReload           func([]*syfthubapi.Endpoint)
	UseEmbeddedPython  bool   // If true, download and use embedded Python
	EmbeddedPythonPath string // Custom path for embedded Python cache
	// OnProgress, if non-nil, receives a LoadProgressEvent at every phase
	// transition during LoadEndpoints. Called from the build goroutine,
	// so the callback must be safe for concurrent invocation.
	OnProgress LoadProgressCallback

	// RoutingRecorderFactory, when non-nil, is invoked once per agent
	// endpoint that has policies configured. The resulting RoutingRecorder
	// is wired into the AgentExecutor for that endpoint so pending policy
	// notices carrying a manual_review handle are captured for later
	// resolution delivery. When nil, manual-review capture is disabled and
	// the executor still surfaces notices but resolutions can only be
	// reconciled via the caller-side "mark manually" path.
	RoutingRecorderFactory manualreview.RoutingRecorderFactory
}

// NewProvider creates a new file-based endpoint provider.
func NewProvider(cfg *ProviderConfig) (*Provider, error) {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	debounce := cfg.Debounce
	if debounce == 0 {
		debounce = time.Second
	}

	pythonPath := cfg.PythonPath

	// Setup embedded Python manager if enabled
	var embeddedPython *EmbeddedPythonManager
	if cfg.UseEmbeddedPython {
		var err error
		embeddedPython, err = NewEmbeddedPythonManager(&EmbeddedPythonConfig{
			BaseDir: cfg.EmbeddedPythonPath,
			Logger:  logger,
		})
		if err != nil {
			logger.Warn("failed to create embedded Python manager", "error", err)
		} else {
			// EnsurePython will be called lazily when needed
			logger.Info("embedded Python manager initialized",
				"version", PythonVersion,
			)
		}
	}

	// If no Python path specified and not using embedded, use system default
	if pythonPath == "" && embeddedPython == nil {
		pythonPath = "python3"
	}

	loader := NewLoader(cfg.BasePath, logger)

	venvManager, err := NewVenvManager(&VenvConfig{
		PythonPath: pythonPath,
		Logger:     logger,
	})
	if err != nil {
		logger.Warn("failed to create venv manager", "error", err)
		// Continue without venv support
	}

	p := &Provider{
		basePath:               cfg.BasePath,
		pythonPath:             pythonPath,
		watchEnabled:           cfg.WatchEnabled,
		debounce:               debounce,
		logger:                 logger,
		loader:                 loader,
		venvManager:            venvManager,
		embeddedPython:         embeddedPython,
		executors:              make(map[string]syfthubapi.Executor),
		noopHandlerPaths:       make(map[string]string),
		routingRecorderFactory: cfg.RoutingRecorderFactory,
		routingRecorders:       make(map[string]manualreview.RoutingRecorder),
		onReload:               cfg.OnReload,
		onProgress:             cfg.OnProgress,
		stopCh:                 make(chan struct{}),
		stoppedCh:              make(chan struct{}),
	}

	return p, nil
}

// Start begins the provider, loading endpoints and starting the watcher.
func (p *Provider) Start(ctx context.Context) error {
	p.mu.Lock()
	if p.running {
		p.mu.Unlock()
		return nil
	}
	p.running = true
	p.stopCh = make(chan struct{})
	p.stoppedCh = make(chan struct{})
	p.mu.Unlock()

	defer close(p.stoppedCh)

	// Load initial endpoints only if not already loaded
	p.mu.RLock()
	alreadyLoaded := len(p.endpoints) > 0
	p.mu.RUnlock()

	if !alreadyLoaded {
		if _, err := p.LoadEndpoints(); err != nil {
			p.logger.Warn("initial endpoint load failed", "error", err)
		}
	} else {
		p.logger.Debug("endpoints already loaded, skipping initial load", "count", len(p.endpoints))
	}

	// Start watcher if enabled
	if p.watchEnabled {
		watcher, err := NewWatcher(&WatcherConfig{
			BasePath:      p.basePath,
			DebounceDelay: p.debounce,
			Logger:        p.logger,
			Callback:      p.handleReload,
		})
		if err != nil {
			p.logger.Warn("failed to create watcher", "error", err)
		} else {
			p.watcher = watcher
			go func() {
				if err := watcher.Start(ctx); err != nil {
					p.logger.Error("watcher error", "error", err)
				}
			}()
		}
	}

	// Wait for stop signal
	select {
	case <-ctx.Done():
		return nil
	case <-p.stopCh:
		return nil
	}
}

// Stop stops the provider.
func (p *Provider) Stop(ctx context.Context) error {
	p.mu.Lock()
	if !p.running {
		p.mu.Unlock()
		return nil
	}
	p.running = false
	close(p.stopCh)
	p.mu.Unlock()

	// Stop watcher
	if p.watcher != nil {
		p.watcher.Stop(ctx)
	}

	// Close all executors and clean up noop handler temp files
	p.mu.Lock()
	p.cleanupResources()
	p.mu.Unlock()

	select {
	case <-p.stoppedCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// cleanupResources closes all executors and removes noop handler temp files.
// Caller must hold p.mu.
func (p *Provider) cleanupResources() {
	for slug, exec := range p.executors {
		if err := exec.Close(); err != nil {
			p.logger.Warn("failed to close executor",
				"slug", slug,
				"error", err,
			)
		}
	}
	p.executors = make(map[string]syfthubapi.Executor)
	for slug, path := range p.noopHandlerPaths {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			p.logger.Warn("failed to remove noop policy handler temp file",
				"slug", slug,
				"path", path,
				"error", err,
			)
		}
	}
	p.noopHandlerPaths = make(map[string]string)

	// Close all manual-review routing recorders. Each recorder owns a SQLite
	// connection to the endpoint's policy/store.db; the connection survives
	// across reloads (executor lifecycle is independent) so closing here on
	// provider shutdown is sufficient.
	for slug, rec := range p.routingRecorders {
		if err := rec.Close(); err != nil {
			p.logger.Warn("failed to close routing recorder", "slug", slug, "error", err)
		}
	}
	p.routingRecorders = make(map[string]manualreview.RoutingRecorder)

	// Remove the entire synth root for this provider instance so
	// container-mode endpoints don't leave stale staging dirs in $TMPDIR
	// across restarts. synthDirForSlug recreates the root on next use.
	root := p.synthRoot()
	if err := os.RemoveAll(root); err != nil && !os.IsNotExist(err) {
		p.logger.Warn("failed to remove synth root",
			"path", root,
			"error", err,
		)
	}
}

// synthRoot returns the per-provider synth root directory (under $TMPDIR).
// Falls back to "default" when instanceID is unset.
func (p *Provider) synthRoot() string {
	id := p.instanceID
	if id == "" {
		id = "default"
	}
	return filepath.Join(os.TempDir(), "syfthub-synth", id)
}

// LoadEndpoints loads all endpoints from the file system.
func (p *Provider) LoadEndpoints() ([]*syfthubapi.Endpoint, error) {
	// Ensure embedded Python is ready if enabled
	if p.embeddedPython != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
		defer cancel()

		pythonPath, err := p.embeddedPython.EnsurePython(ctx)
		if err != nil {
			p.logger.Error("failed to ensure embedded Python", "error", err)
		} else if pythonPath != p.pythonPath {
			p.pythonPath = pythonPath
			p.venvManager, err = NewVenvManager(&VenvConfig{
				PythonPath: pythonPath,
				Logger:     p.logger,
			})
			if err != nil {
				p.logger.Warn("failed to recreate venv manager with embedded Python", "error", err)
			}
		}
	}

	// Ensure the container image exists before loading endpoints.
	if p.containerRuntime != nil && p.containerConfig != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
		defer cancel()
		if err := containermode.EnsureImage(ctx, p.containerRuntime, p.containerConfig.Image, p.logger); err != nil {
			p.logger.Error("failed to ensure container image", "image", p.containerConfig.Image, "error", err)
			return nil, fmt.Errorf("container image not available: %w", err)
		}
	}

	loadedEndpoints, err := p.loader.LoadAll()
	if err != nil {
		return nil, err
	}

	endpoints := make([]*syfthubapi.Endpoint, 0, len(loadedEndpoints))

	p.mu.Lock()
	defer p.mu.Unlock()

	// Close container executors before resetting — they own named Docker
	// containers that must be stopped before a new container with the same
	// name can be created. Subprocess executors are left open; the registry
	// handles their lifecycle via ReplaceFileBased. Close in parallel to
	// avoid sequential 15s-per-container stop timeouts.
	var wg sync.WaitGroup
	for slug, exec := range p.executors {
		if _, isContainer := exec.(*containermode.ContainerExecutor); isContainer {
			wg.Add(1)
			go func(s string, e syfthubapi.Executor) {
				defer wg.Done()
				if err := e.Close(); err != nil {
					p.logger.Warn("failed to close container executor during reload", "slug", s, "error", err)
				}
			}(slug, exec)
		}
	}
	wg.Wait()
	p.executors = make(map[string]syfthubapi.Executor)
	// Keep p.noopHandlerPaths intact: createEndpoint overwrites entries for
	// recreated slugs, and cleanupResources (from Stop) deletes all files.

	total := len(loadedEndpoints)
	// Announce every endpoint as pending up front so the UI can render
	// a complete checklist before any work starts.
	for i, loaded := range loadedEndpoints {
		p.emitProgress(LoadProgressEvent{
			Slug:  loaded.Config.Slug,
			Name:  loaded.Config.Name,
			Phase: LoadPhasePending,
			Index: i,
			Total: total,
		})
	}

	// Container mode: run the slow per-endpoint build (image resolve,
	// sandbox materialize, container start + health wait) in parallel
	// outside any per-endpoint critical section. Each build returns a
	// containerBuildResult that's committed serially below so executor
	// map writes remain ordered. File-mode endpoints fall through to
	// the sequential path — their slow step (venv setup) is cached and
	// the file-mode createEndpoint mutates p.* directly under p.mu.
	containerBuilds := make([]*containerBuildResult, total)
	containerErrs := make([]error, total)
	if p.containerRuntime != nil && p.containerConfig != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
		defer cancel()
		g, gCtx := errgroup.WithContext(ctx)
		g.SetLimit(loadParallelism())
		for i, loaded := range loadedEndpoints {
			i, loaded := i, loaded
			g.Go(func() error {
				base := LoadProgressEvent{
					Slug:  loaded.Config.Slug,
					Name:  loaded.Config.Name,
					Index: i,
					Total: total,
				}
				br, err := p.buildContainerEndpoint(gCtx, loaded, base)
				if err != nil {
					p.logger.Warn("failed to create endpoint",
						"slug", loaded.Config.Slug,
						"error", err,
					)
					containerErrs[i] = err
					return nil
				}
				containerBuilds[i] = br
				return nil
			})
		}
		_ = g.Wait()
	}

	for i, loaded := range loadedEndpoints {
		base := LoadProgressEvent{
			Slug:  loaded.Config.Slug,
			Name:  loaded.Config.Name,
			Index: i,
			Total: total,
		}
		if br := containerBuilds[i]; br != nil {
			p.commitContainerBuild(br)
			endpoints = append(endpoints, br.endpoint)
			base.Phase = LoadPhaseReady
			p.emitProgress(base)
			continue
		}
		if p.containerRuntime != nil && p.containerConfig != nil {
			// Container build failed; warning was already logged in the
			// goroutine. Surface the failure phase to the UI.
			base.Phase = LoadPhaseFailed
			if containerErrs[i] != nil {
				base.Error = containerErrs[i].Error()
			}
			p.emitProgress(base)
			continue
		}
		endpoint, err := p.createEndpoint(loaded)
		if err != nil {
			p.logger.Warn("failed to create endpoint",
				"slug", loaded.Config.Slug,
				"error", err,
			)
			base.Phase = LoadPhaseFailed
			base.Error = err.Error()
			p.emitProgress(base)
			continue
		}
		endpoints = append(endpoints, endpoint)
		base.Phase = LoadPhaseReady
		p.emitProgress(base)
	}

	p.endpoints = endpoints
	return endpoints, nil
}

// createEndpoint creates an Endpoint from a LoadedEndpoint.
// Container mode is all-or-nothing: when a container runtime has been injected
// via SetContainerRuntime, every endpoint runs in a container.
func (p *Provider) createEndpoint(loaded *LoadedEndpoint) (*syfthubapi.Endpoint, error) {
	if p.containerRuntime != nil && p.containerConfig != nil {
		ctx, cancel := context.WithTimeout(context.Background(), p.containerConfig.StartTimeout)
		defer cancel()
		return p.createContainerEndpoint(ctx, loaded)
	}

	p.logger.Info("[POLICY-SETUP] Creating endpoint",
		"slug", loaded.Config.Slug,
		"name", loaded.Config.Name,
		"type", loaded.Config.Type,
		"dir", loaded.Dir,
		"policy_count", len(loaded.PolicyConfigs),
	)

	// Log all loaded policies
	for i, pc := range loaded.PolicyConfigs {
		p.logger.Info("[POLICY-SETUP] Loaded policy config",
			"slug", loaded.Config.Slug,
			"index", i,
			"policy_name", pc.Name,
			"policy_type", pc.Type,
			"config", fmt.Sprintf("%+v", pc.Config),
		)
	}

	if loaded.StoreConfig != nil {
		p.logger.Info("[POLICY-SETUP] Store config",
			"slug", loaded.Config.Slug,
			"store_type", loaded.StoreConfig.Type,
			"store_path", loaded.StoreConfig.Path,
		)
	}

	// Determine Python path (use venv if available)
	pythonPath := p.pythonPath
	if p.venvManager != nil {
		// Install policy-manager from GitHub when policies are configured
		// TODO: Update to git+https://github.com/OpenMined/syft-policies.git once the OpenMined repository becomes public
		var additionalDeps []string
		if len(loaded.PolicyConfigs) > 0 {
			additionalDeps = append(additionalDeps, "git+https://github.com/IonesioJunior/policy-manager.git")
			p.logger.Info("[POLICY-SETUP] Will install policy-manager from GitHub",
				"slug", loaded.Config.Slug,
				"dep", "git+https://github.com/IonesioJunior/policy-manager.git",
			)
		}
		p.logger.Info("[POLICY-SETUP] Creating/using venv",
			"slug", loaded.Config.Slug,
			"endpoint_dir", loaded.Dir,
			"extras", loaded.Config.Runtime.Extras,
			"additional_deps", additionalDeps,
		)
		venvPython, err := p.venvManager.EnsureVenv(loaded.Dir, loaded.Config.Runtime.Extras, additionalDeps...)
		if err != nil {
			p.logger.Warn("[POLICY-SETUP] Failed to create venv, using system Python",
				"slug", loaded.Config.Slug,
				"error", err,
			)
		} else {
			pythonPath = venvPython
			p.logger.Info("[POLICY-SETUP] Using venv Python",
				"slug", loaded.Config.Slug,
				"python_path", pythonPath,
			)
		}
	} else {
		p.logger.Warn("[POLICY-SETUP] No venv manager available",
			"slug", loaded.Config.Slug,
		)
	}

	enabled := true
	if loaded.Config.Enabled != nil {
		enabled = *loaded.Config.Enabled
	}

	endpoint := &syfthubapi.Endpoint{
		Slug:               loaded.Config.Slug,
		Name:               loaded.Config.Name,
		Description:        loaded.Config.Description,
		Type:               ToEndpointType(loaded.Config.Type),
		Enabled:            enabled,
		Version:            loaded.Config.Version,
		Readme:             loaded.ReadmeBody,
		AcceptsAttachments: loaded.Config.AcceptsAttachments,
	}

	// Build handler config based on endpoint type
	handlerCfg := syfthubapi.EndpointHandlerConfig{Logger: p.logger}

	if loaded.Config.Type == string(syfthubapi.EndpointTypeAgent) {
		// Agent endpoints use a long-lived subprocess bridge
		handlerCfg.AgentHandler = NewAgentHandler(&AgentHandlerConfig{
			PythonPath: pythonPath,
			RunnerPath: loaded.RunnerPath,
			WorkDir:    loaded.Dir,
			Env:        loaded.EnvVars,
			Logger:     p.logger,
		})

		// Create dedicated policy executor if policies are configured
		if len(loaded.PolicyConfigs) > 0 {
			policyExec, err := p.createAgentPolicyExecutor(loaded, pythonPath)
			if err != nil {
				return nil, err
			}
			handlerCfg.PolicyExecutor = policyExec
			p.executors[loaded.Config.Slug+".policy"] = policyExec

			// Wire a manual-review routing recorder so pending policy notices
			// surfaced during this agent's sessions are captured for later
			// resolution delivery.
			if rec := p.openRoutingRecorder(loaded); rec != nil {
				handlerCfg.RoutingRecorder = rec
				p.routingRecorders[loaded.Config.Slug] = rec
			}
		}
	} else {
		// Model/DataSource endpoints use one-shot subprocess executor
		usePolicyRunner := len(loaded.PolicyConfigs) > 0
		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			PythonPath:      pythonPath,
			RunnerPath:      loaded.RunnerPath,
			WorkDir:         loaded.Dir,
			Env:             loaded.EnvVars,
			Timeout:         time.Duration(loaded.Config.Runtime.Timeout) * time.Second,
			Logger:          p.logger,
			PolicyConfigs:   loaded.PolicyConfigs,
			StoreConfig:     loaded.StoreConfig,
			UsePolicyRunner: usePolicyRunner,
		})
		if err != nil {
			return nil, err
		}
		handlerCfg.Executor = executor
		p.executors[loaded.Config.Slug] = executor
	}

	endpoint.SetHandler(handlerCfg)
	return endpoint, nil
}

// createAgentPolicyExecutor is the legacy in-place variant: writes the
// noop handler, builds the executor, AND mutates p.noopHandlerPaths.
// Caller must hold p.mu. Used by the file-mode createEndpoint path
// (which already holds the lock for the whole loop).
// openRoutingRecorder builds a manualreview routing recorder for loaded if the
// embedder supplied a factory and the endpoint actually has a policy store.
// Returns nil when capture is disabled or the factory fails (logged) — callers
// treat nil as "manual-review delivery disabled for this endpoint" and the
// agent executor still surfaces pending notices.
func (p *Provider) openRoutingRecorder(loaded *LoadedEndpoint) manualreview.RoutingRecorder {
	if p.routingRecorderFactory == nil || loaded.StoreConfig == nil || loaded.StoreConfig.Path == "" {
		return nil
	}
	rec, err := p.routingRecorderFactory(loaded.StoreConfig.Path)
	if err != nil {
		p.logger.Warn("[POLICY-SETUP] failed to open manual-review routing recorder — manual-review delivery will be disabled for this endpoint",
			"slug", loaded.Config.Slug,
			"store_db", loaded.StoreConfig.Path,
			"error", err,
		)
		return nil
	}
	return rec
}

func (p *Provider) createAgentPolicyExecutor(loaded *LoadedEndpoint, pythonPath string) (syfthubapi.Executor, error) {
	exec, noopPath, err := p.buildAgentPolicyExecutor(loaded, pythonPath)
	if err != nil {
		return nil, err
	}
	p.noopHandlerPaths[loaded.Config.Slug] = noopPath
	return exec, nil
}

// ensurePolicyVenv returns the Python interpreter path for host-side policy
// checks in container mode. It creates (or reuses) a venv that contains only
// policy_manager — the endpoint's own runtime deps are installed inside the
// container, so they are not needed here. Falls back to p.pythonPath when no
// venv manager is available (requires policy_manager already on PATH).
func (p *Provider) ensurePolicyVenv(loaded *LoadedEndpoint) (string, error) {
	if p.venvManager == nil {
		return p.pythonPath, nil
	}
	const policyManagerDep = "git+https://github.com/IonesioJunior/policy-manager.git"
	// nil extras: endpoint deps run inside the container, not on the host.
	return p.venvManager.EnsureVenv(loaded.Dir, nil, policyManagerDep)
}

// handleReload handles file change notifications.
// When affectedDirs is non-empty, only those specific endpoint directories are
// reloaded instead of re-scanning everything. This avoids tearing down and
// recreating executors (venvs, subprocesses) for endpoints that didn't change.
func (p *Provider) handleReload(affectedDirs []string) {
	p.logger.Info("reloading endpoints",
		"affected", len(affectedDirs),
	)

	// Fall back to full reload when we don't know which dirs changed.
	if len(affectedDirs) == 0 {
		endpoints, err := p.LoadEndpoints()
		if err != nil {
			p.logger.Error("failed to reload endpoints", "error", err)
			return
		}
		if p.onReload != nil {
			p.onReload(endpoints)
		}
		return
	}

	// Selective reload: only recreate the affected endpoints.
	for _, dir := range affectedDirs {
		slug := filepath.Base(dir)
		p.logger.Info("selectively reloading endpoint",
			"slug", slug,
			"dir", dir,
		)

		loaded, err := p.loader.LoadEndpoint(dir)
		if err != nil {
			p.logger.Warn("failed to reload endpoint, removing it",
				"slug", slug,
				"dir", dir,
				"error", err,
			)
			p.mu.Lock()
			p.removeEndpointLocked(slug)
			p.mu.Unlock()
			continue
		}

		p.mu.Lock()
		// Close the old executor and noop handler for this slug.
		p.removeEndpointLocked(slug)
		p.mu.Unlock()

		// createEndpoint may do slow work (venv setup, container start); run it
		// outside the lock so concurrent requests are not blocked during reload.
		endpoint, err := p.createEndpoint(loaded)
		if err != nil {
			p.logger.Warn("failed to recreate endpoint",
				"slug", slug,
				"error", err,
			)
			continue
		}

		// Insert the new endpoint, replacing any existing one with the same slug.
		p.mu.Lock()
		replaced := false
		for i, ep := range p.endpoints {
			if ep.Slug == slug {
				p.endpoints[i] = endpoint
				replaced = true
				break
			}
		}
		if !replaced {
			p.endpoints = append(p.endpoints, endpoint)
		}
		p.mu.Unlock()
	}

	// Reconcile p.endpoints against the filesystem — the single source of truth.
	// After selective reload, some slugs may have been removed from disk but
	// not from the in-memory slice (e.g. removeEndpointLocked only cleans
	// executors). A cheap ReadDir pins the list to reality.
	entries, readErr := os.ReadDir(p.basePath)
	if readErr != nil {
		p.logger.Warn("reconcile: failed to read endpoints directory", "path", p.basePath, "error", readErr)
	} else {
		diskSlugs := make(map[string]struct{}, len(entries))
		for _, e := range entries {
			if e.IsDir() && len(e.Name()) > 0 && e.Name()[0] != '.' {
				diskSlugs[e.Name()] = struct{}{}
			}
		}
		p.mu.Lock()
		filtered := make([]*syfthubapi.Endpoint, 0, len(p.endpoints))
		for _, ep := range p.endpoints {
			if _, ok := diskSlugs[ep.Slug]; ok {
				filtered = append(filtered, ep)
			} else {
				p.logger.Info("removing stale endpoint not found on disk", "slug", ep.Slug)
			}
		}
		p.endpoints = filtered
		p.mu.Unlock()
	}

	p.mu.RLock()
	endpoints := make([]*syfthubapi.Endpoint, len(p.endpoints))
	copy(endpoints, p.endpoints)
	p.mu.RUnlock()

	if p.onReload != nil {
		p.onReload(endpoints)
	}
}

// removeEndpointLocked removes the executor references for the given slug
// from the provider's internal maps. For container executors, the executor is
// closed (stopping the container) so that the name can be reused on recreate.
// Subprocess executors are left open — the registry closes stale ones in
// ReplaceFileBased. Caller must hold p.mu.
//
// NOTE: The noop handler file is intentionally NOT deleted here. Between
// removeEndpointLocked and the subsequent ReplaceFileBased call (which closes
// the old invoker), the old endpoint stays in the registry. Its SubprocessExecutor
// still needs the noop file to service in-flight policy checks. Deleting the file
// here would cause "policy check failed: FileNotFoundError" during the container
// restart window. Files are cleaned up by cleanupResources (on Stop) and
// overwritten by createAgentPolicyExecutor on the next reload.
func (p *Provider) removeEndpointLocked(slug string) {
	// Close container executors explicitly so the container name is freed for reuse.
	// Subprocess executors are left open — the registry handles their lifecycle.
	for _, key := range []string{slug, slug + ".policy"} {
		if exec, ok := p.executors[key]; ok {
			if _, isContainer := exec.(*containermode.ContainerExecutor); isContainer {
				if err := exec.Close(); err != nil {
					p.logger.Warn("failed to close container executor on reload", "slug", key, "error", err)
				}
			}
		}
	}
	delete(p.executors, slug)
	delete(p.executors, slug+".policy")
	// Keep p.noopHandlerPaths entry intact — see comment above.

	// Close the routing recorder for this endpoint. Unlike the noop handler
	// file, the recorder is purely in-memory state — closing it here is safe
	// because the AgentExecutor that holds a reference to it goes away when
	// the old invoker is closed by ReplaceFileBased (the new endpoint, if
	// any, gets a fresh recorder via the factory in createEndpoint).
	if rec, ok := p.routingRecorders[slug]; ok {
		if err := rec.Close(); err != nil {
			p.logger.Warn("failed to close routing recorder on reload", "slug", slug, "error", err)
		}
		delete(p.routingRecorders, slug)
	}
}

// RemoveEndpoint removes a single endpoint by slug from both the executor map
// and the in-memory endpoint list. Use this for synchronous deletion so the
// endpoint disappears from Endpoints() immediately, without waiting for the
// file watcher debounce.
func (p *Provider) RemoveEndpoint(slug string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.removeEndpointLocked(slug)
	filtered := make([]*syfthubapi.Endpoint, 0, len(p.endpoints))
	for _, ep := range p.endpoints {
		if ep.Slug != slug {
			filtered = append(filtered, ep)
		}
	}
	p.endpoints = filtered
}

// Endpoints returns the currently loaded endpoints.
func (p *Provider) Endpoints() []*syfthubapi.Endpoint {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.endpoints
}

// GetExecutor returns the executor for an endpoint.
func (p *Provider) GetExecutor(slug string) (syfthubapi.Executor, bool) {
	p.mu.RLock()
	defer p.mu.RUnlock()
	exec, ok := p.executors[slug]
	return exec, ok
}

// SetContainerRuntime injects the container runtime into the provider.
// Implements syfthubapi.ContainerRuntimeSetter.
func (p *Provider) SetContainerRuntime(rt syfthubapi.ContainerRuntime, cfg *syfthubapi.ContainerConfig, instanceID string) {
	p.containerRuntime = rt
	p.containerConfig = cfg
	p.instanceID = instanceID
}

// createContainerEndpoint creates an endpoint backed by a container executor.
// emitProgress delivers a LoadProgressEvent to the registered callback,
// if any. Nil-safe. Called from arbitrary goroutines — callback authors
// are responsible for synchronization.
func (p *Provider) emitProgress(ev LoadProgressEvent) {
	if p.onProgress == nil {
		return
	}
	p.onProgress(ev)
}

// containerBuildResult carries the outputs of a container endpoint build
// that must be applied to provider state once all parallel builds have
// finished. Keeps slow IO (docker, file IO) outside the provider mutex
// while preserving deterministic state mutation order.
type containerBuildResult struct {
	loaded     *LoadedEndpoint
	endpoint   *syfthubapi.Endpoint
	executor   syfthubapi.Executor
	policyExec syfthubapi.Executor // nil unless agent + policies
	noopPath   string              // empty unless policyExec is set

	// routingRecorder mirrors the subprocess path: when the agent endpoint
	// has policies AND the provider has a recorder factory, we open a
	// recorder against the policy store.db here so manual-review notices
	// surfaced during the session are captured for later delivery. nil
	// otherwise. Committed into p.routingRecorders by commitContainerBuild.
	routingRecorder manualreview.RoutingRecorder
}

// createContainerEndpoint is preserved as a single-shot path used by the
// selective-reload code path in handleReload. New code should prefer
// buildContainerEndpoint + commitContainerBuild so the slow work runs
// outside p.mu and can be parallelized.
func (p *Provider) createContainerEndpoint(ctx context.Context, loaded *LoadedEndpoint) (*syfthubapi.Endpoint, error) {
	br, err := p.buildContainerEndpoint(ctx, loaded)
	if err != nil {
		return nil, err
	}
	p.commitContainerBuild(br)
	return br.endpoint, nil
}

// buildContainerEndpoint performs ALL slow IO for a container endpoint
// (image resolve, sandbox materialize, container start) but does NOT
// touch provider state. The caller must commit the returned result to
// p.executors / p.noopHandlerPaths under p.mu via commitContainerBuild.
// progressBase is a partially-populated event the caller has filled with
// Slug/Name/Index/Total; this function clones it and sets Phase/Message
// for each emitted progress update.
func (p *Provider) buildContainerEndpoint(ctx context.Context, loaded *LoadedEndpoint, progressBase ...LoadProgressEvent) (*containerBuildResult, error) {
	emit := func(phase LoadPhase, message string) {
		if len(progressBase) == 0 || p.onProgress == nil {
			return
		}
		ev := progressBase[0]
		ev.Phase = phase
		ev.Message = message
		p.onProgress(ev)
	}
	p.logger.Info("[CONTAINER-SETUP] Creating container endpoint",
		"slug", loaded.Config.Slug,
		"type", loaded.Config.Type,
		"dir", loaded.Dir,
		"policy_count", len(loaded.PolicyConfigs),
	)

	emit(LoadPhaseResolvingImage, "")
	// Resolve per-endpoint image: frontmatter container.image > Dockerfile > global default.
	image, err := containermode.ResolveEndpointImage(
		ctx,
		p.containerRuntime,
		loaded.Config.Slug,
		loaded.Dir,
		loaded.Config.Container.Image,
		loaded.HasDockerfile,
		p.containerConfig.Image,
		p.logger,
		func(stage containermode.ImageResolveStage) {
			switch stage {
			case containermode.ImageStagePulling:
				emit(LoadPhasePullingImage, "")
			case containermode.ImageStageBuilding:
				emit(LoadPhaseBuildingImage, "")
			case containermode.ImageStageVerifying:
				emit(LoadPhaseVerifyingImage, "")
			}
		},
	)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve container image for %s: %w", loaded.Config.Slug, err)
	}

	emit(LoadPhaseMaterializing, "")
	// Build the synth dir — the ONLY code+resources view the container ever
	// sees. .env, policy/, setup.yaml are absent from it by construction.
	manifest, err := BuildSandboxManifest(loaded)
	if err != nil {
		return nil, fmt.Errorf("sandbox manifest for %s: %w", loaded.Config.Slug, err)
	}
	synthDir, err := p.synthDirForSlug(loaded.Config.Slug)
	if err != nil {
		return nil, fmt.Errorf("synth dir for %s: %w", loaded.Config.Slug, err)
	}
	// Rebuild from scratch — selective-reload requirement.
	if err := os.RemoveAll(synthDir); err != nil {
		return nil, fmt.Errorf("clear synth dir %q: %w", synthDir, err)
	}
	if err := MaterializeSandbox(manifest, synthDir, p.logger); err != nil {
		return nil, fmt.Errorf("materialize sandbox for %s: %w", loaded.Config.Slug, err)
	}

	// Ensure the workspace pool dir exists (host-side bind source).
	workspaceDir := filepath.Join(loaded.Dir, manifest.WorkspaceSubPath)
	if err := os.MkdirAll(workspaceDir, 0o755); err != nil {
		return nil, fmt.Errorf("create workspace dir %q: %w", workspaceDir, err)
	}

	// Network mode at the DOCKER level: per-endpoint sandbox.network.mode
	// > global config. server.py uses the SYFT_SANDBOX_NET env var below
	// to decide bwrap's --unshare-net, independently of this.
	dockerNetwork := ""
	if loaded.Config.Sandbox.Network.Mode == "none" {
		dockerNetwork = "none"
	}

	// Sandbox-level network mode forwarded to server.py via env var.
	// Falls back to "open" when unset (container has full network; bwrap
	// shares it).
	sandboxNet := loaded.Config.Sandbox.Network.Mode
	if sandboxNet == "" {
		sandboxNet = "open"
	}

	// Workspace scope — agent endpoints default to per-session so each
	// chat gets a fresh scratch dir; one-shot endpoints default to shared.
	workspaceScope := loaded.Config.Sandbox.Workspace.Scope
	if workspaceScope == "" {
		if loaded.Config.Type == string(syfthubapi.EndpointTypeAgent) {
			workspaceScope = "per_session"
		} else {
			workspaceScope = "shared"
		}
	}

	// Allowlist of env var names the handler may see.
	handlerEnvKeys := collectKeys(loaded.HandlerEnv)

	spec := containermode.BuildEndpointSpec(containermode.EndpointSpecConfig{
		Slug:             loaded.Config.Slug,
		SynthCodeDir:     synthDir,
		WorkspacePoolDir: workspaceDir,
		HandlerEnvKeys:   handlerEnvKeys,
		Global:           *p.containerConfig,
		// Container env intentionally narrowed to HandlerEnv (the
		// allowlist) rather than the full PolicyEnv. The host-side
		// policy runner consumes PolicyEnv directly; the container
		// never needs the wider set. Leaving PolicyEnv out of the
		// container's environ closes a leak path: the in-container
		// bwrap child shares the container's PID namespace (kernel
		// procfs-mount rule for userns), so the handler could
		// otherwise read /proc/<server_py_pid>/environ and recover
		// secrets that were deliberately kept out of HandlerEnv.
		EnvVars:     loaded.HandlerEnv,
		InstanceID:  p.instanceID,
		Image:       image,
		NetworkMode: dockerNetwork,
		Sandbox: containermode.SandboxRuntimeConfig{
			AllowSubprocess:   loaded.Config.Sandbox.AllowSubprocess,
			WorkspaceScope:    containermode.WorkspaceScope(workspaceScope),
			NetMode:           containermode.SandboxNetMode(sandboxNet),
			SubprocessEnvKeys: loaded.Config.Sandbox.SubprocessEnv,
		},
	})

	// Append per-endpoint host bind mounts declared in README.md frontmatter.
	for _, m := range loaded.Config.Container.Mounts {
		source, err := expandMountSource(m.Source)
		if err != nil {
			return nil, fmt.Errorf("invalid mount for %s: %w", loaded.Config.Slug, err)
		}
		spec.Mounts = append(spec.Mounts, containermode.Mount{
			Type:     "bind",
			Source:   source,
			Target:   m.Target,
			ReadOnly: m.ReadOnly,
		})
	}

	emit(LoadPhaseStartingContainer, "")
	executor, err := containermode.NewContainerExecutor(ctx, &containermode.ContainerExecutorConfig{
		Runtime:       p.containerRuntime,
		Spec:          spec,
		StartTimeout:  p.containerConfig.StartTimeout,
		Logger:        p.logger,
		PolicyConfigs: loaded.PolicyConfigs,
		StoreConfig:   loaded.StoreConfig,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create container executor for %s: %w", loaded.Config.Slug, err)
	}

	enabled := true
	if loaded.Config.Enabled != nil {
		enabled = *loaded.Config.Enabled
	}

	endpoint := &syfthubapi.Endpoint{
		Slug:               loaded.Config.Slug,
		Name:               loaded.Config.Name,
		Description:        loaded.Config.Description,
		Type:               ToEndpointType(loaded.Config.Type),
		Enabled:            enabled,
		Version:            loaded.Config.Version,
		Readme:             loaded.ReadmeBody,
		AcceptsAttachments: loaded.Config.AcceptsAttachments,
	}

	br := &containerBuildResult{
		loaded:   loaded,
		endpoint: endpoint,
		executor: executor,
	}

	// Wire via SetHandler — agent uses container agent handler, others use executor.
	// For agents with policies the policy gate runs on the HOST via a noop
	// SubprocessExecutor (same mechanism as file mode). policy_manager is not
	// installed inside the container image; it runs in the endpoint's host-side
	// venv so the gate executes before the container session is ever started.
	handlerCfg := syfthubapi.EndpointHandlerConfig{Logger: p.logger}
	if loaded.Config.Type == string(syfthubapi.EndpointTypeAgent) {
		handlerCfg.AgentHandler = containermode.NewContainerAgentHandler(executor, p.logger)
		if len(loaded.PolicyConfigs) > 0 {
			policyPython, err := p.ensurePolicyVenv(loaded)
			if err != nil {
				return nil, fmt.Errorf("failed to set up policy venv for %s: %w", loaded.Config.Slug, err)
			}
			policyExec, noopPath, err := p.buildAgentPolicyExecutor(loaded, policyPython)
			if err != nil {
				return nil, fmt.Errorf("failed to create policy executor for %s: %w", loaded.Config.Slug, err)
			}
			handlerCfg.PolicyExecutor = policyExec
			br.policyExec = policyExec
			br.noopPath = noopPath

			// Wire a manual-review routing recorder so pending policy notices
			// surfaced during this agent's container sessions are captured
			// for later resolution delivery.
			if rec := p.openRoutingRecorder(loaded); rec != nil {
				handlerCfg.RoutingRecorder = rec
				br.routingRecorder = rec
			}
		}
	} else {
		handlerCfg.Executor = executor
	}
	endpoint.SetHandler(handlerCfg)

	p.logger.Info("[CONTAINER-SETUP] Container endpoint ready",
		"slug", loaded.Config.Slug,
		"type", loaded.Config.Type,
	)

	return br, nil
}

// commitContainerBuild applies a containerBuildResult to provider state.
// Caller must hold p.mu.
func (p *Provider) commitContainerBuild(br *containerBuildResult) {
	slug := br.loaded.Config.Slug
	p.executors[slug] = br.executor
	if br.policyExec != nil {
		p.executors[slug+".policy"] = br.policyExec
	}
	if br.noopPath != "" {
		p.noopHandlerPaths[slug] = br.noopPath
	}
	if br.routingRecorder != nil {
		// Close any previous recorder for this slug (selective reload path)
		// before stashing the new one so the prior SQLite handle is released.
		if old, ok := p.routingRecorders[slug]; ok {
			_ = old.Close()
		}
		p.routingRecorders[slug] = br.routingRecorder
	}
}

// buildAgentPolicyExecutor is the non-mutating variant of
// createAgentPolicyExecutor: it writes the noop handler file to disk and
// returns the path + executor, but does not touch p.noopHandlerPaths.
// Caller commits the noopPath via commitContainerBuild.
func (p *Provider) buildAgentPolicyExecutor(loaded *LoadedEndpoint, pythonPath string) (syfthubapi.Executor, string, error) {
	slugHash := nodeops.HashShort(loaded.Config.Slug)
	noopPath := filepath.Join(os.TempDir(), fmt.Sprintf("syfthub_noop_policy_%s.py", slugHash))
	if err := os.WriteFile(noopPath, []byte(noopPolicyHandler), 0600); err != nil {
		return nil, "", fmt.Errorf("failed to write policy check handler: %w", err)
	}

	exec, err := NewSubprocessExecutor(&ExecutorConfig{
		PythonPath:      pythonPath,
		RunnerPath:      noopPath,
		WorkDir:         loaded.Dir,
		Env:             loaded.EnvVars,
		Timeout:         10 * time.Second,
		Logger:          p.logger,
		PolicyConfigs:   loaded.PolicyConfigs,
		StoreConfig:     loaded.StoreConfig,
		UsePolicyRunner: true,
	})
	if err != nil {
		return nil, "", err
	}
	return exec, noopPath, nil
}

// synthDirForSlug returns the per-endpoint synth dir path under the
// provider's synth root. The synth root is created lazily on first call.
// Caller is expected to hold p.mu (Provider mutates p.endpoints around it).
func (p *Provider) synthDirForSlug(slug string) (string, error) {
	root := p.synthRoot()
	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", err
	}
	return filepath.Join(root, slug), nil
}

// collectKeys extracts the env-var NAMES from a list of "KEY=value" strings.
// Used to build the HandlerEnvKeys allowlist passed in the container spec.
func collectKeys(env []string) []string {
	out := make([]string, 0, len(env))
	for _, kv := range env {
		key, _, ok := strings.Cut(kv, "=")
		if !ok || key == "" {
			continue
		}
		out = append(out, key)
	}
	return out
}

// expandMountSource expands ~ and $VAR references in a mount source path.
// Returns an error if expansion produces an empty or relative path.
func expandMountSource(source string) (string, error) {
	if strings.HasPrefix(source, "~/") || source == "~" {
		home, err := os.UserHomeDir()
		if err == nil {
			source = home + source[1:]
		}
	}
	expanded := os.ExpandEnv(source)
	if expanded == "" {
		return "", fmt.Errorf("mount source %q expanded to empty string", source)
	}
	return expanded, nil
}
