package filemode

import (
	"context"
	"crypto/sha256"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

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

	endpoints        []*syfthubapi.Endpoint
	executors        map[string]syfthubapi.Executor
	noopHandlerPaths map[string]string // slug -> temp file path for noop policy handlers
	mu               sync.RWMutex

	onReload  func([]*syfthubapi.Endpoint)
	running   bool
	stopCh    chan struct{}
	stoppedCh chan struct{}
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
		basePath:         cfg.BasePath,
		pythonPath:       pythonPath,
		watchEnabled:     cfg.WatchEnabled,
		debounce:         debounce,
		logger:           logger,
		loader:           loader,
		venvManager:      venvManager,
		embeddedPython:   embeddedPython,
		executors:        make(map[string]syfthubapi.Executor),
		noopHandlerPaths: make(map[string]string),
		onReload:         cfg.OnReload,
		stopCh:           make(chan struct{}),
		stoppedCh:        make(chan struct{}),
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
			// Fall back to system Python
		} else {
			p.pythonPath = pythonPath
			// Update venv manager with embedded Python path
			p.venvManager, err = NewVenvManager(&VenvConfig{
				PythonPath: pythonPath,
				Logger:     p.logger,
			})
			if err != nil {
				p.logger.Warn("failed to recreate venv manager with embedded Python", "error", err)
			}
		}
	}

	loadedEndpoints, err := p.loader.LoadAll()
	if err != nil {
		return nil, err
	}

	endpoints := make([]*syfthubapi.Endpoint, 0, len(loadedEndpoints))

	p.mu.Lock()
	defer p.mu.Unlock()

	// Reset executor map without closing — the registry still references
	// the old executors and will close stale ones in ReplaceFileBased.
	p.executors = make(map[string]syfthubapi.Executor)
	// Keep p.noopHandlerPaths intact: createEndpoint overwrites entries for
	// recreated slugs, and cleanupResources (from Stop) deletes all files.

	for _, loaded := range loadedEndpoints {
		endpoint, err := p.createEndpoint(loaded)
		if err != nil {
			p.logger.Warn("failed to create endpoint",
				"slug", loaded.Config.Slug,
				"error", err,
			)
			continue
		}
		endpoints = append(endpoints, endpoint)
	}

	p.endpoints = endpoints
	return endpoints, nil
}

// createEndpoint creates an Endpoint from a LoadedEndpoint.
func (p *Provider) createEndpoint(loaded *LoadedEndpoint) (*syfthubapi.Endpoint, error) {
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
		Slug:        loaded.Config.Slug,
		Name:        loaded.Config.Name,
		Description: loaded.Config.Description,
		Type:        ToEndpointType(loaded.Config.Type),
		Enabled:     enabled,
		Version:     loaded.Config.Version,
		Readme:      loaded.ReadmeBody,
	}

	// Agent endpoints use a long-lived subprocess bridge (not one-shot executor)
	if loaded.Config.Type == string(syfthubapi.EndpointTypeAgent) {
		handler := NewAgentHandler(&AgentHandlerConfig{
			PythonPath: pythonPath,
			RunnerPath: loaded.RunnerPath,
			WorkDir:    loaded.Dir,
			Env:        loaded.EnvVars,
			Logger:     p.logger,
		})
		endpoint.SetAgentHandler(handler)
		p.logger.Info("[AGENT-SETUP] Agent handler created",
			"slug", loaded.Config.Slug,
		)

		// If policies are configured, create a dedicated policy executor.
		// Agent handlers run as long-lived subprocesses and cannot use the standard
		// SubprocessExecutor for invocation, but policies still need to be enforced
		// before the handler starts. A noop handler is used so the policy_manager.runner
		// only evaluates policies and returns the result.
		if len(loaded.PolicyConfigs) > 0 {
			// Write the noop handler to a temp directory with a stable name
			// derived from the slug so hot-reloads reuse the same file.
			slugHash := fmt.Sprintf("%x", sha256.Sum256([]byte(loaded.Config.Slug)))[:12]
			noopPath := filepath.Join(os.TempDir(), fmt.Sprintf("syfthub_noop_policy_%s.py", slugHash))
			if err := os.WriteFile(noopPath, []byte(noopPolicyHandler), 0600); err != nil {
				p.logger.Error("[AGENT-SETUP] Failed to write policy check handler",
					"slug", loaded.Config.Slug, "path", noopPath, "error", err)
				return nil, fmt.Errorf("failed to write policy check handler: %w", err)
			}
			p.noopHandlerPaths[loaded.Config.Slug] = noopPath

			policyExec, err := NewSubprocessExecutor(&ExecutorConfig{
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
				p.logger.Error("[AGENT-SETUP] Failed to create policy executor",
					"slug", loaded.Config.Slug, "error", err)
				return nil, err
			}

			endpoint.SetPolicyExecutor(policyExec)
			p.executors[loaded.Config.Slug+".policy"] = policyExec

			p.logger.Info("[AGENT-SETUP] POLICY ENFORCEMENT ENABLED for agent endpoint",
				"slug", loaded.Config.Slug,
				"policy_count", len(loaded.PolicyConfigs),
			)
		} else {
			p.logger.Warn("[AGENT-SETUP] NO POLICY ENFORCEMENT for agent endpoint (no policies configured)",
				"slug", loaded.Config.Slug,
			)
		}

		return endpoint, nil
	}

	// Model/DataSource endpoints use one-shot subprocess executor
	usePolicyRunner := len(loaded.PolicyConfigs) > 0
	p.logger.Info("[POLICY-SETUP] Creating executor",
		"slug", loaded.Config.Slug,
		"use_policy_runner", usePolicyRunner,
		"python_path", pythonPath,
		"runner_path", loaded.RunnerPath,
		"timeout", loaded.Config.Runtime.Timeout,
	)

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
		p.logger.Error("[POLICY-SETUP] Failed to create executor",
			"slug", loaded.Config.Slug,
			"error", err,
		)
		return nil, err
	}

	p.executors[loaded.Config.Slug] = executor

	if usePolicyRunner {
		p.logger.Info("[POLICY-SETUP] POLICY ENFORCEMENT ENABLED for endpoint",
			"slug", loaded.Config.Slug,
			"policy_count", len(loaded.PolicyConfigs),
		)
	} else {
		p.logger.Warn("[POLICY-SETUP] NO POLICY ENFORCEMENT for endpoint (no policies configured)",
			"slug", loaded.Config.Slug,
		)
	}

	endpoint.SetExecutor(executor)

	return endpoint, nil
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

		endpoint, err := p.createEndpoint(loaded)
		if err != nil {
			p.mu.Unlock()
			p.logger.Warn("failed to recreate endpoint",
				"slug", slug,
				"error", err,
			)
			continue
		}

		// Insert the new endpoint, replacing any existing one with the same slug.
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

	p.mu.RLock()
	endpoints := make([]*syfthubapi.Endpoint, len(p.endpoints))
	copy(endpoints, p.endpoints)
	p.mu.RUnlock()

	if p.onReload != nil {
		p.onReload(endpoints)
	}
}

// removeEndpointLocked removes the executor references for the given slug
// from the provider's internal maps. It does NOT close executors — the
// registry owns executor lifecycle and closes stale ones in ReplaceFileBased.
// Caller must hold p.mu.
func (p *Provider) removeEndpointLocked(slug string) {
	delete(p.executors, slug)
	delete(p.executors, slug+".policy")
	if path, ok := p.noopHandlerPaths[slug]; ok {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			p.logger.Warn("failed to remove noop handler", "slug", slug, "error", err)
		}
		delete(p.noopHandlerPaths, slug)
	}
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
