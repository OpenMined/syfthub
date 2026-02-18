package syfthubapi

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// RequestLog represents a single request log entry for telemetry.
// This captures comprehensive information about each request for debugging and ETL.
type RequestLog struct {
	// ID is a unique identifier for this log entry.
	ID string `json:"id"`

	// Timestamp is when the request was received.
	Timestamp time.Time `json:"timestamp"`

	// CorrelationID is the request tracking ID from the tunnel protocol.
	CorrelationID string `json:"correlation_id"`

	// EndpointSlug is the target endpoint identifier.
	EndpointSlug string `json:"endpoint_slug"`

	// EndpointType is "model" or "data_source".
	EndpointType string `json:"endpoint_type"`

	// User contains the authenticated user information.
	User *LogUserInfo `json:"user,omitempty"`

	// Request contains the request details.
	Request *LogRequest `json:"request"`

	// Response contains the response details.
	Response *LogResponse `json:"response"`

	// Policy contains policy evaluation results (if policies were applied).
	Policy *LogPolicy `json:"policy,omitempty"`

	// Timing contains timing information.
	Timing *LogTiming `json:"timing"`
}

// LogUserInfo contains user information for the log entry.
type LogUserInfo struct {
	// ID is the user's unique identifier (sub claim from token).
	ID string `json:"id"`

	// Username is the user's username.
	Username string `json:"username,omitempty"`

	// Email is the user's email address.
	Email string `json:"email,omitempty"`

	// Role is the user's role.
	Role string `json:"role,omitempty"`
}

// LogRequest contains request information for the log entry.
type LogRequest struct {
	// Type is "model" or "data_source".
	Type string `json:"type"`

	// Messages contains the chat messages (for model endpoints).
	Messages []Message `json:"messages,omitempty"`

	// Query contains the query string (for data source endpoints).
	Query string `json:"query,omitempty"`

	// RawSize is the size of the raw request payload in bytes.
	RawSize int `json:"raw_size"`
}

// LogResponse contains response information for the log entry.
type LogResponse struct {
	// Success indicates whether the request succeeded.
	Success bool `json:"success"`

	// Content contains the response content (may be truncated).
	Content string `json:"content,omitempty"`

	// ContentTruncated indicates if the content was truncated.
	ContentTruncated bool `json:"content_truncated,omitempty"`

	// Error contains the error message if the request failed.
	Error string `json:"error,omitempty"`

	// ErrorType contains the error type/class name.
	ErrorType string `json:"error_type,omitempty"`

	// ErrorCode contains the tunnel error code.
	ErrorCode string `json:"error_code,omitempty"`
}

