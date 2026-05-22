package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"
)

// MppxGate is the interface the processor uses to drive the x402 settle-on-
// success flow. The concrete implementation lives in the mppxgate package
// (TempoGate); the interface is mirrored here so the processor can hold it
// without importing mppxgate back (an import cycle).
//
// All three methods accept and mutate the policy-result / request-context
// metadata map. They are intentionally pointer-free and have no syfthubapi
// types in their signatures, so mppxgate stays a leaf package.
type MppxGate interface {
	// PreVerify is called BEFORE invoker.ParseRequest when the caller
	// supplied a payment_credential. Implementations verify the credential
	// (HMAC + sender recovery + amount/recipient match + nonce freshness)
	// and, on success, populate metadata with payment_verified=true plus
	// payment_challenge_id / payment_nonce / payment_signed_tx_hex so the
	// Python policy short-circuits its second pre_execute.
	PreVerify(ctx context.Context, credential string, metadata map[string]any) error

	// BuildChallenge is called when a policy result is Pending and carries
	// an x402_challenge_spec. Implementations materialize the HMAC-bound
	// mppx Challenge from the spec and write payment_challenge / amount /
	// currency / recipient / challenge_id into resultMeta.
	BuildChallenge(ctx context.Context, spec map[string]any, resultMeta map[string]any) error

	// SettleAfterHandler is called AFTER invoker.Invoke succeeds. It
	// broadcasts the signed transfer previously parked in metadata by
	// PreVerify, then writes payment_receipt / payment_status so the
	// Python post_execute can record settlement. No-op when metadata
	// carries no signed tx.
	SettleAfterHandler(ctx context.Context, metadata map[string]any) error
}

// RequestProcessor handles the execution of endpoint requests.
// It orchestrates authentication and endpoint invocation.
type RequestProcessor struct {
	registry   *EndpointRegistry
	authClient *HubClient
	logger     *slog.Logger
	logHook    RequestLogHook
	gate       MppxGate
}

// ProcessorConfig holds configuration for RequestProcessor.
type ProcessorConfig struct {
	Registry   *EndpointRegistry
	AuthClient *HubClient
	Logger     *slog.Logger
	// Gate is the optional x402 mppx gate. When nil the processor behaves
	// exactly as before (no PreVerify, no BuildChallenge, no settle).
	Gate MppxGate
}

// NewRequestProcessor creates a new request processor.
func NewRequestProcessor(cfg *ProcessorConfig) *RequestProcessor {
	return &RequestProcessor{
		registry:   cfg.Registry,
		authClient: cfg.AuthClient,
		logger:     cfg.Logger,
		gate:       cfg.Gate,
	}
}

