// Package main provides the Wails binding layer for syfthub-desktop-gui.
// This file implements the Facade pattern over the core syfthubapi SDK,
// exposing thread-safe methods that can be called from the React frontend.
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/joho/godotenv"
	"github.com/openmined/syfthub-desktop-gui/internal/app"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// App is the main application struct that bridges Go backend with React frontend.
// All public methods are exposed to JavaScript via Wails bindings.
type App struct {
	ctx          context.Context    // Wails runtime context
	core         *app.App           // Core application logic
	config       *app.Config        // Current configuration
	settings     *Settings          // Persistent user settings
	state        AppState           // Current app state
	stateErr     string             // Error message if state is StateError
	startTime    time.Time          // When the app started running
	mu           sync.RWMutex       // Protects state, stateErr, startTime, settings
	cancel       context.CancelFunc // Cancels the background Run() goroutine
	runDone      chan struct{}      // Signals when Run() goroutine completes
	chatCancel   context.CancelFunc // Cancels the in-flight StreamChat goroutine
	chatStreamID uint64             // Monotonically increasing stream counter
	chatMu       sync.Mutex         // Protects chatCancel and chatStreamID
}

// NewApp creates a new App application struct.
func NewApp() *App {
	return &App{
		state:   StateIdle,
		runDone: make(chan struct{}),
	}
}

// startup is called when the Wails app starts.
// It initializes the core application but doesn't start the service yet.
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx

	// Load persistent settings first
	settings, err := LoadSettings()
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("Could not load settings: %v", err))
	}
	a.settings = settings

	// If settings are configured, apply them to environment
	if settings.IsConfigured {
		runtime.LogInfo(ctx, "Loaded settings from config file")

		// Set environment variables from settings
		if settings.SyftHubURL != "" {
			os.Setenv("SYFTHUB_URL", settings.SyftHubURL)
		}
		if settings.APIKey != "" {
			os.Setenv("SYFTHUB_API_KEY", settings.APIKey)

			// Fetch username from SyftHub API and set SPACE_URL for tunneling mode
			if err := a.fetchAndSetSpaceURL(ctx, settings.SyftHubURL, settings.APIKey); err != nil {
				runtime.LogWarning(ctx, fmt.Sprintf("Could not fetch username from SyftHub: %v", err))
			}

			// Fetch aggregator URL from user profile
			if aggURL, err := a.fetchAggregatorURL(ctx, settings.SyftHubURL, settings.APIKey); err != nil {
				runtime.LogWarning(ctx, fmt.Sprintf("Could not fetch aggregator URL: %v", err))
			} else if aggURL != "" {
				a.settings.AggregatorURL = aggURL
			}
		}

		// Resolve and set endpoints path
		endpointsPath, err := resolveEndpointsPath(settings.EndpointsPath)
		if err == nil {
			os.Setenv("ENDPOINTS_PATH", endpointsPath)
		}
	} else {
		// Not configured - try loading from .env as fallback
		exePath, err := os.Executable()
		if err == nil {
			envPath := filepath.Join(filepath.Dir(exePath), ".env")
			if err := godotenv.Load(envPath); err != nil {
				runtime.LogWarning(ctx, fmt.Sprintf("Could not load .env from %s: %v", envPath, err))
				// Also try current directory as fallback
				if err := godotenv.Load(".env"); err != nil {
					runtime.LogWarning(ctx, fmt.Sprintf("Could not load .env from current directory: %v", err))
				}
			} else {
				runtime.LogInfo(ctx, fmt.Sprintf("Loaded .env from %s", envPath))
			}
		}
	}

	// Load configuration from environment
	a.config = app.ConfigFromEnv()

	// Log startup
	runtime.LogInfo(ctx, "SyftHub Desktop GUI starting up")
	runtime.LogInfo(ctx, fmt.Sprintf("Endpoints path: %s", a.config.EndpointsPath))
	runtime.LogInfo(ctx, fmt.Sprintf("SyftHub URL: %s", os.Getenv("SYFTHUB_URL")))
	runtime.LogInfo(ctx, fmt.Sprintf("Space URL: %s", os.Getenv("SPACE_URL")))
	runtime.LogInfo(ctx, fmt.Sprintf("Settings configured: %v", settings.IsConfigured))
}

