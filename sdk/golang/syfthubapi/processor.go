package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"
)

// RequestProcessor handles the execution of endpoint requests.
// It orchestrates authentication and endpoint invocation.
type RequestProcessor struct {
	registry   *EndpointRegistry
	authClient *HubClient
	logger     *slog.Logger
	logHook    RequestLogHook
}

// ProcessorConfig holds configuration for RequestProcessor.
type ProcessorConfig struct {
	Registry   *EndpointRegistry
	AuthClient *HubClient
	Logger     *slog.Logger
}

// NewRequestProcessor creates a new request processor.
func NewRequestProcessor(cfg *ProcessorConfig) *RequestProcessor {
	return &RequestProcessor{
		registry:   cfg.Registry,
		authClient: cfg.AuthClient,
		logger:     cfg.Logger,
	}
}

// SetLogHook sets the request log hook callback.
// The hook is called after each request is processed with the full log entry.
func (p *RequestProcessor) SetLogHook(hook RequestLogHook) {
	p.logHook = hook
}

// Process handles an incoming tunnel request.
// It performs authentication, endpoint lookup, handler execution, and response formatting.
func (p *RequestProcessor) Process(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
	startTime := time.Now()

	p.logger.Info("[REQUEST] ========== INCOMING REQUEST ==========",
		"correlation_id", req.CorrelationID,
		"endpoint", req.Endpoint.Slug,
		"endpoint_type", req.Endpoint.Type,
		"has_token", req.SatelliteToken != "",
		"payload_size", len(req.Payload),
	)

	p.logger.Debug("[REQUEST] Raw payload",
		"correlation_id", req.CorrelationID,
		"payload", string(req.Payload),
	)

	// Create request context
	reqCtx := NewRequestContext()
	reqCtx.EndpointSlug = req.Endpoint.Slug
	reqCtx.EndpointType = EndpointType(req.Endpoint.Type)

	// emitLogAndReturn emits the request log (if a hook is configured) and returns
	// the response. ep is the resolved endpoint (nil if lookup failed or auth was
	// rejected before lookup ran), enabling type-specific log enrichment.
	emitLogAndReturn := func(resp *TunnelResponse, userCtx *UserContext, ep *Endpoint) (*TunnelResponse, error) {
		if p.logHook != nil {
			log := BuildRequestLog(req, userCtx, resp, reqCtx.PolicyResult, startTime)
			if log.Request != nil {
				p.enrichLog(log, req, ep)
			}
			p.logHook(ctx, log)
		}
		return resp, nil
	}

	// Verify token and get user context
	userCtx, err := p.verifyToken(ctx, req.SatelliteToken)
	if err != nil {
		p.logger.Warn("[REQUEST] Token verification failed",
			"correlation_id", req.CorrelationID,
			"error", err,
		)
		resp := p.errorResponse(req, TunnelErrorCodeAuthFailed, err.Error())
		return emitLogAndReturn(resp, nil, nil)
	}
	reqCtx.User = userCtx

	p.logger.Info("[REQUEST] User authenticated",
		"correlation_id", req.CorrelationID,
		"user_sub", userCtx.Sub,
		"username", userCtx.Username,
	)

	// Get endpoint
	endpoint, ok := p.registry.Get(req.Endpoint.Slug)
	if !ok {
		resp := p.errorResponse(req, TunnelErrorCodeEndpointNotFound,
			fmt.Sprintf("endpoint not found: %s", req.Endpoint.Slug))
		return emitLogAndReturn(resp, userCtx, nil)
	}

	if !endpoint.Enabled {
		resp := p.errorResponse(req, TunnelErrorCodeEndpointDisabled,
			fmt.Sprintf("endpoint disabled: %s", req.Endpoint.Slug))
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	if endpoint.invoker == nil {
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed,
			fmt.Sprintf("no handler registered for endpoint: %s", req.Endpoint.Slug))
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	// Generic invocation pipeline: parse → invoke → format
	p.logger.Info("[REQUEST] Invoking endpoint",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
		"type", endpoint.Type,
	)

	input, err := endpoint.invoker.ParseRequest(req.Payload)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}
	reqCtx.Input = input

	result, err := endpoint.invoker.Invoke(ctx, input, reqCtx)
	if err != nil {
		p.logger.Error("[REQUEST] Endpoint execution failed",
			"correlation_id", req.CorrelationID,
			"slug", endpoint.Slug,
			"error", err,
		)
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	formatted, err := endpoint.invoker.FormatResponse(result)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeInternalError, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	reqCtx.Output = formatted

	p.logger.Info("[REQUEST] Endpoint execution succeeded",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
	)

	// Serialize response
	payload, err := json.Marshal(formatted)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeInternalError,
			fmt.Sprintf("failed to serialize response: %v", err))
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	processedAt := time.Now()
	resp := &TunnelResponse{
		Protocol:      TunnelProtocolV1,
		Type:          TunnelTypeResponse,
		CorrelationID: req.CorrelationID,
		Status:        TunnelStatusSuccess,
		EndpointSlug:  req.Endpoint.Slug,
		Payload:       payload,
		Timing: &TunnelTiming{
			ReceivedAt:  startTime,
			ProcessedAt: processedAt,
			DurationMs:  processedAt.Sub(startTime).Milliseconds(),
		},
	}
	return emitLogAndReturn(resp, userCtx, endpoint)
}

// enrichLog delegates type-specific log enrichment to the endpoint's invoker.
// endpoint may be nil (e.g. for error responses where lookup failed); in that
// case the function falls back to payload-based type inference.
func (p *RequestProcessor) enrichLog(log *RequestLog, req *TunnelRequest, endpoint *Endpoint) {
	if endpoint != nil && endpoint.invoker != nil {
		endpoint.invoker.EnrichLog(log, req.Payload)
		return
	}
	p.enrichLogFallback(log, req)
}

// enrichLogFallback parses the request payload based on type string for logging.
// Used when the endpoint's invoker is not available.
func (p *RequestProcessor) enrichLogFallback(log *RequestLog, req *TunnelRequest) {
	if log.Request == nil {
		return
	}
	switch EndpointType(req.Endpoint.Type) {
	case EndpointTypeModel, EndpointTypeAgent:
		var modelReq ModelQueryRequest
		if err := json.Unmarshal(req.Payload, &modelReq); err == nil {
			log.Request.Messages = modelReq.Messages
		}
	case EndpointTypeDataSource:
		var dsReq DataSourceQueryRequest
		if err := json.Unmarshal(req.Payload, &dsReq); err == nil {
			log.Request.Query = dsReq.GetQuery()
		}
	}
}

// verifyToken verifies a satellite token and returns the user context.
func (p *RequestProcessor) verifyToken(ctx context.Context, token string) (*UserContext, error) {
	if p.authClient == nil {
		return nil, &AuthenticationError{Message: "auth client not initialized"}
	}
	return p.authClient.VerifyToken(ctx, token)
}

// errorResponse creates an error tunnel response.
func (p *RequestProcessor) errorResponse(req *TunnelRequest, code TunnelErrorCode, message string) *TunnelResponse {
	p.logger.Debug("returning error response",
		"correlation_id", req.CorrelationID,
		"code", code,
		"message", message,
	)
	return &TunnelResponse{
		Protocol:      TunnelProtocolV1,
		Type:          TunnelTypeResponse,
		CorrelationID: req.CorrelationID,
		Status:        TunnelStatusError,
		EndpointSlug:  req.Endpoint.Slug,
		Error: &TunnelError{
			Code:    code,
			Message: message,
		},
	}
}