// LogPolicy contains policy evaluation information for the log entry.
type LogPolicy struct {
	// Evaluated indicates whether policies were evaluated for this request.
	Evaluated bool `json:"evaluated"`

	// Allowed indicates whether the request was allowed by policies.
	Allowed bool `json:"allowed"`

	// PolicyName is the name of the policy that made the final decision.
	PolicyName string `json:"policy_name,omitempty"`

	// Reason is the reason for the policy decision.
	Reason string `json:"reason,omitempty"`

	// Pending indicates if the request is pending manual review.
	Pending bool `json:"pending,omitempty"`

	// Metadata contains additional policy metadata.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// LogTiming contains timing information for the log entry.
type LogTiming struct {
	// ReceivedAt is when the request was received.
	ReceivedAt time.Time `json:"received_at"`

	// ProcessedAt is when processing completed.
	ProcessedAt time.Time `json:"processed_at"`

	// DurationMs is the total processing duration in milliseconds.
	DurationMs int64 `json:"duration_ms"`
}

// RequestLogHook is a callback function invoked after each request is processed.
// Implementations should be non-blocking or handle blocking internally.
type RequestLogHook func(ctx context.Context, log *RequestLog)

// LogStore is the interface for storing and querying request logs.
type LogStore interface {
	// Write appends a log entry. Should be non-blocking or handle async internally.
	Write(ctx context.Context, entry *RequestLog) error

	// Query retrieves logs for an endpoint with optional filters.
	Query(ctx context.Context, slug string, opts *LogQueryOptions) (*LogQueryResult, error)

	// GetStats returns aggregate statistics for an endpoint.
	GetStats(ctx context.Context, slug string) (*LogStats, error)

	// Close closes the log store and flushes any pending writes.
	Close() error
}

// LogQueryOptions contains options for querying logs.
type LogQueryOptions struct {
	// Offset is the number of entries to skip.
	Offset int `json:"offset"`

	// Limit is the maximum number of entries to return.
	Limit int `json:"limit"`

	// StartTime filters logs after this time (inclusive).
	StartTime *time.Time `json:"start_time,omitempty"`

	// EndTime filters logs before this time (exclusive).
	EndTime *time.Time `json:"end_time,omitempty"`

	// Status filters by status: "success", "error", or "" for all.
	Status string `json:"status,omitempty"`

	// UserID filters by user ID.
	UserID string `json:"user_id,omitempty"`

	// PolicyOnly returns only logs where policies were evaluated.
	PolicyOnly bool `json:"policy_only,omitempty"`
}

// LogQueryResult contains the result of a log query.
type LogQueryResult struct {
	// Logs contains the matching log entries.
	Logs []*RequestLog `json:"logs"`

	// Total is the total number of matching entries (before pagination).
	Total int `json:"total"`

	// HasMore indicates if there are more entries after this page.
	HasMore bool `json:"has_more"`
}

// LogStats contains aggregate statistics for an endpoint's logs.
type LogStats struct {
	// TotalRequests is the total number of requests.
	TotalRequests int64 `json:"total_requests"`

	// SuccessCount is the number of successful requests.
	SuccessCount int64 `json:"success_count"`

	// ErrorCount is the number of failed requests.
	ErrorCount int64 `json:"error_count"`

	// PolicyDenyCount is the number of requests denied by policy.
	PolicyDenyCount int64 `json:"policy_deny_count"`

	// AvgDurationMs is the average processing duration in milliseconds.
	AvgDurationMs float64 `json:"avg_duration_ms"`

	// LastRequestTime is the timestamp of the most recent request.
	LastRequestTime *time.Time `json:"last_request_time,omitempty"`
}

// NewRequestLogID generates a new unique log entry ID.
func NewRequestLogID() string {
	return uuid.New().String()
}

// MaxLogContentSize is the maximum size of content stored in logs (10KB).
const MaxLogContentSize = 10 * 1024

// TruncateForLog truncates a string to the maximum log content size.
func TruncateForLog(s string) (string, bool) {
	if len(s) <= MaxLogContentSize {
		return s, false
	}
	return s[:MaxLogContentSize], true
}

// BuildRequestLog creates a RequestLog from request processing data.
func BuildRequestLog(
	req *TunnelRequest,
	userCtx *UserContext,
	resp *TunnelResponse,
	policyResult *PolicyResultOutput,
	startTime time.Time,
) *RequestLog {
	processedAt := time.Now()

	log := &RequestLog{
		ID:            NewRequestLogID(),
		Timestamp:     startTime,
		CorrelationID: req.CorrelationID,
		EndpointSlug:  req.Endpoint.Slug,
		EndpointType:  req.Endpoint.Type,
		Timing: &LogTiming{
			ReceivedAt:  startTime,
			ProcessedAt: processedAt,
			DurationMs:  processedAt.Sub(startTime).Milliseconds(),
		},
	}

	// User info
	if userCtx != nil {
		log.User = &LogUserInfo{
			ID:       userCtx.Sub,
			Username: userCtx.Username,
			Email:    userCtx.Email,
			Role:     userCtx.Role,
		}
	}

	// Request info
	log.Request = &LogRequest{
		Type:    req.Endpoint.Type,
		RawSize: len(req.Payload),
	}

	// Response info
	log.Response = &LogResponse{}
	if resp != nil {
		if resp.Status == "success" {
			log.Response.Success = true
			if len(resp.Payload) > 0 {
				content := string(resp.Payload)
				truncated, wasTruncated := TruncateForLog(content)
				log.Response.Content = truncated
				log.Response.ContentTruncated = wasTruncated
			}
		} else {
			log.Response.Success = false
			if resp.Error != nil {
				log.Response.Error = resp.Error.Message
				log.Response.ErrorCode = string(resp.Error.Code)
			}
		}
	}

	// Policy info
	if policyResult != nil {
		log.Policy = &LogPolicy{
			Evaluated:  true,
			Allowed:    policyResult.Allowed,
			PolicyName: policyResult.PolicyName,
			Reason:     policyResult.Reason,
			Pending:    policyResult.Pending,
			Metadata:   policyResult.Metadata,
		}
	}

	return log
}
