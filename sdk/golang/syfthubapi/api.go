package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"golang.org/x/sync/errgroup"
)

// Transport interface is implemented in transport package.
type Transport interface {
	Start(ctx context.Context) error
	Stop(ctx context.Context) error
	SetRequestHandler(handler RequestHandler)
}

// RequestHandler handles incoming requests.
type RequestHandler func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error)

// LifecycleHook is a function called during startup or shutdown.
type LifecycleHook func(ctx context.Context) error

// SyftAPI is the main application for building SyftHub Spaces.
type SyftAPI struct {
	// config holds the configuration.
	config *Config

	// logger is the structured logger.
	logger *slog.Logger

	// registry manages registered endpoints.
	registry *EndpointRegistry

	// transport handles HTTP or NATS communication.
	transport Transport

	// heartbeatManager manages heartbeat signals.
	heartbeatManager HeartbeatManager

	// fileProvider manages file-based endpoints.
	fileProvider FileProvider

	// authClient handles token verification with SyftHub backend.
	authClient *AuthClient

	// syncClient handles endpoint synchronization with SyftHub backend.
	syncClient *SyncClient

	// processor handles request execution.
	processor *RequestProcessor

	// middleware chain.
	middleware []Middleware

	// lifecycle hooks.
	startupHooks  []LifecycleHook
	shutdownHooks []LifecycleHook

	// shutdown coordination.
	shutdownCh chan struct{}

	// mu protects concurrent access.
	mu sync.RWMutex
}

// HeartbeatManager interface for heartbeat management.
type HeartbeatManager interface {
	Start(ctx context.Context) error
	Stop(ctx context.Context) error
}

// FileProvider interface for file-based endpoint management.
type FileProvider interface {
	Start(ctx context.Context) error
	Stop(ctx context.Context) error
	LoadEndpoints() ([]*Endpoint, error)
}

// New creates a new SyftAPI instance with the given options.
func New(opts ...Option) *SyftAPI {
	config := DefaultConfig()

	// Load from environment first (warn on error but continue - options can override)
	if err := config.LoadFromEnv(); err != nil {
		slog.Warn("failed to load config from environment", "error", err)
	}

	// Apply options (override env)
	for _, opt := range opts {
		opt(config)
	}

	// Setup logger
	var level slog.Level
	switch config.LogLevel {
	case "DEBUG":
		level = slog.LevelDebug
	case "WARNING", "WARN":
		level = slog.LevelWarn
	case "ERROR":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	logger := slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{
		Level: level,
	}))

	// Create auth client for token verification
	slogLogger := NewSlogLogger(logger)
	authClient := NewAuthClient(config.SyftHubURL, config.APIKey, slogLogger)

	// Create sync client for endpoint synchronization
	syncClient := NewSyncClient(config.SyftHubURL, config.APIKey, logger)

	// Create endpoint registry
	registry := NewEndpointRegistry()

	// Create request processor
	// Note: Policy enforcement is handled by Python policy_manager.runner
	processor := NewRequestProcessor(&ProcessorConfig{
		Registry:   registry,
		AuthClient: authClient,
		Logger:     logger,
	})

	return &SyftAPI{
		config:     config,
		logger:     logger,
		registry:   registry,
		authClient: authClient,
		syncClient: syncClient,
		processor:  processor,
		shutdownCh: make(chan struct{}),
	}
}

// DataSource starts building a data source endpoint.
func (api *SyftAPI) DataSource(slug string) *DataSourceBuilder {
	builder := &DataSourceBuilder{
		api: api,
		endpoint: &Endpoint{
			Slug:    slug,
			Type:    EndpointTypeDataSource,
			Enabled: true,
		},
	}

	if err := validateSlug(slug); err != nil {
		builder.err = err
	}

	return builder
}

// Model starts building a model endpoint.
func (api *SyftAPI) Model(slug string) *ModelBuilder {
	builder := &ModelBuilder{
		api: api,
		endpoint: &Endpoint{
			Slug:    slug,
			Type:    EndpointTypeModel,
			Enabled: true,
		},
	}

	if err := validateSlug(slug); err != nil {
		builder.err = err
	}

	return builder
}

// registerEndpoint registers an endpoint with the API.
func (api *SyftAPI) registerEndpoint(endpoint *Endpoint) error {
	api.logger.Info("registering endpoint",
		"slug", endpoint.Slug,
		"type", endpoint.Type,
		"name", endpoint.Name,
	)
	return api.registry.Register(endpoint)
}

