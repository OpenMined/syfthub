// Package app provides the core application setup for syfthub-desktop.
package app

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/heartbeat"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"

	"github.com/openmined/syfthub-desktop-gui/internal/logs"
)

// App represents the syfthub-desktop application.
type App struct {
	api                *syfthubapi.SyftAPI
	provider           *filemode.Provider
	logger             *slog.Logger
	config             *Config
	logStore           *logs.FileLogStore
	onEndpointsChanged func()                       // External notification callback for file watcher events
	onNewLog           func(*syfthubapi.RequestLog) // External notification callback for new log entries
}

// Config holds application configuration.
type Config struct {
	EndpointsPath     string
	PythonPath        string
	UseEmbeddedPython bool // If true, download and use standalone Python
	WatchEnabled      bool
	WatchDebounce     time.Duration
	LogLevel          string
}

// DefaultConfig returns configuration with sensible defaults.
func DefaultConfig() *Config {
	return &Config{
		EndpointsPath:     "./endpoints",
		PythonPath:        "",
		UseEmbeddedPython: true, // Use embedded Python by default
		WatchEnabled:      true,
		WatchDebounce:     time.Second,
		LogLevel:          "INFO",
	}
}

// ConfigFromEnv creates configuration from environment variables.
func ConfigFromEnv() *Config {
	cfg := DefaultConfig()

	if v := os.Getenv("ENDPOINTS_PATH"); v != "" {
		cfg.EndpointsPath = v
	}
	if v := os.Getenv("PYTHON_PATH"); v != "" {
		cfg.PythonPath = v
		// If custom Python path is set, disable embedded Python
		cfg.UseEmbeddedPython = false
	}
	if v := os.Getenv("USE_EMBEDDED_PYTHON"); v == "false" {
		cfg.UseEmbeddedPython = false
	}
	if v := os.Getenv("LOG_LEVEL"); v != "" {
		cfg.LogLevel = v
	}
	if v := os.Getenv("WATCH_ENABLED"); v == "false" {
		cfg.WatchEnabled = false
	}

	return cfg
}

// New creates a new App instance.
func New(cfg *Config) (*App, error) {
	if cfg == nil {
		cfg = ConfigFromEnv()
	}

	// Resolve endpoints path to absolute
	endpointsPath, err := filepath.Abs(cfg.EndpointsPath)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve endpoints path: %w", err)
	}
	cfg.EndpointsPath = endpointsPath

	// Create the SyftAPI instance
	api := syfthubapi.New(
		syfthubapi.WithLogLevel(cfg.LogLevel),
		syfthubapi.WithEndpointsPath(cfg.EndpointsPath),
		syfthubapi.WithWatchEnabled(cfg.WatchEnabled),
		syfthubapi.WithWatchDebounce(cfg.WatchDebounce.Seconds()),
	)

	logger := api.Logger()

	// Create log store
	logStorePath, err := logs.DefaultLogStorePath()
	if err != nil {
		logger.Warn("failed to get default log store path, using temp directory", "error", err)
		logStorePath = filepath.Join(os.TempDir(), "syfthub-desktop", "logs")
	}

	logStore, err := logs.NewFileLogStore(logStorePath)
	if err != nil {
		logger.Warn("failed to create log store", "error", err)
		// Continue without log store - it's not critical
	}

	app := &App{
		api:      api,
		logger:   logger,
		config:   cfg,
		logStore: logStore,
	}

	// Set up log hook if log store was created
	if logStore != nil {
		api.SetLogHook(app.handleRequestLog)
	}

	return app, nil
}

// handleRequestLog is the callback invoked for each processed request.
func (a *App) handleRequestLog(ctx context.Context, log *syfthubapi.RequestLog) {
	// Write to log store
	if a.logStore != nil {
		if err := a.logStore.Write(ctx, log); err != nil {
			a.logger.Warn("failed to write request log", "error", err)
		}
	}

	// Notify external listeners (Wails GUI)
	if a.onNewLog != nil {
		a.onNewLog(log)
	}
}

// SetOnEndpointsChanged sets a callback that will be invoked when the file
// watcher detects changes and endpoints are reloaded. This allows external
// components (like the Wails GUI) to be notified of changes.
func (a *App) SetOnEndpointsChanged(callback func()) {
	a.onEndpointsChanged = callback
}

// SetOnNewLog sets a callback that will be invoked when a new request log is created.
// This allows external components (like the Wails GUI) to be notified of new logs.
func (a *App) SetOnNewLog(callback func(*syfthubapi.RequestLog)) {
	a.onNewLog = callback
}

// GetLogs retrieves logs for an endpoint with optional filters.
func (a *App) GetLogs(ctx context.Context, slug string, opts *syfthubapi.LogQueryOptions) (*syfthubapi.LogQueryResult, error) {
	if a.logStore == nil {
		return &syfthubapi.LogQueryResult{
			Logs:    []*syfthubapi.RequestLog{},
			Total:   0,
			HasMore: false,
		}, nil
	}
	return a.logStore.Query(ctx, slug, opts)
}

