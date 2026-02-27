// Package main provides the Wails binding layer for syfthub-desktop-gui.
// This file implements the Facade pattern over the core syfthubapi SDK,
// exposing thread-safe methods that can be called from the React frontend.
package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/joho/godotenv"
	"github.com/openmined/syfthub-desktop-gui/internal/app"
	syfthub "github.com/openmined/syfthub/sdk/golang/syfthub"
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
	mu           sync.RWMutex       // Protects state, stateErr, startTime, settings, syftClient, username
	cancel       context.CancelFunc // Cancels the background Run() goroutine
	runDone      chan struct{}      // Signals when Run() goroutine completes
	chatCancel   context.CancelFunc // Cancels the in-flight StreamChat goroutine
	chatStreamID uint64             // Monotonically increasing stream counter
	chatMu       sync.Mutex         // Protects chatCancel and chatStreamID
	syftClient   *syfthub.Client    // Hub API client; nil if not configured
	username     string             // Authenticated user's username (set after login)
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

			// Initialize the SDK client (fetches username, sets SPACE_URL)
			a.initSyftClient(ctx, settings.SyftHubURL, settings.APIKey)
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

// initSyftClient creates a new syfthub.Client and authenticates to fetch the username.
// It stores the client in a.syftClient, the username in a.username, and sets SPACE_URL.
// Safe to call without a.mu held — acquires it internally for state updates.
func (a *App) initSyftClient(ctx context.Context, syfthubURL, apiKey string) {
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(syfthubURL),
		syfthub.WithAPIToken(apiKey),
	)
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("Could not create syfthub client: %v", err))
		return
	}

	// Fetch user info with a timeout to get the username for tunneling mode
	fetchCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	user, err := client.Auth.Me(fetchCtx)
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("Could not fetch user info: %v", err))
		// Store the client even if user info failed — aggregator URL still works
		a.mu.Lock()
		a.syftClient = client
		a.mu.Unlock()
		return
	}

	spaceURL := fmt.Sprintf("tunneling:%s", user.Username)
	os.Setenv("SPACE_URL", spaceURL)

	a.mu.Lock()
	a.syftClient = client
	a.username = user.Username
	a.mu.Unlock()

	runtime.LogInfo(ctx, fmt.Sprintf("Authenticated as %s, using tunnel mode", user.Username))
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
	if a.syftClient != nil {
		aggURL = a.syftClient.AggregatorURL()
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

		// Initialize the SDK client (network call — acquires a.mu internally)
		a.initSyftClient(a.ctx, syfthubURL, apiKey)
	}

	// Resolve and set endpoints path
	resolvedPath, err := resolveEndpointsPath(endpointsPath)
	if err == nil {
		os.Setenv("ENDPOINTS_PATH", resolvedPath)
	}

	// Update internal state
	a.mu.Lock()
	a.settings = settings
	a.config = app.ConfigFromEnv()
	a.mu.Unlock()

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

// GetAggregatorURL returns the aggregator URL from the SDK client.
// Returns a non-empty string whenever the app is configured (defaults to
// {syfthubURL}/aggregator/api/v1 if no custom aggregator is set).
func (a *App) GetAggregatorURL() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.syftClient == nil {
		runtime.LogInfo(a.ctx, "[aggregator] GetAggregatorURL: syftClient is nil, returning empty")
		return ""
	}
	url := a.syftClient.AggregatorURL()
	runtime.LogInfo(a.ctx, fmt.Sprintf("[aggregator] GetAggregatorURL: %q", url))
	return url
}

// StreamChat starts a streaming chat session via the syfthub SDK.
// It returns immediately; all streaming data flows through Wails events:
//   - "chat:stream-event" with a ChatStreamEvent payload for every event
//
// Any previously running stream is cancelled before starting the new one.
func (a *App) StreamChat(request ChatRequest) error {
	a.mu.RLock()
	client := a.syftClient
	username := a.username
	a.mu.RUnlock()

	if client == nil {
		return fmt.Errorf("not configured — save SyftHub settings first")
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

		if err := a.runSDKChatStream(chatCtx, client, username, request); err != nil {
			// Only emit error if the context wasn't cancelled (user stop).
			if chatCtx.Err() == nil {
				evt := ChatStreamEvent{Type: "error", Message: err.Error()}
				runtime.EventsEmit(a.ctx, "chat:stream-event", evt)
			}
		}
	}()

	return nil
}

// runSDKChatStream performs the SDK streaming chat call and emits Wails events.
func (a *App) runSDKChatStream(ctx context.Context, client *syfthub.Client, username string, request ChatRequest) error {
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

	// Build model path: "username/slug"
	modelPath := request.Model.Slug
	if username != "" {
		modelPath = username + "/" + request.Model.Slug
	}

	// Build data source paths
	dataSources := make([]string, 0, len(request.DataSources))
	for _, ds := range request.DataSources {
		if username != "" {
			dataSources = append(dataSources, username+"/"+ds.Slug)
		} else {
			dataSources = append(dataSources, ds.Slug)
		}
	}

	// Convert conversation history
	messages := make([]syfthub.Message, 0, len(request.Messages))
	for _, m := range request.Messages {
		messages = append(messages, syfthub.Message{Role: m.Role, Content: m.Content})
	}

	chatReq := &syfthub.ChatCompleteRequest{
		Prompt:      request.Prompt,
		Model:       modelPath,
		DataSources: dataSources,
		TopK:        topK,
		MaxTokens:   maxTokens,
		Temperature: temperature,
		Messages:    messages,
	}

	eventCh, errCh := client.Chat().Stream(ctx, chatReq)

	for eventCh != nil {
		select {
		case <-ctx.Done():
			return nil
		case err, ok := <-errCh:
			if !ok {
				errCh = nil
			} else if err != nil {
				return err
			}
		case event, ok := <-eventCh:
			if !ok {
				return nil // stream complete
			}
			a.dispatchSDKEvent(event, request)
		}
	}

	return nil
}

