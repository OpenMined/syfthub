package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
)

// EndpointInvoker encapsulates the type-specific behavior of an endpoint.
// Each endpoint type (data_source, model, agent) has its own implementation
// that handles request parsing, handler invocation, response formatting, and
// log enrichment. This eliminates scattered type-switch dispatch across the
// processor and endpoint layers.
type EndpointInvoker interface {
	// ParseRequest extracts the typed input from the raw tunnel payload.
	ParseRequest(payload json.RawMessage) (any, error)

	// Invoke executes the endpoint handler with the parsed input.
	Invoke(ctx context.Context, input any, reqCtx *RequestContext) (any, error)

	// FormatResponse wraps the handler result in the aggregator-expected shape.
	FormatResponse(result any) (any, error)

	// EnrichLog adds type-specific fields to the request log using the
	// already-parsed input (avoids re-unmarshaling the raw payload).
	EnrichLog(log *RequestLog, parsed any)

	// Close releases any resources owned by the invoker (executors, subprocesses, containers).
	Close() error
}

// executeViaExecutor runs an Executor, captures policy results in reqCtx, and
// returns the raw result bytes. Shared by UnifiedInvoker and AgentOneShotInvoker.
func executeViaExecutor(ctx context.Context, exec Executor, input *ExecutorInput, reqCtx *RequestContext, slug string) (json.RawMessage, error) {
	output, err := exec.Execute(ctx, input)
	if err != nil {
		return nil, fmt.Errorf("endpoint %q: subprocess execution failed: %w", slug, err)
	}

	// Capture policy result in request context for logging
	if reqCtx != nil && output.PolicyResult != nil {
		reqCtx.PolicyResult = output.PolicyResult
	}

	if !output.Success {
		if output.ErrorType != "" {
			return nil, fmt.Errorf("endpoint %q: %s (%s)", slug, output.Error, output.ErrorType)
		}
		return nil, fmt.Errorf("endpoint %q: %s", slug, output.Error)
	}

	return output.Result, nil
}

// buildExecutorInput creates an ExecutorInput with the given type and populates
// context and payment credential from the RequestContext.
//
// reqCtx.Metadata is passed through by reference so any keys the caller (or
// upstream gates) wrote into it are visible to the runner. In particular,
// after a successful mppxgate.SettleAfterHandler the following keys flow
// through to the Python policy's post_execute:
//
//   - payment_receipt       (settlement reference + status, set on success)
//   - payment_status        ("settled" / "failed" / chain status)
//   - payment_nonce         (verified nonce, set by PreVerify)
//   - payment_challenge_id  (canonical challenge id used as row primary key)
//
// The processor relies on this passthrough when it re-invokes the executor
// with PolicyPhase == "post" after settlement.
func buildExecutorInput(inputType string, slug string, endpointType EndpointType, reqCtx *RequestContext) *ExecutorInput {
	input := &ExecutorInput{Type: inputType}
	if reqCtx != nil {
		userID := ""
		if reqCtx.User != nil {
			userID = reqCtx.User.Username
		}
		input.Context = &ExecutionContext{
			UserID:       userID,
			EndpointSlug: slug,
			EndpointType: string(endpointType),
			Metadata:     reqCtx.Metadata,
		}
		input.PaymentCredential = reqCtx.PaymentCredential
	}
	return input
}

// errNoHandler returns a standard error for endpoints with no registered handler.
func errNoHandler(slug string) error {
	return fmt.Errorf("endpoint %q: no handler registered", slug)
}

// errInvalidPayload wraps a JSON unmarshal error.
func errInvalidPayload(err error) error {
	return fmt.Errorf("invalid request payload: %w", err)
}
