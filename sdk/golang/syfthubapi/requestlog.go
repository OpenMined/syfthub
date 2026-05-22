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
	// Derived from Timing.ReceivedAt; kept for JSON compatibility and external consumers.
	Timestamp time.Time `json:"timestamp"`

	// CorrelationID is the request tracking ID from the tunnel protocol.
	CorrelationID string `json:"correlation_id"`

	// EndpointSlug is the target endpoint identifier.
	EndpointSlug string `json:"endpoint_slug"`

	// EndpointType is "model", "data_source", or "agent".
	EndpointType string `json:"endpoint_type"`

	// User contains the authenticated user information.
	User *LogUserInfo `json:"user,omitempty"`

	// Request contains the request details.
	Request *LogRequest `json:"request"`

	// Response contains the response details.
	Response *LogResponse `json:"response"`

	// Policy contains policy evaluation results (if policies were applied).
	Policy *LogPolicy `json:"policy,omitempty"`

	// Payment contains payment information when a TransactionPolicy required
	// (and possibly verified) an on-chain payment for this request. Nil when
	// the endpoint had no payment policy attached.
	Payment *PaymentLog `json:"payment,omitempty"`

	// Timing contains timing information.
	Timing *LogTiming `json:"timing"`

	// Status is the lifecycle state of the request this entry describes.
	// For agent sessions, multiple snapshots may be emitted with the same ID
	// as the session progresses: LogStatusRunning while in flight, then one
	// terminal value (LogStatusCompleted, LogStatusFailed, LogStatusTerminated)
	// when the session ends. Old entries written before this field existed
	// decode as "" — readers should treat empty as terminal.
	Status string `json:"status,omitempty"`
}

// Lifecycle values for RequestLog.Status. Empty string is treated as terminal
// by readers (back-compat with logs written before this field existed).
// LogStatusTerminated is the state for a session ended by an external actor
// (user Stop, manager shutdown) — distinct from LogStatusCompleted (handler
// returned nil) and LogStatusFailed (handler returned an error).
const (
	LogStatusRunning    = "running"
	LogStatusCompleted  = "completed"
	LogStatusFailed     = "failed"
	LogStatusTerminated = "terminated"
)

// PaymentLog captures on-chain payment metadata for a request that flowed
// through a TransactionPolicy. It records both the issued challenge and, if
// the caller settled it, the resulting on-chain transaction.
type PaymentLog struct {
	// ChallengeID is the unique identifier for the payment challenge issued
	// to the caller (mirrors the `id` field of the WWW-Authenticate-style header).
	ChallengeID string `json:"challenge_id"`

	// TxHash is the on-chain transaction hash that settled the challenge.
	// Empty when the request was rejected with PAYMENT_REQUIRED before settlement.
	TxHash string `json:"tx_hash,omitempty"`

	// Amount is the required payment amount, stringified to preserve precision
	// (e.g., "0.10").
	Amount string `json:"amount"`

	// Currency is the token contract address or symbol (e.g., a PathUSD address).
	Currency string `json:"currency"`

	// Recipient is the on-chain address that should receive (or did receive)
	// the payment.
	Recipient string `json:"recipient"`

	// Status is one of "required", "verified", or "failed".
	Status string `json:"status"`

	// PaidAt is the RFC3339 timestamp the payment was verified on-chain.
	// Empty when Status is "required" or "failed".
	PaidAt string `json:"paid_at,omitempty"`
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

// NewLogPolicyFromResult projects a PolicyResultOutput into the on-the-wire
// LogPolicy shape. Returns nil when the result is nil so callers can assign
// the result directly to RequestLog.Policy.
func NewLogPolicyFromResult(r *PolicyResultOutput) *LogPolicy {
	if r == nil {
		return nil
	}
	return &LogPolicy{
		Evaluated:  true,
		Allowed:    r.Allowed,
		PolicyName: r.PolicyName,
		Reason:     r.Reason,
		Pending:    r.Pending,
		Metadata:   r.Metadata,
	}
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

	timing := &LogTiming{
		ReceivedAt:  startTime,
		ProcessedAt: processedAt,
		DurationMs:  processedAt.Sub(startTime).Milliseconds(),
	}

	log := &RequestLog{
		ID:            NewRequestLogID(),
		Timestamp:     timing.ReceivedAt,
		CorrelationID: req.CorrelationID,
		EndpointSlug:  req.Endpoint.Slug,
		EndpointType:  req.Endpoint.Type,
		Timing:        timing,
		// Status is set below once we know whether the response succeeded.
		Status: LogStatusCompleted,
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
			log.Status = LogStatusFailed
			if resp.Error != nil {
				log.Response.Error = resp.Error.Message
				log.Response.ErrorCode = string(resp.Error.Code)
			}
		}
	}

	// Policy info
	log.Policy = NewLogPolicyFromResult(policyResult)

	// Payment info — populated from transaction policy metadata.
	if policyResult != nil && policyResult.Metadata != nil {
		getStr := func(k string) string {
			if v, ok := policyResult.Metadata[k].(string); ok {
				return v
			}
			return ""
		}
		challengeID := getStr("challenge_id")
		amount := getStr("payment_amount")
		currency := getStr("payment_currency")
		recipient := getStr("payment_recipient")
		txHash := getStr("tx_hash")

		if challengeID != "" || amount != "" || txHash != "" {
			status := "required"
			if policyResult.Allowed && txHash != "" {
				status = "verified"
			} else if !policyResult.Allowed && !policyResult.Pending {
				status = "failed"
			}
			paidAt := ""
			if status == "verified" {
				paidAt = time.Now().UTC().Format(time.RFC3339)
			}
			log.Payment = &PaymentLog{
				ChallengeID: challengeID,
				TxHash:      txHash,
				Amount:      amount,
				Currency:    currency,
				Recipient:   recipient,
				Status:      status,
				PaidAt:      paidAt,
			}
		}
	}

	return log
}