// Use adds middleware to the processing chain.
func (api *SyftAPI) Use(mw Middleware) {
	api.mu.Lock()
	defer api.mu.Unlock()
	api.middleware = append(api.middleware, mw)
}

// OnStartup registers a startup hook.
func (api *SyftAPI) OnStartup(hook LifecycleHook) {
	api.mu.Lock()
	defer api.mu.Unlock()
	api.startupHooks = append(api.startupHooks, hook)
}

// OnShutdown registers a shutdown hook.
func (api *SyftAPI) OnShutdown(hook LifecycleHook) {
	api.mu.Lock()
	defer api.mu.Unlock()
	api.shutdownHooks = append(api.shutdownHooks, hook)
}

// Config returns the current configuration.
func (api *SyftAPI) Config() *Config {
	return api.config
}

// Logger returns the logger.
func (api *SyftAPI) Logger() *slog.Logger {
	return api.logger
}

// Endpoints returns all registered endpoints.
func (api *SyftAPI) Endpoints() []*Endpoint {
	return api.registry.List()
}

// GetEndpoint retrieves an endpoint by slug.
func (api *SyftAPI) GetEndpoint(slug string) (*Endpoint, bool) {
	return api.registry.Get(slug)
}

// Run starts the SyftAPI server and blocks until shutdown.
func (api *SyftAPI) Run(ctx context.Context) error {
	// Validate configuration
	if err := api.config.Validate(); err != nil {
		return fmt.Errorf("invalid configuration: %w", err)
	}

	// Setup signal handling
	ctx, cancel := signal.NotifyContext(ctx, syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	api.logger.Info("starting SyftAPI",
		"syfthub_url", api.config.SyftHubURL,
		"space_url", api.config.SpaceURL,
		"tunnel_mode", api.config.IsTunnelMode(),
	)

	// Run startup hooks
	for _, hook := range api.startupHooks {
		if err := hook(ctx); err != nil {
			return fmt.Errorf("startup hook failed: %w", err)
		}
	}

	// Initialize file-based endpoints if configured and not already loaded
	// Skip loading if endpoints are already in the registry (loaded by example before Run())
	if api.config.EndpointsPath != "" && api.fileProvider != nil {
		existingFileBased := 0
		for _, ep := range api.registry.List() {
			if ep.IsFileBased() {
				existingFileBased++
			}
		}

		if existingFileBased == 0 {
			endpoints, err := api.fileProvider.LoadEndpoints()
			if err != nil {
				api.logger.Warn("failed to load file-based endpoints", "error", err)
			} else {
				api.registry.ReplaceFileBased(endpoints)
				api.logger.Info("loaded file-based endpoints", "count", len(endpoints))
			}
		} else {
			api.logger.Debug("file-based endpoints already loaded", "count", existingFileBased)
		}
	}

	// Sync endpoints with SyftHub
	if err := api.syncEndpoints(ctx); err != nil {
		api.logger.Warn("failed to sync endpoints", "error", err)
	}

	// Setup transport
	if err := api.setupTransport(); err != nil {
		return fmt.Errorf("failed to setup transport: %w", err)
	}
	api.transport.SetRequestHandler(api.handleRequest)

	// Start components concurrently
	g, gCtx := errgroup.WithContext(ctx)

	// Start heartbeat
	if api.config.HeartbeatEnabled && api.heartbeatManager != nil {
		g.Go(func() error {
			return api.heartbeatManager.Start(gCtx)
		})
	}

	// Start file watcher
	if api.config.WatchEnabled && api.fileProvider != nil {
		g.Go(func() error {
			return api.fileProvider.Start(gCtx)
		})
	}

	// Start transport
	g.Go(func() error {
		return api.transport.Start(gCtx)
	})

	// Wait for shutdown signal or error
	err := g.Wait()

	// Run shutdown
	api.shutdown(context.Background())

	return err
}

// shutdown performs graceful shutdown.
func (api *SyftAPI) shutdown(ctx context.Context) {
	api.logger.Info("shutting down SyftAPI")

	// Stop file provider
	if api.fileProvider != nil {
		if err := api.fileProvider.Stop(ctx); err != nil {
			api.logger.Warn("error stopping file provider", "error", err)
		}
	}

	// Stop heartbeat
	if api.heartbeatManager != nil {
		if err := api.heartbeatManager.Stop(ctx); err != nil {
			api.logger.Warn("error stopping heartbeat", "error", err)
		}
	}

	// Stop transport
	if api.transport != nil {
		if err := api.transport.Stop(ctx); err != nil {
			api.logger.Warn("error stopping transport", "error", err)
		}
	}

	// Close all endpoint executors
	for _, ep := range api.registry.List() {
		if ep.executor != nil {
			if err := ep.executor.Close(); err != nil {
				api.logger.Warn("error closing executor", "endpoint", ep.Slug, "error", err)
			}
		}
	}

	// Run shutdown hooks
	for _, hook := range api.shutdownHooks {
		if err := hook(ctx); err != nil {
			api.logger.Warn("shutdown hook error", "error", err)
		}
	}

	api.logger.Info("SyftAPI shutdown complete")
}

// Shutdown initiates graceful shutdown.
func (api *SyftAPI) Shutdown(ctx context.Context) error {
	close(api.shutdownCh)
	api.shutdown(ctx)
	return nil
}

// setupTransport creates the appropriate transport based on config.
func (api *SyftAPI) setupTransport() error {
	if api.config.IsTunnelMode() {
		// NATS transport will be set externally or created here
		api.logger.Info("tunnel mode enabled",
			"username", api.config.GetTunnelUsername(),
		)
	} else {
		// HTTP transport will be created in transport package
		api.logger.Info("HTTP mode enabled",
			"host", api.config.ServerHost,
			"port", api.config.ServerPort,
		)
	}
	return nil
}

// syncEndpoints sends endpoints to SyftHub backend.
func (api *SyftAPI) syncEndpoints(ctx context.Context) error {
	endpoints := api.registry.List()
	if len(endpoints) == 0 {
		api.logger.Debug("no endpoints to sync")
		return nil
	}

	// Build endpoint infos with visibility and connect info
	infos := make([]EndpointInfo, 0, len(endpoints))
	for _, ep := range endpoints {
		if !ep.Enabled {
			continue
		}

		info := ep.Info()
		// Set visibility (default to public)
		info.Visibility = "public"
		// Set connection info pointing to this space
		info.Connect = []ConnectionInfo{
			{
				Type:   "http",
				Config: map[string]any{"url": api.config.SpaceURL},
			},
		}
		// Ensure version is semver format
		if info.Version == "" {
			info.Version = "0.1.0"
		}

		infos = append(infos, info)
	}

	api.logger.Info("syncing endpoints with SyftHub", "count", len(infos))

	// First update user's domain
	if err := api.syncClient.UpdateDomain(ctx, api.config.SpaceURL); err != nil {
		api.logger.Warn("failed to update domain", "error", err)
		// Continue with sync even if domain update fails
	}

	// Sync endpoints
	result, err := api.syncClient.SyncEndpoints(ctx, infos)
	if err != nil {
		return err
	}

	api.logger.Info("endpoints synced with SyftHub",
		"synced", result.Synced,
		"deleted", result.Deleted,
	)

	return nil
}

// handleRequest processes an incoming request by delegating to the processor.
func (api *SyftAPI) handleRequest(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
	return api.processor.Process(ctx, req)
}

// SetTransport sets the transport (used by transport package).
func (api *SyftAPI) SetTransport(t Transport) {
	api.transport = t
}

// SetHeartbeatManager sets the heartbeat manager.
func (api *SyftAPI) SetHeartbeatManager(hm HeartbeatManager) {
	api.heartbeatManager = hm
}

// SetFileProvider sets the file provider.
func (api *SyftAPI) SetFileProvider(fp FileProvider) {
	api.fileProvider = fp
}

// SetLogHook sets the request log hook callback.
// The hook is called after each request is processed with the full log entry.
func (api *SyftAPI) SetLogHook(hook RequestLogHook) {
	if api.processor != nil {
		api.processor.SetLogHook(hook)
	}
}

// SyncEndpoints triggers a re-sync of all endpoints with SyftHub.
// This should be called after endpoints are modified (e.g., after hot-reload).
func (api *SyftAPI) SyncEndpoints(ctx context.Context) error {
	return api.syncEndpoints(ctx)
}

// SyncEndpointsAsync triggers a re-sync in a background goroutine.
// This is useful for non-blocking updates like toggling endpoint enabled status.
// Errors are logged but not returned.
func (api *SyftAPI) SyncEndpointsAsync() {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if err := api.syncEndpoints(ctx); err != nil {
			api.logger.Warn("async endpoint sync failed", "error", err)
		}
	}()
}

// Registry returns the endpoint registry.
func (api *SyftAPI) Registry() *EndpointRegistry {
	return api.registry
}

// unmarshalJSON is a helper to unmarshal JSON.
func unmarshalJSON(data json.RawMessage, v any) error {
	return json.Unmarshal(data, v)
}