// GetLogStats returns aggregate statistics for an endpoint's logs.
func (a *App) GetLogStats(ctx context.Context, slug string) (*syfthubapi.LogStats, error) {
	if a.logStore == nil {
		return &syfthubapi.LogStats{}, nil
	}
	return a.logStore.GetStats(ctx, slug)
}

// GetLogByID retrieves a specific log entry by ID.
func (a *App) GetLogByID(ctx context.Context, slug, logID string) (*syfthubapi.RequestLog, error) {
	if a.logStore == nil {
		return nil, fmt.Errorf("log store not initialized")
	}
	return a.logStore.GetLogByID(ctx, slug, logID)
}

// DeleteLogs deletes all logs for an endpoint.
func (a *App) DeleteLogs(ctx context.Context, slug string) error {
	if a.logStore == nil {
		return nil
	}
	return a.logStore.DeleteLogs(ctx, slug)
}

// Setup initializes the application components.
func (a *App) Setup(ctx context.Context) error {
	apiConfig := a.api.Config()

	// Log embedded Python status
	if a.config.UseEmbeddedPython {
		a.logger.Info("embedded Python enabled - will download if needed")
	} else if a.config.PythonPath != "" {
		a.logger.Info("using custom Python", "path", a.config.PythonPath)
	} else {
		a.logger.Info("using system Python")
	}

	// Create file provider
	provider, err := filemode.NewProvider(&filemode.ProviderConfig{
		BasePath:          a.config.EndpointsPath,
		PythonPath:        a.config.PythonPath,
		UseEmbeddedPython: a.config.UseEmbeddedPython,
		WatchEnabled:      a.config.WatchEnabled,
		Debounce:          a.config.WatchDebounce,
		Logger:            a.logger,
		OnReload:          a.handleReload,
	})
	if err != nil {
		return fmt.Errorf("failed to create file provider: %w", err)
	}
	a.provider = provider
	a.api.SetFileProvider(provider)

	// Load initial endpoints
	endpoints, err := provider.LoadEndpoints()
	if err != nil {
		a.logger.Warn("failed to load endpoints", "error", err)
	} else {
		a.api.Registry().ReplaceFileBased(endpoints)
		a.logger.Info("loaded endpoints", "count", len(endpoints))
		for _, ep := range endpoints {
			a.logger.Info("endpoint registered",
				"slug", ep.Slug,
				"type", ep.Type,
				"name", ep.Name,
			)
		}
	}

	// Setup transport based on mode
	t, err := a.setupTransport(ctx, apiConfig)
	if err != nil {
		return fmt.Errorf("failed to setup transport: %w", err)
	}
	a.api.SetTransport(t)

	// Setup heartbeat if enabled
	if apiConfig.HeartbeatEnabled {
		hbManager := heartbeat.NewManager(&heartbeat.Config{
			BaseURL:            apiConfig.SyftHubURL,
			APIKey:             apiConfig.APIKey,
			SpaceURL:           apiConfig.SpaceURL,
			TTLSeconds:         apiConfig.HeartbeatTTLSeconds,
			IntervalMultiplier: apiConfig.HeartbeatIntervalMultiplier,
			Logger:             a.logger,
		})
		a.api.SetHeartbeatManager(hbManager)
	}

	// Register lifecycle hooks
	a.api.OnStartup(func(ctx context.Context) error {
		a.logger.Info("syfthub-desktop starting up")
		return nil
	})

	a.api.OnShutdown(func(ctx context.Context) error {
		a.logger.Info("syfthub-desktop shutting down")
		return nil
	})

	return nil
}

// Run starts the application.
func (a *App) Run(ctx context.Context) error {
	apiConfig := a.api.Config()

	a.logger.Info("starting syfthub-desktop",
		"mode", a.getModeString(apiConfig),
		"endpoints_path", a.config.EndpointsPath,
		"watch_enabled", a.config.WatchEnabled,
	)

	return a.api.Run(ctx)
}

// Shutdown gracefully shuts down the application.
func (a *App) Shutdown(ctx context.Context) error {
	// Close log store first to flush pending writes
	if a.logStore != nil {
		if err := a.logStore.Close(); err != nil {
			a.logger.Warn("error closing log store", "error", err)
		}
	}
	return a.api.Shutdown(ctx)
}

// handleReload is called when endpoints are reloaded.
func (a *App) handleReload(endpoints []*syfthubapi.Endpoint) {
	a.logger.Info("endpoints reloaded", "count", len(endpoints))
	a.api.Registry().ReplaceFileBased(endpoints)

	// Re-sync with SyftHub
	if err := a.api.SyncEndpoints(context.Background()); err != nil {
		a.logger.Error("failed to re-sync endpoints", "error", err)
	} else {
		a.logger.Info("endpoints synced with SyftHub")
	}

	// Notify external listeners (Wails GUI)
	if a.onEndpointsChanged != nil {
		a.onEndpointsChanged()
	}
}

// setupTransport creates the appropriate transport based on configuration.
func (a *App) setupTransport(ctx context.Context, cfg *syfthubapi.Config) (syfthubapi.Transport, error) {
	if cfg.IsTunnelMode() {
		return a.setupNATSTransport(ctx, cfg)
	}
	return a.setupHTTPTransport(cfg)
}