// dispatchSDKEvent converts a typed SDK ChatEvent to a ChatStreamEvent and emits it.
func (a *App) dispatchSDKEvent(event syfthub.ChatEvent, request ChatRequest) {
	var evt ChatStreamEvent

	switch e := event.(type) {
	case *syfthub.RetrievalStartEvent:
		evt = ChatStreamEvent{
			Type:        "retrieval_start",
			SourceCount: len(request.DataSources),
		}
	case *syfthub.SourceCompleteEvent:
		evt = ChatStreamEvent{
			Type:               "source_complete",
			Path:               e.Source.Path,
			Status:             string(e.Source.Status),
			DocumentsRetrieved: e.Source.DocumentsRetrieved,
		}
	case *syfthub.RetrievalCompleteEvent:
		evt = ChatStreamEvent{Type: "retrieval_complete"}
	case *syfthub.RerankingStartEvent:
		evt = ChatStreamEvent{Type: "reranking_start", TotalDocuments: e.Documents}
	case *syfthub.RerankingCompleteEvent:
		evt = ChatStreamEvent{Type: "reranking_complete", TotalDocuments: e.Documents, TimeMs: e.TimeMs}
	case *syfthub.GenerationStartEvent:
		evt = ChatStreamEvent{Type: "generation_start"}
	case *syfthub.GenerationHeartbeatEvent:
		evt = ChatStreamEvent{Type: "generation_heartbeat", TimeMs: e.ElapsedMs}
	case *syfthub.TokenEvent:
		evt = ChatStreamEvent{Type: "token", Content: e.Content}
	case *syfthub.DoneEvent:
		sources := make(map[string]ChatDocumentSource, len(e.Sources))
		for k, v := range e.Sources {
			sources[k] = ChatDocumentSource{Slug: v.Slug, Content: v.Content}
		}
		evt = ChatStreamEvent{Type: "done", Response: e.Response, Sources: sources}
	case *syfthub.ErrorEvent:
		evt = ChatStreamEvent{Type: "error", Message: e.Error}
	default:
		return
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

// ============================================================================
// Aggregator Management Bindings
// ============================================================================

// toUserAggregator converts the SDK's UserAggregator to the desktop's UserAggregator type.
func toUserAggregator(a syfthub.UserAggregator) UserAggregator {
	return UserAggregator{
		ID:        a.ID,
		Name:      a.Name,
		URL:       a.URL,
		IsDefault: a.IsDefault,
		CreatedAt: a.CreatedAt.Format(time.RFC3339),
	}
}

// GetUserAggregators fetches the list of aggregators for the current user via the SDK.
func (a *App) GetUserAggregators() ([]UserAggregator, error) {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()

	if client == nil {
		runtime.LogWarning(a.ctx, "[aggregator] GetUserAggregators: app not configured")
		return nil, fmt.Errorf("app not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	sdkAggregators, err := client.Users.Aggregators.List(ctx)
	if err != nil {
		runtime.LogError(a.ctx, fmt.Sprintf("[aggregator] List error: %v", err))
		return nil, fmt.Errorf("failed to fetch aggregators: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("[aggregator] fetched %d aggregators", len(sdkAggregators)))

	result := make([]UserAggregator, 0, len(sdkAggregators))
	for _, agg := range sdkAggregators {
		result = append(result, toUserAggregator(agg))
	}
	return result, nil
}

// CreateUserAggregator creates a new aggregator for the current user via the SDK.
func (a *App) CreateUserAggregator(name, url string, isDefault bool) (UserAggregator, error) {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()

	if client == nil {
		return UserAggregator{}, fmt.Errorf("app not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	created, err := client.Users.Aggregators.Create(ctx, name, url)
	if err != nil {
		return UserAggregator{}, fmt.Errorf("failed to create aggregator: %w", err)
	}

	// If the caller wants this to be default but the server didn't set it as default, set it now.
	if isDefault && !created.IsDefault {
		updated, err := client.Users.Aggregators.SetDefault(ctx, created.ID)
		if err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("[aggregator] Failed to set default: %v", err))
			return toUserAggregator(*created), nil
		}
		return toUserAggregator(*updated), nil
	}

	return toUserAggregator(*created), nil
}

// UpdateUserAggregator updates an existing aggregator by ID via the SDK.
func (a *App) UpdateUserAggregator(id int, name, url string) (UserAggregator, error) {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()

	if client == nil {
		return UserAggregator{}, fmt.Errorf("app not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req := &syfthub.UpdateAggregatorRequest{
		Name: &name,
		URL:  &url,
	}
	updated, err := client.Users.Aggregators.Update(ctx, id, req)
	if err != nil {
		return UserAggregator{}, fmt.Errorf("failed to update aggregator: %w", err)
	}

	return toUserAggregator(*updated), nil
}

// DeleteUserAggregator deletes an aggregator by ID via the SDK.
func (a *App) DeleteUserAggregator(id int) error {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()

	if client == nil {
		return fmt.Errorf("app not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	return client.Users.Aggregators.Delete(ctx, id)
}

// SetDefaultUserAggregator sets the given aggregator as the default via the SDK.
func (a *App) SetDefaultUserAggregator(id int) (UserAggregator, error) {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()

	if client == nil {
		return UserAggregator{}, fmt.Errorf("app not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	updated, err := client.Users.Aggregators.SetDefault(ctx, id)
	if err != nil {
		return UserAggregator{}, fmt.Errorf("failed to set default aggregator: %w", err)
	}

	return toUserAggregator(*updated), nil
}
