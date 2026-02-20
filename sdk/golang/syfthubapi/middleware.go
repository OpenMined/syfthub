package syfthubapi

import (
	"context"
	"log/slog"
	"time"
)

// Middleware is a function that wraps a RequestHandler.
type Middleware func(next RequestHandler) RequestHandler

// MiddlewareChain builds a chain of middleware.
type MiddlewareChain struct {
	middleware []Middleware
}

// NewMiddlewareChain creates a new middleware chain.
func NewMiddlewareChain(middleware ...Middleware) *MiddlewareChain {
	return &MiddlewareChain{
		middleware: middleware,
	}
}

// Add adds middleware to the chain.
func (c *MiddlewareChain) Add(mw Middleware) {
	c.middleware = append(c.middleware, mw)
}

// Then wraps a handler with all middleware in the chain.
func (c *MiddlewareChain) Then(handler RequestHandler) RequestHandler {
	// Apply middleware in reverse order so first added runs first
	for i := len(c.middleware) - 1; i >= 0; i-- {
		handler = c.middleware[i](handler)
	}
	return handler
}

// LoggingMiddleware logs request/response information.
func LoggingMiddleware(logger *slog.Logger) Middleware {
	return func(next RequestHandler) RequestHandler {
		return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			start := time.Now()

			logger.Info("request started",
				"correlation_id", req.CorrelationID,
				"endpoint", req.Endpoint.Slug,
				"type", req.Endpoint.Type,
			)

			resp, err := next(ctx, req)

			duration := time.Since(start)

			if err != nil {
				logger.Error("request failed",
					"correlation_id", req.CorrelationID,
					"endpoint", req.Endpoint.Slug,
					"duration_ms", duration.Milliseconds(),
					"error", err,
				)
			} else if resp.Status == "error" {
				logger.Warn("request error",
					"correlation_id", req.CorrelationID,
					"endpoint", req.Endpoint.Slug,
					"duration_ms", duration.Milliseconds(),
					"error_code", resp.Error.Code,
					"error_message", resp.Error.Message,
				)
			} else {
				logger.Info("request completed",
					"correlation_id", req.CorrelationID,
					"endpoint", req.Endpoint.Slug,
					"duration_ms", duration.Milliseconds(),
					"status", resp.Status,
				)
			}

			return resp, err
		}
	}
}

// RecoveryMiddleware recovers from panics in handlers.
func RecoveryMiddleware(logger *slog.Logger) Middleware {
	return func(next RequestHandler) RequestHandler {
		return func(ctx context.Context, req *TunnelRequest) (resp *TunnelResponse, err error) {
			defer func() {
				if r := recover(); r != nil {
					logger.Error("handler panic recovered",
						"correlation_id", req.CorrelationID,
						"endpoint", req.Endpoint.Slug,
						"panic", r,
					)

					resp = &TunnelResponse{
						Protocol:      "syfthub-tunnel/v1",
						Type:          "endpoint_response",
						CorrelationID: req.CorrelationID,
						Status:        "error",
						EndpointSlug:  req.Endpoint.Slug,
						Error: &TunnelError{
							Code:    TunnelErrorCodeInternalError,
							Message: "internal server error",
						},
					}
				}
			}()

			return next(ctx, req)
		}
	}
}

// TimeoutMiddleware adds a timeout to request processing.
func TimeoutMiddleware(timeout time.Duration) Middleware {
	return func(next RequestHandler) RequestHandler {
		return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			ctx, cancel := context.WithTimeout(ctx, timeout)
			defer cancel()

			// Channel for the response
			type result struct {
				resp *TunnelResponse
				err  error
			}
			ch := make(chan result, 1)

			go func() {
				resp, err := next(ctx, req)
				ch <- result{resp, err}
			}()

			select {
			case <-ctx.Done():
				if ctx.Err() == context.DeadlineExceeded {
					return &TunnelResponse{
						Protocol:      "syfthub-tunnel/v1",
						Type:          "endpoint_response",
						CorrelationID: req.CorrelationID,
						Status:        "error",
						EndpointSlug:  req.Endpoint.Slug,
						Error: &TunnelError{
							Code:    TunnelErrorCodeTimeout,
							Message: "request timeout",
						},
					}, nil
				}
				return &TunnelResponse{
					Protocol:      "syfthub-tunnel/v1",
					Type:          "endpoint_response",
					CorrelationID: req.CorrelationID,
					Status:        "error",
					EndpointSlug:  req.Endpoint.Slug,
					Error: &TunnelError{
						Code:    TunnelErrorCodeInternalError,
						Message: "request cancelled",
					},
				}, nil
			case r := <-ch:
				return r.resp, r.err
			}
		}
	}
}

// MetricsMiddleware collects request metrics.
type MetricsCollector interface {
	RecordRequest(endpoint string, duration time.Duration, status string)
}

// MetricsMiddleware creates middleware that collects metrics.
func MetricsMiddleware(collector MetricsCollector) Middleware {
	return func(next RequestHandler) RequestHandler {
		return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			start := time.Now()
			resp, err := next(ctx, req)
			duration := time.Since(start)

			status := "success"
			if err != nil || (resp != nil && resp.Status == "error") {
				status = "error"
			}

			collector.RecordRequest(req.Endpoint.Slug, duration, status)

			return resp, err
		}
	}
}

// CorrelationIDMiddleware ensures each request has a unique correlation ID.
func CorrelationIDMiddleware() Middleware {
	return func(next RequestHandler) RequestHandler {
		return func(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
			if req.CorrelationID == "" {
				req.CorrelationID = generateRequestID()
			}
			return next(ctx, req)
		}
	}
}

// RequestIDMiddleware is an alias for CorrelationIDMiddleware for backward compatibility.
// Deprecated: Use CorrelationIDMiddleware instead.
func RequestIDMiddleware() Middleware {
	return CorrelationIDMiddleware()
}

// generateRequestID generates a unique request ID.
func generateRequestID() string {
	return time.Now().Format("20060102150405.000000000")
}

// Logger interface for components that need logging.
type Logger interface {
	Debug(msg string, args ...any)
	Info(msg string, args ...any)
	Warn(msg string, args ...any)
	Error(msg string, args ...any)
}

// SlogLogger wraps slog.Logger to implement Logger interface.
type SlogLogger struct {
	*slog.Logger
}

// NewSlogLogger creates a new SlogLogger.
func NewSlogLogger(logger *slog.Logger) *SlogLogger {
	return &SlogLogger{Logger: logger}
}

// Debug logs at debug level.
func (l *SlogLogger) Debug(msg string, args ...any) {
	l.Logger.Debug(msg, args...)
}

// Info logs at info level.
func (l *SlogLogger) Info(msg string, args ...any) {
	l.Logger.Info(msg, args...)
}

// Warn logs at warn level.
func (l *SlogLogger) Warn(msg string, args ...any) {
	l.Logger.Warn(msg, args...)
}

// Error logs at error level.
func (l *SlogLogger) Error(msg string, args ...any) {
	l.Logger.Error(msg, args...)
}