// SetMppxGate installs (or replaces) the mppx gate. Safe to call after
// construction; not safe to swap mid-request.
func (p *RequestProcessor) SetMppxGate(gate MppxGate) {
	p.gate = gate
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

	p.logger.Debug("[REQUEST] incoming",
		"correlation_id", req.CorrelationID,
		"endpoint", req.Endpoint.Slug,
		"endpoint_type", req.Endpoint.Type,
		"has_token", req.SatelliteToken != "",
		"payload_size", len(req.Payload),
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
				p.enrichLog(log, req, ep, reqCtx.Input)
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
	reqCtx.PaymentCredential = req.PaymentCredential

	p.logger.Debug("[REQUEST] user authenticated",
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

	p.logger.Debug("[REQUEST] invoking endpoint",
		"correlation_id", req.CorrelationID,
		"slug", endpoint.Slug,
		"type", endpoint.Type,
	)

	// Verify a presented payment credential up-front, BEFORE invoking the
	// handler. A failure here is non-fatal: we log it and fall through —
	// the Python pre_execute will see no payment_verified flag in metadata
	// and return a fresh challenge spec, which the policy chain surfaces
	// as a PAYMENT_REQUIRED via the maybeBuildChallenge path below. Doing
	// it pre-handler (rather than inside the policy) keeps the crypto in
	// Go and matches the "settle on success" lifecycle: PreVerify parks
	// the signed tx, the handler runs, SettleAfterHandler broadcasts.
	if reqCtx.PaymentCredential != "" && p.gate != nil {
		if err := p.gate.PreVerify(ctx, reqCtx.PaymentCredential, reqCtx.Metadata); err != nil {
			p.logger.Info("[REQUEST] payment credential pre-verify failed; policy will issue fresh challenge",
				"correlation_id", req.CorrelationID,
				"slug", endpoint.Slug,
				"error", err,
			)
		}
	}

	input, err := endpoint.invoker.ParseRequest(req.Payload)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}
	reqCtx.Input = input

	result, err := endpoint.invoker.Invoke(ctx, input, reqCtx)
	if err != nil {
		if resp := p.maybeBuildChallenge(ctx, req, reqCtx); resp != nil {
			return emitLogAndReturn(resp, userCtx, endpoint)
		}
		p.logger.Error("[REQUEST] Endpoint execution failed",
			"correlation_id", req.CorrelationID,
			"slug", endpoint.Slug,
			"error", err,
		)
		resp := p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	// Handler succeeded — settle the parked payment (no-op when none is
	// parked). Errors are non-fatal: the response still goes out, and the
	// gate writes a payment_failure into metadata so post_execute can
	// record the failed settlement attempt.
	if p.gate != nil {
		if err := p.gate.SettleAfterHandler(ctx, reqCtx.Metadata); err != nil {
			p.logger.Warn("[REQUEST] payment settlement failed after successful handler",
				"correlation_id", req.CorrelationID,
				"slug", endpoint.Slug,
				"error", err,
			)
		}
	}

	formatted, err := endpoint.invoker.FormatResponse(result)
	if err != nil {
		resp := p.errorResponse(req, TunnelErrorCodeInternalError, err.Error())
		return emitLogAndReturn(resp, userCtx, endpoint)
	}

	reqCtx.Output = formatted

	p.logger.Debug("[REQUEST] endpoint execution succeeded",
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
// case the function falls back to payload-based type inference. parsedInput is
// the value produced by ParseRequest (nil when parsing did not run).
func (p *RequestProcessor) enrichLog(log *RequestLog, req *TunnelRequest, endpoint *Endpoint, parsedInput any) {
	if endpoint != nil && endpoint.invoker != nil && parsedInput != nil {
		endpoint.invoker.EnrichLog(log, parsedInput)
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
		return nil, fmt.Errorf("authentication: auth client not initialized")
	}
	return p.authClient.VerifyToken(ctx, token)
}

// maybeBuildChallenge builds a PAYMENT_REQUIRED tunnel response when the
// policy chain returned a Pending result carrying either:
//
//   - an x402_challenge_spec (Python X402PayPerRequestPolicy round 1): the
//     gate materializes the canonical HMAC-bound challenge in-place and the
//     processor surfaces it as a PAYMENT_REQUIRED.
//   - a pre-built payment_challenge wire string in metadata (legacy path used
//     by other payment policies): surfaced unchanged.
//
// Returns nil if the request did not surface a payment challenge.
func (p *RequestProcessor) maybeBuildChallenge(ctx context.Context, req *TunnelRequest, reqCtx *RequestContext) *TunnelResponse {
	if reqCtx.PolicyResult == nil || !reqCtx.PolicyResult.Pending {
		return nil
	}
	meta := reqCtx.PolicyResult.Metadata
	if meta == nil {
		return nil
	}

	// Legacy short-circuit: if metadata already has a payment_challenge,
	// trust it and skip BuildChallenge. Some payment policies build the
	// challenge themselves (e.g. the old MppAccountingPolicy path).
	if _, ok := PaymentChallengeFromMetadata(meta); !ok {
		// New x402 path: materialize the challenge from the Python spec.
		spec, ok := meta["x402_challenge_spec"].(map[string]any)
		if !ok || spec == nil {
			return nil
		}
		if p.gate == nil {
			p.logger.Warn("[REQUEST] x402 challenge spec present but no gate configured",
				"correlation_id", req.CorrelationID)
			return nil
		}
		if err := p.gate.BuildChallenge(ctx, spec, meta); err != nil {
			p.logger.Error("[REQUEST] failed to build x402 challenge",
				"correlation_id", req.CorrelationID, "error", err)
			return nil
		}
	}

	details := CopyPaymentMetadata(meta)
	p.logger.Info("[REQUEST] Payment required",
		"correlation_id", req.CorrelationID,
		"challenge_id", details["challenge_id"],
		"amount", details["payment_amount"],
	)
	resp := p.errorResponse(req, TunnelErrorCodePaymentRequired, "payment required")
	resp.Error.Details = details
	return resp
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
