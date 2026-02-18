// Package main provides type definitions for the Wails binding layer.
// These types are serialized to JSON and used by the React frontend.
package main

// AppState represents the current state of the application.
type AppState string

const (
	StateIdle     AppState = "idle"     // Not connected, waiting to start
	StateStarting AppState = "starting" // Initializing connection
	StateRunning  AppState = "running"  // Connected and processing requests
	StateStopping AppState = "stopping" // Gracefully shutting down
	StateError    AppState = "error"    // Error state, see ErrorMessage
)

// StatusInfo provides current application status for the frontend.
type StatusInfo struct {
	State        AppState `json:"state"`
	ErrorMessage string   `json:"errorMessage,omitempty"`
	Mode         string   `json:"mode"`             // "HTTP" or "NATS Tunnel"
	Uptime       int64    `json:"uptime,omitempty"` // Seconds since start
}

// EndpointInfo represents an endpoint for display in the UI.
type EndpointInfo struct {
	Slug        string `json:"slug"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Type        string `json:"type"` // "model" or "data_source"
	Enabled     bool   `json:"enabled"`
	Version     string `json:"version,omitempty"`
	HasPolicies bool   `json:"hasPolicies"`
}

// ConfigInfo represents the application configuration.
type ConfigInfo struct {
	SyftHubURL        string `json:"syfthubUrl"`
	SpaceURL          string `json:"spaceUrl"`
	EndpointsPath     string `json:"endpointsPath"`
	LogLevel          string `json:"logLevel"`
	WatchEnabled      bool   `json:"watchEnabled"`
	UseEmbeddedPython bool   `json:"useEmbeddedPython"`
	PythonPath        string `json:"pythonPath,omitempty"`
}

// ConfigRequest represents a configuration update from the frontend.
type ConfigRequest struct {
	SyftHubURL        string `json:"syfthubUrl,omitempty"`
	APIKey            string `json:"apiKey,omitempty"`
	SpaceURL          string `json:"spaceUrl,omitempty"`
	EndpointsPath     string `json:"endpointsPath,omitempty"`
	LogLevel          string `json:"logLevel,omitempty"`
	WatchEnabled      *bool  `json:"watchEnabled,omitempty"`
	UseEmbeddedPython *bool  `json:"useEmbeddedPython,omitempty"`
}

// LogEntry represents a log message for display in the UI.
type LogEntry struct {
	Timestamp string `json:"timestamp"`
	Level     string `json:"level"`
	Message   string `json:"message"`
	Fields    string `json:"fields,omitempty"` // JSON-encoded extra fields
}

// ============================================================================
// Request Log Types (for the Logs tab)
// ============================================================================

// RequestLogEntry represents a single request log entry for display in the UI.
type RequestLogEntry struct {
	ID            string           `json:"id"`
	Timestamp     string           `json:"timestamp"` // RFC3339Nano format
	CorrelationID string           `json:"correlationId"`
	EndpointSlug  string           `json:"endpointSlug"`
	EndpointType  string           `json:"endpointType"`
	User          *LogUserInfo     `json:"user,omitempty"`
	Request       *LogRequestInfo  `json:"request,omitempty"`
	Response      *LogResponseInfo `json:"response,omitempty"`
	Policy        *LogPolicyInfo   `json:"policy,omitempty"`
	Timing        *LogTimingInfo   `json:"timing,omitempty"`
}

// LogUserInfo contains user information for a log entry.
type LogUserInfo struct {
	ID       string `json:"id"`
	Username string `json:"username,omitempty"`
	Email    string `json:"email,omitempty"`
	Role     string `json:"role,omitempty"`
}

// LogMessage represents a chat message in a log entry.
type LogMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// LogRequestInfo contains request information for a log entry.
type LogRequestInfo struct {
	Type     string       `json:"type"`
	Messages []LogMessage `json:"messages,omitempty"`
	Query    string       `json:"query,omitempty"`
	RawSize  int          `json:"rawSize"`
}

// LogResponseInfo contains response information for a log entry.
type LogResponseInfo struct {
	Success          bool   `json:"success"`
	Content          string `json:"content,omitempty"`
	ContentTruncated bool   `json:"contentTruncated,omitempty"`
	Error            string `json:"error,omitempty"`
	ErrorType        string `json:"errorType,omitempty"`
	ErrorCode        string `json:"errorCode,omitempty"`
}

// LogPolicyInfo contains policy evaluation information for a log entry.
type LogPolicyInfo struct {
	Evaluated  bool   `json:"evaluated"`
	Allowed    bool   `json:"allowed"`
	PolicyName string `json:"policyName,omitempty"`
	Reason     string `json:"reason,omitempty"`
	Pending    bool   `json:"pending,omitempty"`
}

// LogTimingInfo contains timing information for a log entry.
type LogTimingInfo struct {
	ReceivedAt  string `json:"receivedAt"`
	ProcessedAt string `json:"processedAt"`
	DurationMs  int64  `json:"durationMs"`
}

// LogQueryResult contains the result of a log query.
type LogQueryResult struct {
	Logs    []RequestLogEntry `json:"logs"`
	Total   int               `json:"total"`
	HasMore bool              `json:"hasMore"`
}

// LogStats contains aggregate statistics for an endpoint's logs.
type LogStats struct {
	TotalRequests   int64   `json:"totalRequests"`
	SuccessCount    int64   `json:"successCount"`
	ErrorCount      int64   `json:"errorCount"`
	PolicyDenyCount int64   `json:"policyDenyCount"`
	AvgDurationMs   float64 `json:"avgDurationMs"`
	LastRequestTime *string `json:"lastRequestTime,omitempty"`
}
