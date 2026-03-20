package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"
)

// RequestProcessor handles the execution of endpoint requests.
// It orchestrates authentication and endpoint invocation.
// Note: Policy enforcement is handled by the Python policy_manager.runner
// for file-based endpoints.
type RequestProcessor struct {
	registry   *EndpointRegistry
	authClient *AuthClient
	logger     *slog.Logger
	logHook    RequestLogHook
}

// ProcessorConfig holds configuration for RequestProcessor.
type ProcessorConfig struct {
	Registry   *EndpointRegistry
	AuthClient *AuthClient
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
// It performs authentication, policy checks, handler execution, and response formatting.
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

	// Helper to emit log and return response
	emitLogAndReturn := func(resp *TunnelResponse, userCtx *UserContext) (*TunnelResponse, error) {
		if p.logHook != nil {
			log := BuildRequestLog(req, userCtx, resp, reqCtx.PolicyResult, startTime)
			// Parse request content for logging
			p.enrichLogWithRequestContent(log, req)
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
		return emitLogAndReturn(resp, nil)
	}
	reqCtx.User = userCtx

	p.logger.Info("[REQUEST] User authenticated",
		"correlation_id", req.CorrelationID,
		"user_sub", userCtx.Sub,
		"username", userCtx.Username,
		"email", userCtx.Email,
		"role", userCtx.Role,
	)

	// Get endpoint
	endpoint, ok := p.registry.Get(req.Endpoint.Slug)
	if !ok {
		p.logger.Warn("[REQUEST] Endpoint not found",
			"correlation_id", req.CorrelationID,
			"slug", req.Endpoint.Slug,
		)
		resp := p.errorResponse(req, TunnelErrorCodeEndpointNotFound,
			fmt.Sprintf("endpoint not found: %s", req.Endpoint.Slug))
		return emitLogAndReturn(resp, userCtx)
	}

	p.logger.Info("[REQUEST] Endpoint found",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
		"name", endpoint.Name,
		"type", endpoint.Type,
		"enabled", endpoint.Enabled,
		"is_file_based", endpoint.IsFileBased(),
	)

	if !endpoint.Enabled {
		p.logger.Warn("[REQUEST] Endpoint disabled",
			"correlation_id", req.CorrelationID,
			"slug", req.Endpoint.Slug,
		)
		resp := p.errorResponse(req, TunnelErrorCodeEndpointDisabled,
			fmt.Sprintf("endpoint disabled: %s", req.Endpoint.Slug))
		return emitLogAndReturn(resp, userCtx)
	}

	// Execute handler based on type
	// Note: Policy enforcement is handled by Python policy_manager.runner
	// for file-based endpoints with policies configured.
	p.logger.Info("[REQUEST] Invoking endpoint handler",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
		"user_sub", userCtx.Sub,
	)

	result, err := p.invokeEndpoint(ctx, req, endpoint, reqCtx)
	if err != nil {
		p.logger.Error("[REQUEST] Endpoint execution failed",
			"correlation_id", req.CorrelationID,
			"slug", endpoint.Slug,
			"error", err,
		)
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error())
		return emitLogAndReturn(resp, userCtx)
	}

	p.logger.Info("[REQUEST] Endpoint execution succeeded",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
	)

	reqCtx.Output = result

	// Serialize response
	payload, err := json.Marshal(result)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeInternalError,
			fmt.Sprintf("failed to serialize response: %v", err))
		return emitLogAndReturn(resp, userCtx)
	}

	processedAt := time.Now()
	resp := &TunnelResponse{
		Protocol:      "syfthub-tunnel/v1",
		Type:          "endpoint_response",
		CorrelationID: req.CorrelationID,
		Status:        "success",
		EndpointSlug:  req.Endpoint.Slug,
		Payload:       payload,
		Timing: &TunnelTiming{
			ReceivedAt:  startTime,
			ProcessedAt: processedAt,
			DurationMs:  processedAt.Sub(startTime).Milliseconds(),
		},
	}
	return emitLogAndReturn(resp, userCtx)
}