// setupNATSTransport creates a NATS transport for tunnel mode.
func (a *App) setupNATSTransport(ctx context.Context, cfg *syfthubapi.Config) (syfthubapi.Transport, error) {
	a.logger.Info("setting up NATS transport")

	// Get NATS credentials from SyftHub
	authClient := syfthubapi.NewAuthClient(cfg.SyftHubURL, cfg.APIKey, &slogAdapter{a.logger})

	natsCreds, err := authClient.GetNATSCredentials(ctx, cfg.GetTunnelUsername())
	if err != nil {
		a.logger.Warn("failed to get NATS credentials, using fallback", "error", err)
		natsCreds = &syfthubapi.NATSCredentials{
			URL:     getEnvOrDefault("NATS_URL", "nats://localhost:4222"),
			Token:   getEnvOrDefault("NATS_TOKEN", "test-token"),
			Subject: fmt.Sprintf("syfthub.spaces.%s", cfg.GetTunnelUsername()),
		}
	}

	a.logger.Info("NATS credentials obtained",
		"url", natsCreds.URL,
		"subject", natsCreds.Subject,
	)

	return transport.NewNATSTransport(&transport.Config{
		SpaceURL:        cfg.SpaceURL,
		NATSCredentials: natsCreds,
		Logger:          a.logger,
	})
}

// setupHTTPTransport creates an HTTP transport.
func (a *App) setupHTTPTransport(cfg *syfthubapi.Config) (syfthubapi.Transport, error) {
	a.logger.Info("setting up HTTP transport",
		"host", cfg.ServerHost,
		"port", cfg.ServerPort,
	)

	return transport.NewHTTPTransport(&transport.Config{
		SpaceURL: cfg.SpaceURL,
		Host:     cfg.ServerHost,
		Port:     cfg.ServerPort,
		Logger:   a.logger,
	})
}

// getModeString returns a human-readable mode description.
func (a *App) getModeString(cfg *syfthubapi.Config) string {
	if cfg.IsTunnelMode() {
		return fmt.Sprintf("NATS Tunnel (user: %s)", cfg.GetTunnelUsername())
	}
	return fmt.Sprintf("HTTP (port: %d)", cfg.ServerPort)
}

// slogAdapter adapts slog.Logger to the Logger interface.
type slogAdapter struct {
	*slog.Logger
}

func (s *slogAdapter) Debug(msg string, args ...any) { s.Logger.Debug(msg, args...) }
func (s *slogAdapter) Info(msg string, args ...any)  { s.Logger.Info(msg, args...) }
func (s *slogAdapter) Warn(msg string, args ...any)  { s.Logger.Warn(msg, args...) }
func (s *slogAdapter) Error(msg string, args ...any) { s.Logger.Error(msg, args...) }

func getEnvOrDefault(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// EndpointInfo provides endpoint information for the GUI.
type EndpointInfo struct {
	Slug        string
	Name        string
	Description string
	Type        string
	Enabled     bool
	Version     string
}

// HasPolicies returns true if the endpoint has policies configured.
func (e *EndpointInfo) HasPolicies() bool {
	// This is a simplified check; in reality we'd check the executor
	return false
}

// GetEndpoints returns information about all loaded endpoints.
func (a *App) GetEndpoints() []EndpointInfo {
	if a.api == nil {
		return nil
	}

	registry := a.api.Registry()
	if registry == nil {
		return nil
	}

	endpoints := registry.List()
	result := make([]EndpointInfo, 0, len(endpoints))

	for _, ep := range endpoints {
		result = append(result, EndpointInfo{
			Slug:        ep.Slug,
			Name:        ep.Name,
			Description: ep.Description,
			Type:        string(ep.Type),
			Enabled:     ep.Enabled,
			Version:     ep.Version,
		})
	}

	return result
}

// ReloadEndpoints reloads endpoints from the filesystem.
func (a *App) ReloadEndpoints() error {
	if a.provider == nil {
		return fmt.Errorf("provider not initialized")
	}

	endpoints, err := a.provider.LoadEndpoints()
	if err != nil {
		return fmt.Errorf("failed to load endpoints: %w", err)
	}

	a.api.Registry().ReplaceFileBased(endpoints)
	a.logger.Info("endpoints reloaded", "count", len(endpoints))

	// Re-sync with SyftHub
	if err := a.api.SyncEndpoints(context.Background()); err != nil {
		a.logger.Warn("failed to sync endpoints", "error", err)
	}

	return nil
}

// SetEndpointEnabled updates the enabled status of an endpoint in the registry
// without triggering a full reload. This is a fast O(1) operation.
func (a *App) SetEndpointEnabled(slug string, enabled bool) bool {
	if a.api == nil {
		return false
	}
	return a.api.Registry().SetEnabled(slug, enabled)
}

// SyncEndpointsAsync triggers a background sync of endpoints with SyftHub.
// This is non-blocking and suitable for use after quick updates like toggling enabled.
func (a *App) SyncEndpointsAsync() {
	if a.api == nil {
		return
	}
	a.api.SyncEndpointsAsync()
}
