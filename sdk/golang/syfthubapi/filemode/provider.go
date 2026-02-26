package filemode

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

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

	endpoints []*syfthubapi.Endpoint
	executors map[string]syfthubapi.Executor
	mu        sync.RWMutex

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
		basePath:       cfg.BasePath,
		pythonPath:     pythonPath,
		watchEnabled:   cfg.WatchEnabled,
		debounce:       debounce,
		logger:         logger,
		loader:         loader,
		venvManager:    venvManager,
		embeddedPython: embeddedPython,
		executors:      make(map[string]syfthubapi.Executor),
		onReload:       cfg.OnReload,
		stopCh:         make(chan struct{}),
		stoppedCh:      make(chan struct{}),
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

	// Close all executors
	p.mu.Lock()
	for slug, exec := range p.executors {
		if err := exec.Close(); err != nil {
			p.logger.Warn("failed to close executor",
				"slug", slug,
				"error", err,
			)
		}
	}
	p.executors = make(map[string]syfthubapi.Executor)
	p.mu.Unlock()

	select {
	case <-p.stoppedCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
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

	// Close old executors
	for slug, exec := range p.executors {
		if err := exec.Close(); err != nil {
			p.logger.Warn("failed to close old executor",
				"slug", slug,
				"error", err,
			)
		}
	}
	p.executors = make(map[string]syfthubapi.Executor)

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

	// Create executor
	// Use policy runner when policies are configured
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
		Policies:    loaded.PolicyConfigs,
	}

	// Set the executor for file-based execution
	endpoint.SetExecutor(executor)

	return endpoint, nil
}

// handleReload handles file change notifications.
func (p *Provider) handleReload(affectedDirs []string) {
	p.logger.Info("reloading endpoints",
		"affected", len(affectedDirs),
	)

	endpoints, err := p.LoadEndpoints()
	if err != nil {
		p.logger.Error("failed to reload endpoints", "error", err)
		return
	}

	if p.onReload != nil {
		p.onReload(endpoints)
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