// enrichLogWithRequestContent parses the request payload and adds content to the log.
func (p *RequestProcessor) enrichLogWithRequestContent(log *RequestLog, req *TunnelRequest) {
	if log.Request == nil {
		return
	}

	switch EndpointType(req.Endpoint.Type) {
	case EndpointTypeModel:
		var modelReq ModelQueryRequest
		if err := json.Unmarshal(req.Payload, &modelReq); err == nil {
			log.Request.Messages = modelReq.Messages
		}
	case EndpointTypeDataSource:
		var dsReq DataSourceQueryRequest
		if err := json.Unmarshal(req.Payload, &dsReq); err == nil {
			log.Request.Query = dsReq.GetQuery()
		}
	case EndpointTypeAgent:
		// Agent sessions use separate handler path; no enrichment needed
	}
}

// verifyToken verifies a satellite token and returns the user context.
func (p *RequestProcessor) verifyToken(ctx context.Context, token string) (*UserContext, error) {
	if p.authClient == nil {
		return nil, &AuthenticationError{Message: "auth client not initialized"}
	}
	return p.authClient.VerifyToken(ctx, token)
}

// invokeEndpoint executes the endpoint handler based on type.
func (p *RequestProcessor) invokeEndpoint(ctx context.Context, req *TunnelRequest, endpoint *Endpoint, reqCtx *RequestContext) (any, error) {
	// Use the actual registered endpoint type, not the request type,
	// so agent endpoints work even when the aggregator sends type="model".
	endpointType := endpoint.Type

	p.logger.Info("[INVOKE] Invoking endpoint",
		"correlation_id", req.CorrelationID,
		"endpoint_type", endpointType,
		"request_type", req.Endpoint.Type,
		"user_sub", reqCtx.User.Sub,
	)

	switch endpointType {
	case EndpointTypeDataSource:
		var dsReq DataSourceQueryRequest
		if err := json.Unmarshal(req.Payload, &dsReq); err != nil {
			return nil, fmt.Errorf("invalid request payload: %w", err)
		}
		reqCtx.Input = dsReq.GetQuery()

		p.logger.Info("[INVOKE] Data source query",
			"correlation_id", req.CorrelationID,
			"query", dsReq.GetQuery(),
			"user_sub", reqCtx.User.Sub,
		)

		docs, err := endpoint.InvokeDataSource(ctx, dsReq.GetQuery(), reqCtx)
		if err != nil {
			p.logger.Error("[INVOKE] Data source invocation failed",
				"correlation_id", req.CorrelationID,
				"error", err,
			)
			return nil, err
		}

		p.logger.Info("[INVOKE] Data source invocation succeeded",
			"correlation_id", req.CorrelationID,
			"docs_count", len(docs),
		)

		return DataSourceQueryResponse{
			References: DataSourceReferences{Documents: docs},
		}, nil

	case EndpointTypeModel:
		var modelReq ModelQueryRequest
		if err := json.Unmarshal(req.Payload, &modelReq); err != nil {
			return nil, fmt.Errorf("invalid request payload: %w", err)
		}
		reqCtx.Input = modelReq.Messages

		p.logger.Info("[INVOKE] Model query",
			"correlation_id", req.CorrelationID,
			"messages_count", len(modelReq.Messages),
			"user_sub", reqCtx.User.Sub,
		)

		// Log each message
		for i, msg := range modelReq.Messages {
			p.logger.Debug("[INVOKE] Message content",
				"correlation_id", req.CorrelationID,
				"index", i,
				"role", msg.Role,
				"content", msg.Content,
			)
		}

		response, err := endpoint.InvokeModel(ctx, modelReq.Messages, reqCtx)
		if err != nil {
			p.logger.Error("[INVOKE] Model invocation failed",
				"correlation_id", req.CorrelationID,
				"error", err,
			)
			return nil, err
		}

		p.logger.Info("[INVOKE] Model invocation succeeded",
			"correlation_id", req.CorrelationID,
			"response_length", len(response),
		)

		return ModelQueryResponse{
			Summary: ModelSummary{
				Message: ModelSummaryMessage{Content: response},
			},
		}, nil

	case EndpointTypeAgent:
		// Enforce policies before starting agent handler.
		policyResult, err := endpoint.CheckPolicies(ctx, reqCtx)
		if err != nil {
			p.logger.Error("[INVOKE] Agent policy check failed",
				"correlation_id", req.CorrelationID, "error", err)
			return nil, fmt.Errorf("policy check failed: %w", err)
		}
		if policyResult != nil {
			reqCtx.PolicyResult = policyResult
			if !policyResult.Allowed {
				p.logger.Warn("[INVOKE] Agent request denied by policy",
					"correlation_id", req.CorrelationID,
					"policy_name", policyResult.PolicyName,
					"reason", policyResult.Reason,
				)
				return nil, &ExecutionError{
					Endpoint: endpoint.Slug,
					Message:  fmt.Sprintf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason),
				}
			}
		}

		// One-shot agent invocation: run the agent handler synchronously,
		// collect all agent.message events, and return as a model response.
		// This allows agent endpoints to work with the regular chat flow.
		var modelReq ModelQueryRequest
		if err := json.Unmarshal(req.Payload, &modelReq); err != nil {
			return nil, fmt.Errorf("invalid request payload: %w", err)
		}
		reqCtx.Input = modelReq.Messages

		// Extract prompt from last user message
		prompt := ""
		for i := len(modelReq.Messages) - 1; i >= 0; i-- {
			if modelReq.Messages[i].Role == "user" {
				prompt = modelReq.Messages[i].Content
				break
			}
		}

		handler, err := endpoint.GetAgentHandler()
		if err != nil {
			return nil, err
		}

		p.logger.Info("[INVOKE] Agent one-shot invocation",
			"correlation_id", req.CorrelationID,
			"prompt_length", len(prompt),
			"messages_count", len(modelReq.Messages),
		)

		// Create a temporary session for one-shot invocation.
		// Use the request context so the session inherits the NATS timeout.
		session := NewAgentSession(
			ctx,
			fmt.Sprintf("oneshot-%s", req.CorrelationID),
			prompt,
			modelReq.Messages,
			AgentConfig{},
			reqCtx.User,
			endpoint.Slug,
		)

		// Run handler via the canonical lifecycle method (spawns goroutine,
		// sends terminal events, closes sendCh/done on completion).
		session.RunHandler(handler)

		// Collect all agent.message events until handler completes.
		// If the agent requests interactive input, cancel the session
		// gracefully instead of auto-responding with fabricated input.
		var buf strings.Builder
		inputRequested := false
		for event := range session.SendCh() {
			switch event.EventType {
			case "agent.message":
				var data map[string]any
				if json.Unmarshal(event.Data, &data) == nil {
					if content, ok := data["content"].(string); ok {
						buf.WriteString(content)
					}
				}
			case "agent.request_input":
				// The agent handler is asking for user input, which
				// cannot be provided in one-shot mode. Cancel the
				// session so the handler's Receive() unblocks with a
				// context error and the handler can exit cleanly.
				inputRequested = true
				p.logger.Info("[INVOKE] Agent requested input in one-shot mode, cancelling session",
					"correlation_id", req.CorrelationID,
				)
				session.Cancel()
			}
		}

		response := buf.String()
		if inputRequested {
			if response != "" {
				response += "\n\n"
			}
			response += "[Note: This agent requires interactive mode. " +
				"It attempted to request user input, which is not supported in one-shot invocation. " +
				"Use an interactive agent session for full functionality.]"
		}
		if response == "" {
			response = "Agent completed without producing a message."
		}

		p.logger.Info("[INVOKE] Agent one-shot invocation succeeded",
			"correlation_id", req.CorrelationID,
			"response_length", len(response),
		)

		return ModelQueryResponse{
			Summary: ModelSummary{
				Message: ModelSummaryMessage{Content: response},
			},
		}, nil

	default:
		p.logger.Error("[INVOKE] Unknown endpoint type",
			"correlation_id", req.CorrelationID,
			"type", endpoint.Type,
		)
		return nil, fmt.Errorf("unknown endpoint type: %s", endpoint.Type)
	}
}

// errorResponse creates an error tunnel response.
func (p *RequestProcessor) errorResponse(req *TunnelRequest, code TunnelErrorCode, message string) *TunnelResponse {
	p.logger.Debug("returning error response",
		"correlation_id", req.CorrelationID,
		"code", code,
		"message", message,
	)
	return &TunnelResponse{
		Protocol:      "syfthub-tunnel/v1",
		Type:          "endpoint_response",
		CorrelationID: req.CorrelationID,
		Status:        "error",
		EndpointSlug:  req.Endpoint.Slug,
		Error: &TunnelError{
			Code:    code,
			Message: message,
		},
	}
}