// fetchAndSetSpaceURL fetches the username from SyftHub API and sets SPACE_URL for tunneling mode.
func (a *App) fetchAndSetSpaceURL(ctx context.Context, syfthubURL, apiKey string) error {
	// Create auth client to get user info
	authClient := syfthubapi.NewAuthClient(syfthubURL, apiKey, nil)

	// Fetch user info with a timeout
	fetchCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	user, err := authClient.GetMe(fetchCtx)
	if err != nil {
		return fmt.Errorf("failed to get user info: %w", err)
	}

	if user.Username == "" {
		return fmt.Errorf("username not found in response")
	}

	// Set SPACE_URL for tunneling mode
	spaceURL := fmt.Sprintf("tunneling:%s", user.Username)
	os.Setenv("SPACE_URL", spaceURL)

	runtime.LogInfo(ctx, fmt.Sprintf("Authenticated as %s, using tunnel mode", user.Username))
	return nil
}

// fetchAggregatorURL fetches the aggregator_url from the SyftHub user profile.
// The Go SDK's UserContext struct doesn't include this field, so we parse it directly.
func (a *App) fetchAggregatorURL(ctx context.Context, syfthubURL, apiKey string) (string, error) {
	fetchCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	reqURL := strings.TrimRight(syfthubURL, "/") + "/api/v1/auth/me"
	req, err := http.NewRequestWithContext(fetchCtx, http.MethodGet, reqURL, nil)
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to fetch user profile: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("user profile request returned %d", resp.StatusCode)
	}

	var profile struct {
		AggregatorURL string `json:"aggregator_url"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&profile); err != nil {
		return "", fmt.Errorf("failed to decode user profile: %w", err)
	}

	return profile.AggregatorURL, nil
}

// shutdown is called when the Wails app is closing.
func (a *App) shutdown(ctx context.Context) {
	runtime.LogInfo(ctx, "SyftHub Desktop GUI shutting down")

	// Stop the core app if running
	a.mu.RLock()
	running := a.state == StateRunning || a.state == StateStarting
	a.mu.RUnlock()

	if running {
		_ = a.Stop()
	}
}

// GetStatus returns the current application status.
func (a *App) GetStatus() StatusInfo {
	a.mu.RLock()
	defer a.mu.RUnlock()

	runtime.LogInfo(a.ctx, fmt.Sprintf("GetStatus called, state=%s", a.state))

	info := StatusInfo{
		State:        a.state,
		ErrorMessage: a.stateErr,
		Mode:         a.getMode(),
	}

	if a.state == StateRunning && !a.startTime.IsZero() {
		info.Uptime = int64(time.Since(a.startTime).Seconds())
	}

	return info
}

// GetEndpoints returns the list of loaded endpoints.
func (a *App) GetEndpoints() []EndpointInfo {
	a.mu.RLock()
	defer a.mu.RUnlock()

	runtime.LogInfo(a.ctx, "GetEndpoints called")

	if a.core == nil {
		runtime.LogWarning(a.ctx, "GetEndpoints: core is nil, returning empty")
		return []EndpointInfo{}
	}

	endpoints := a.core.GetEndpoints()
	runtime.LogInfo(a.ctx, fmt.Sprintf("GetEndpoints: returning %d endpoints", len(endpoints)))
	result := make([]EndpointInfo, 0, len(endpoints))

	for _, ep := range endpoints {
		result = append(result, EndpointInfo{
			Slug:        ep.Slug,
			Name:        ep.Name,
			Description: ep.Description,
			Type:        ep.Type,
			Enabled:     ep.Enabled,
			Version:     ep.Version,
			HasPolicies: ep.HasPolicies(),
		})
	}

	return result
}

// GetConfig returns the current configuration.
func (a *App) GetConfig() ConfigInfo {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return ConfigInfo{}
	}

	aggURL := ""
	if a.settings != nil {
		aggURL = a.settings.AggregatorURL
	}

	return ConfigInfo{
		SyftHubURL:        os.Getenv("SYFTHUB_URL"),
		SpaceURL:          os.Getenv("SPACE_URL"),
		EndpointsPath:     a.config.EndpointsPath,
		LogLevel:          a.config.LogLevel,
		WatchEnabled:      a.config.WatchEnabled,
		UseEmbeddedPython: a.config.UseEmbeddedPython,
		PythonPath:        a.config.PythonPath,
		AggregatorURL:     aggURL,
	}
}

// Start initializes and starts the core application.
// This runs the transport (HTTP or NATS) in a background goroutine.
func (a *App) Start() error {
	a.mu.Lock()

	// Check if already running
	if a.state == StateRunning || a.state == StateStarting {
		a.mu.Unlock()
		return fmt.Errorf("application is already %s", a.state)
	}

	// Update state to starting
	a.state = StateStarting
	a.stateErr = ""
	a.mu.Unlock()

	// Emit state change event to frontend
	runtime.EventsEmit(a.ctx, "app:state-changed", a.GetStatus())

	// Create core application
	core, err := app.New(a.config)
	if err != nil {
		a.setErrorState(fmt.Sprintf("failed to create app: %v", err))
		return err
	}

	// Create cancellable context for the Run() goroutine
	runCtx, cancel := context.WithCancel(context.Background())

	a.mu.Lock()
	a.core = core
	a.cancel = cancel
	a.runDone = make(chan struct{})
	a.mu.Unlock()

	// Setup the core application
	if err := core.Setup(runCtx); err != nil {
		cancel()
		a.setErrorState(fmt.Sprintf("failed to setup app: %v", err))
		return err
	}

	// Wire file watcher events to frontend
	core.SetOnEndpointsChanged(func() {
		runtime.LogInfo(a.ctx, "File watcher detected changes, notifying frontend")
		runtime.EventsEmit(a.ctx, "app:endpoints-changed", a.GetEndpoints())
	})

	// Wire new log events to frontend
	core.SetOnNewLog(func(log *syfthubapi.RequestLog) {
		entry := convertRequestLog(log)
		runtime.EventsEmit(a.ctx, "app:new-log", entry)
	})

	// Run in background goroutine
	go func() {
		defer close(a.runDone)

		// Mark as running
		a.mu.Lock()
		a.state = StateRunning
		a.startTime = time.Now()
		a.mu.Unlock()
		runtime.EventsEmit(a.ctx, "app:state-changed", a.GetStatus())
		runtime.LogInfo(a.ctx, "SyftHub service started")

		// Block here until cancelled or error
		if err := core.Run(runCtx); err != nil {
			// Only set error if not a normal cancellation
			if runCtx.Err() == nil {
				a.setErrorState(fmt.Sprintf("run error: %v", err))
			}
		}

		// Mark as idle when done
		a.mu.Lock()
		if a.state != StateError {
			a.state = StateIdle
		}
		a.startTime = time.Time{}
		a.mu.Unlock()
		runtime.EventsEmit(a.ctx, "app:state-changed", a.GetStatus())
		runtime.LogInfo(a.ctx, "SyftHub service stopped")
	}()

	return nil
}

// Stop gracefully stops the core application.
func (a *App) Stop() error {
	a.mu.Lock()

	// Check if running
	if a.state != StateRunning && a.state != StateStarting {
		a.mu.Unlock()
		return fmt.Errorf("application is not running (state: %s)", a.state)
	}

	// Update state
	a.state = StateStopping
	cancel := a.cancel
	runDone := a.runDone
	core := a.core
	a.mu.Unlock()

	runtime.EventsEmit(a.ctx, "app:state-changed", a.GetStatus())
	runtime.LogInfo(a.ctx, "Stopping SyftHub service...")

	// Cancel the context to signal Run() to stop
	if cancel != nil {
		cancel()
	}

	// Gracefully shutdown core app
	if core != nil {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		if err := core.Shutdown(shutdownCtx); err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Shutdown error: %v", err))
		}
	}

	// Wait for Run() goroutine to complete
	select {
	case <-runDone:
		// Clean exit
	case <-time.After(15 * time.Second):
		runtime.LogWarning(a.ctx, "Timeout waiting for service to stop")
	}

	return nil
}

// ReloadEndpoints reloads endpoints from the filesystem.
func (a *App) ReloadEndpoints() error {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return fmt.Errorf("application not initialized")
	}

	runtime.LogInfo(a.ctx, "Reloading endpoints...")

	if err := core.ReloadEndpoints(); err != nil {
		return fmt.Errorf("failed to reload endpoints: %w", err)
	}

	// Emit event with updated endpoints
	runtime.EventsEmit(a.ctx, "app:endpoints-changed", a.GetEndpoints())

	return nil
}

// Greet is a simple test method to verify Go-React communication.
func (a *App) Greet(name string) string {
	return fmt.Sprintf("Hello %s! SyftHub Desktop is ready.", name)
}

// GetVersion returns the application version.
func (a *App) GetVersion() string {
	return Version
}

// LogDebug logs a debug message from the frontend to Go stdout.
func (a *App) LogDebug(component, message string) {
	runtime.LogInfo(a.ctx, fmt.Sprintf("[FE:%s] %s", component, message))
}

// setErrorState sets the app to error state and emits an event.
func (a *App) setErrorState(errMsg string) {
	a.mu.Lock()
	a.state = StateError
	a.stateErr = errMsg
	a.mu.Unlock()
	runtime.EventsEmit(a.ctx, "app:state-changed", a.GetStatus())
	runtime.LogError(a.ctx, errMsg)
}

// getMode returns the connection mode string.
func (a *App) getMode() string {
	spaceURL := os.Getenv("SPACE_URL")
	if len(spaceURL) > 10 && spaceURL[:10] == "tunneling:" {
		return "NATS Tunnel"
	}
	return "HTTP"
}

// HasSettings returns true if the app has been configured.
func (a *App) HasSettings() bool {
	a.mu.RLock()
	defer a.mu.RUnlock()
	result := a.settings != nil && a.settings.IsConfigured
	runtime.LogInfo(a.ctx, fmt.Sprintf("HasSettings called, returning: %v", result))
	return result
}

// GetSettings returns the current settings.
func (a *App) GetSettings() *Settings {
	a.mu.RLock()
	defer a.mu.RUnlock()
	runtime.LogInfo(a.ctx, "GetSettings called")
	if a.settings == nil {
		return DefaultSettings()
	}
	return a.settings
}

// SaveSettingsData saves the provided settings and applies them.
// This is the method exposed to the frontend.
func (a *App) SaveSettingsData(syfthubURL, apiKey, endpointsPath string) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	// Create settings
	settings := &Settings{
		SyftHubURL:    syfthubURL,
		APIKey:        apiKey,
		EndpointsPath: endpointsPath,
		IsConfigured:  true,
	}

	// Save to file
	if err := SaveSettings(settings); err != nil {
		return fmt.Errorf("failed to save settings: %w", err)
	}

	// Ensure endpoints directory exists
	if err := EnsureEndpointsDir(endpointsPath); err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("Could not create endpoints directory: %v", err))
	}

	// Apply settings to environment
	os.Setenv("SYFTHUB_URL", syfthubURL)
	if apiKey != "" {
		os.Setenv("SYFTHUB_API_KEY", apiKey)

		// Fetch username from SyftHub API and set SPACE_URL for tunneling mode
		if err := a.fetchAndSetSpaceURL(a.ctx, syfthubURL, apiKey); err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Could not fetch username from SyftHub: %v", err))
		}

		// Fetch and cache aggregator URL
		if aggURL, err := a.fetchAggregatorURL(a.ctx, syfthubURL, apiKey); err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Could not fetch aggregator URL: %v", err))
		} else if aggURL != "" {
			settings.AggregatorURL = aggURL
		}
	}

	// Resolve and set endpoints path
	resolvedPath, err := resolveEndpointsPath(endpointsPath)
	if err == nil {
		os.Setenv("ENDPOINTS_PATH", resolvedPath)
	}

	// Update internal state
	a.settings = settings
	a.config = app.ConfigFromEnv()

	runtime.LogInfo(a.ctx, "Settings saved successfully")
	runtime.LogInfo(a.ctx, fmt.Sprintf("SyftHub URL: %s", syfthubURL))
	runtime.LogInfo(a.ctx, fmt.Sprintf("Endpoints path: %s", a.config.EndpointsPath))

	return nil
}

// GetDefaultEndpointsPath returns the default endpoints directory path.
func (a *App) GetDefaultEndpointsPath() string {
	path, err := getDefaultEndpointsPath()
	if err != nil {
		return ".endpoints"
	}
	return path
}

// GetSettingsDir returns the settings directory path.
func (a *App) GetSettingsDir() string {
	dir, err := getSettingsDir()
	if err != nil {
		return ""
	}
	return dir
}

// BrowseForFolder opens a native folder picker dialog and returns the selected path.
func (a *App) BrowseForFolder(title string) string {
	path, err := runtime.OpenDirectoryDialog(a.ctx, runtime.OpenDialogOptions{
		Title: title,
	})
	if err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("Folder dialog error: %v", err))
		return ""
	}
	return path
}

// ============================================================================
// Log-related bindings
// ============================================================================

// GetLogs retrieves logs for an endpoint with pagination and filters.
func (a *App) GetLogs(slug string, offset, limit int, status string) (*LogQueryResult, error) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return &LogQueryResult{
			Logs:    []RequestLogEntry{},
			Total:   0,
			HasMore: false,
		}, nil
	}

	opts := &syfthubapi.LogQueryOptions{
		Offset: offset,
		Limit:  limit,
		Status: status,
	}

	result, err := core.GetLogs(context.Background(), slug, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to get logs: %w", err)
	}

	// Convert to frontend types
	return convertLogQueryResult(result), nil
}

// GetLogStats returns aggregate statistics for an endpoint's logs.
func (a *App) GetLogStats(slug string) (*LogStats, error) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return &LogStats{}, nil
	}

	stats, err := core.GetLogStats(context.Background(), slug)
	if err != nil {
		return nil, fmt.Errorf("failed to get log stats: %w", err)
	}

	// Convert to frontend type
	return convertLogStats(stats), nil
}

// GetLogDetail retrieves a specific log entry by ID.
func (a *App) GetLogDetail(slug, logID string) (*RequestLogEntry, error) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return nil, fmt.Errorf("application not initialized")
	}

	log, err := core.GetLogByID(context.Background(), slug, logID)
	if err != nil {
		return nil, fmt.Errorf("failed to get log: %w", err)
	}

	return convertRequestLog(log), nil
}

// DeleteLogs deletes all logs for an endpoint.
func (a *App) DeleteLogs(slug string) error {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return fmt.Errorf("application not initialized")
	}

	return core.DeleteLogs(context.Background(), slug)
}

// convertLogQueryResult converts SDK log query result to frontend type.
func convertLogQueryResult(result *syfthubapi.LogQueryResult) *LogQueryResult {
	logs := make([]RequestLogEntry, 0, len(result.Logs))
	for _, log := range result.Logs {
		logs = append(logs, *convertRequestLog(log))
	}

	return &LogQueryResult{
		Logs:    logs,
		Total:   result.Total,
		HasMore: result.HasMore,
	}
}

// convertRequestLog converts SDK request log to frontend type.
func convertRequestLog(log *syfthubapi.RequestLog) *RequestLogEntry {
	entry := &RequestLogEntry{
		ID:            log.ID,
		Timestamp:     log.Timestamp.Format(time.RFC3339Nano),
		CorrelationID: log.CorrelationID,
		EndpointSlug:  log.EndpointSlug,
		EndpointType:  log.EndpointType,
	}

	if log.User != nil {
		entry.User = &LogUserInfo{
			ID:       log.User.ID,
			Username: log.User.Username,
			Email:    log.User.Email,
			Role:     log.User.Role,
		}
	}

	if log.Request != nil {
		entry.Request = &LogRequestInfo{
			Type:    log.Request.Type,
			Query:   log.Request.Query,
			RawSize: log.Request.RawSize,
		}
		// Convert messages if present
		if len(log.Request.Messages) > 0 {
			msgs := make([]LogMessage, 0, len(log.Request.Messages))
			for _, msg := range log.Request.Messages {
				msgs = append(msgs, LogMessage{
					Role:    msg.Role,
					Content: msg.Content,
				})
			}
			entry.Request.Messages = msgs
		}
	}

	if log.Response != nil {
		entry.Response = &LogResponseInfo{
			Success:          log.Response.Success,
			Content:          log.Response.Content,
			ContentTruncated: log.Response.ContentTruncated,
			Error:            log.Response.Error,
			ErrorType:        log.Response.ErrorType,
			ErrorCode:        log.Response.ErrorCode,
		}
	}

	if log.Policy != nil {
		entry.Policy = &LogPolicyInfo{
			Evaluated:  log.Policy.Evaluated,
			Allowed:    log.Policy.Allowed,
			PolicyName: log.Policy.PolicyName,
			Reason:     log.Policy.Reason,
			Pending:    log.Policy.Pending,
		}
	}

	if log.Timing != nil {
		entry.Timing = &LogTimingInfo{
			ReceivedAt:  log.Timing.ReceivedAt.Format(time.RFC3339Nano),
			ProcessedAt: log.Timing.ProcessedAt.Format(time.RFC3339Nano),
			DurationMs:  log.Timing.DurationMs,
		}
	}

	return entry
}

// convertLogStats converts SDK log stats to frontend type.
func convertLogStats(stats *syfthubapi.LogStats) *LogStats {
	result := &LogStats{
		TotalRequests:   stats.TotalRequests,
		SuccessCount:    stats.SuccessCount,
		ErrorCount:      stats.ErrorCount,
		PolicyDenyCount: stats.PolicyDenyCount,
		AvgDurationMs:   stats.AvgDurationMs,
	}

	if stats.LastRequestTime != nil {
		formatted := stats.LastRequestTime.Format(time.RFC3339Nano)
		result.LastRequestTime = &formatted
	}

	return result
}

// ============================================================================
// Chat Bindings
// ============================================================================

// GetAggregatorURL returns the cached aggregator URL from settings.
func (a *App) GetAggregatorURL() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.settings == nil {
		return ""
	}
	return a.settings.AggregatorURL
}

// StreamChat starts an SSE streaming chat session with the aggregator.
// It returns immediately; all streaming data flows through Wails events:
//   - "chat:stream-event" with a ChatStreamEvent payload for every SSE event
//
// Any previously running stream is cancelled before starting the new one.
func (a *App) StreamChat(request ChatRequest) error {
	a.mu.RLock()
	aggURL := ""
	if a.settings != nil {
		aggURL = a.settings.AggregatorURL
	}
	a.mu.RUnlock()

	if aggURL == "" {
		return fmt.Errorf("aggregator URL not configured — save SyftHub settings first")
	}

	// Cancel any existing in-flight stream.
	a.chatMu.Lock()
	if a.chatCancel != nil {
		a.chatCancel()
		a.chatCancel = nil
	}
	chatCtx, cancel := context.WithCancel(context.Background())
	a.chatCancel = cancel
	a.chatStreamID++
	myStreamID := a.chatStreamID
	a.chatMu.Unlock()

	go func() {
		defer func() {
			a.chatMu.Lock()
			if a.chatStreamID == myStreamID {
				a.chatCancel = nil
			}
			a.chatMu.Unlock()
		}()

		if err := a.runChatStream(chatCtx, aggURL, request); err != nil {
			// Only emit error if the context wasn't cancelled (user stop).
			if chatCtx.Err() == nil {
				evt := ChatStreamEvent{Type: "error", Message: err.Error()}
				runtime.EventsEmit(a.ctx, "chat:stream-event", evt)
			}
		}
	}()

	return nil
}

// runChatStream performs the actual HTTP SSE call and emits Wails events.
func (a *App) runChatStream(ctx context.Context, aggURL string, request ChatRequest) error {
	topK := request.TopK
	if topK == 0 {
		topK = 5
	}
	maxTokens := request.MaxTokens
	if maxTokens == 0 {
		maxTokens = 1024
	}
	temperature := request.Temperature
	if temperature == 0 {
		temperature = 0.7
	}

	type aggRef struct {
		URL           string `json:"url"`
		Slug          string `json:"slug"`
		Name          string `json:"name"`
		TenantName    string `json:"tenant_name,omitempty"`
		OwnerUsername string `json:"owner_username,omitempty"`
	}

	toAggRef := func(r ChatEndpointRef) aggRef {
		return aggRef{URL: r.URL, Slug: r.Slug, Name: r.Name, TenantName: r.TenantName, OwnerUsername: r.OwnerUsername}
	}

	dataSources := make([]aggRef, 0, len(request.DataSources))
	for _, ds := range request.DataSources {
		dataSources = append(dataSources, toAggRef(ds))
	}

	messages := make([]map[string]string, 0, len(request.Messages))
	for _, m := range request.Messages {
		messages = append(messages, map[string]string{"role": m.Role, "content": m.Content})
	}

	bodyMap := map[string]any{
		"prompt":             request.Prompt,
		"model":              toAggRef(request.Model),
		"data_sources":       dataSources,
		"endpoint_tokens":    map[string]string{},
		"transaction_tokens": map[string]string{},
		"top_k":              topK,
		"max_tokens":         maxTokens,
		"temperature":        temperature,
		"stream":             true,
	}
	if len(messages) > 0 {
		bodyMap["messages"] = messages
	}

	bodyBytes, err := json.Marshal(bodyMap)
	if err != nil {
		return fmt.Errorf("failed to marshal chat request: %w", err)
	}

	endpoint := strings.TrimRight(aggURL, "/") + "/chat/stream"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(bodyBytes))
	if err != nil {
		return fmt.Errorf("failed to create HTTP request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("aggregator request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("aggregator returned status %d", resp.StatusCode)
	}

	scanner := bufio.NewScanner(resp.Body)
	var eventType string
	var dataBuffer strings.Builder

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		line := scanner.Text()

		switch {
		case strings.HasPrefix(line, "event: "):
			eventType = strings.TrimPrefix(line, "event: ")
		case strings.HasPrefix(line, "data: "):
			dataBuffer.WriteString(strings.TrimPrefix(line, "data: "))
		case line == "":
			if eventType != "" && dataBuffer.Len() > 0 {
				a.dispatchSSEEvent(eventType, dataBuffer.String())
			}
			eventType = ""
			dataBuffer.Reset()
		}
	}

	if err := scanner.Err(); err != nil && ctx.Err() == nil {
		return fmt.Errorf("SSE read error: %w", err)
	}

	return nil
}

// dispatchSSEEvent parses a raw SSE data payload and emits a ChatStreamEvent.
func (a *App) dispatchSSEEvent(eventType, data string) {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal([]byte(data), &raw); err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("chat: failed to parse SSE data for event %q: %v", eventType, err))
		return
	}

	evt := ChatStreamEvent{Type: eventType}

	if v, ok := raw["content"]; ok {
		_ = json.Unmarshal(v, &evt.Content)
	}
	if v, ok := raw["sources"]; ok {
		if eventType == "retrieval_start" {
			_ = json.Unmarshal(v, &evt.SourceCount)
		} else {
			_ = json.Unmarshal(v, &evt.Sources)
		}
	}
	if v, ok := raw["path"]; ok {
		_ = json.Unmarshal(v, &evt.Path)
	}
	if v, ok := raw["status"]; ok {
		_ = json.Unmarshal(v, &evt.Status)
	}
	if v, ok := raw["documents_retrieved"]; ok {
		_ = json.Unmarshal(v, &evt.DocumentsRetrieved)
	}
	if v, ok := raw["total_documents"]; ok {
		_ = json.Unmarshal(v, &evt.TotalDocuments)
	}
	if v, ok := raw["time_ms"]; ok {
		_ = json.Unmarshal(v, &evt.TimeMs)
	}
	if v, ok := raw["message"]; ok {
		_ = json.Unmarshal(v, &evt.Message)
	}
	if v, ok := raw["response"]; ok {
		_ = json.Unmarshal(v, &evt.Response)
	}
	if v, ok := raw["profit_share"]; ok {
		_ = json.Unmarshal(v, &evt.ProfitShare)
	}

	runtime.EventsEmit(a.ctx, "chat:stream-event", evt)
}

// StopChat cancels any in-flight StreamChat goroutine.
func (a *App) StopChat() {
	a.chatMu.Lock()
	defer a.chatMu.Unlock()
	if a.chatCancel != nil {
		a.chatCancel()
		a.chatCancel = nil
	}
}
