package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
)

// AgentOneShotInvoker handles agent endpoint invocation in one-shot (non-interactive) mode.
// It creates a temporary session, runs the handler, collects agent.message events,
// and returns the accumulated messages as a ModelQueryResponse.
//
// For persistent interactive sessions, the AgentSessionManager is used directly
// via the NATS transport; this invoker is only for the synchronous request/response flow.
type AgentOneShotInvoker struct {
	codec          EndpointCodec // ModelCodec — agents parse/format like models
	handler        AgentHandler
	policyExecutor Executor
	slug           string
	logger         *slog.Logger
}

func (a *AgentOneShotInvoker) ParseRequest(payload json.RawMessage) (any, error) {
	return a.codec.ParsePayload(payload)
}

func (a *AgentOneShotInvoker) Invoke(ctx context.Context, input any, reqCtx *RequestContext) (any, error) {
	messages := input.([]Message)
	prompt := lastUserContent(messages)

	// Enforce policies before starting agent handler. Pass the latest user
	// content so prompt_filter / token_limit see real input.
	if a.policyExecutor != nil {
		policyResult, err := a.checkPolicies(ctx, reqCtx, prompt)
		if err != nil {
			return nil, fmt.Errorf("policy check failed: %w", err)
		}
		if policyResult != nil {
			reqCtx.PolicyResult = policyResult
			if !policyResult.Allowed {
				return nil, &ExecutionError{
					Endpoint: a.slug,
					Message:  fmt.Sprintf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason),
				}
			}
		}
	}

	if a.handler == nil {
		return nil, errNoHandler(a.slug)
	}

	// Create a temporary session for one-shot invocation.
	session := NewAgentSession(ctx, AgentSessionParams{
		ID:           fmt.Sprintf("oneshot-%s", reqCtx.EndpointSlug),
		Prompt:       prompt,
		EndpointSlug: a.slug,
		Messages:     messages,
		Config:       AgentConfig{},
		User:         reqCtx.User,
	})

	session.RunHandler(a.handler)

	var buf strings.Builder
	inputRequested := false
	for event := range session.SendCh() {
		switch event.EventType {
		case EventTypeAgentMessage:
			var data map[string]any
			if json.Unmarshal(event.Data, &data) == nil {
				if content, ok := data["content"].(string); ok {
					buf.WriteString(content)
				}
			}
		case EventTypeAgentRequestInput:
			inputRequested = true
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

	return response, nil
}

func (a *AgentOneShotInvoker) FormatResponse(result any) (any, error) {
	return a.codec.WrapResponse(result)
}

func (a *AgentOneShotInvoker) EnrichLog(log *RequestLog, parsed any) {
	a.codec.EnrichLog(log, parsed)
}

func (a *AgentOneShotInvoker) Close() error {
	if a.policyExecutor != nil {
		return a.policyExecutor.Close()
	}
	return nil
}

// checkPolicies runs policy evaluation without executing the endpoint handler.
// userContent is the actual user message to evaluate; when empty a placeholder
// is used so existing call sites that don't carry message content still work.
// Passing real content lets prompt_filter / token_limit policies inspect input
// rather than the placeholder.
func (a *AgentOneShotInvoker) checkPolicies(ctx context.Context, reqCtx *RequestContext, userContent string) (*PolicyResultOutput, error) {
	input := buildExecutorInput(string(EndpointTypeAgent), a.slug, EndpointTypeAgent, reqCtx)
	content := userContent
	if content == "" {
		content = "policy_check"
	}
	input.Messages = []Message{{Role: "user", Content: content}}
	// Signal the executor to skip handler invocation. Required for container
	// mode where the real handler is always loaded (no separate noop handler
	// file exists unlike subprocess mode).
	input.PolicyCheckOnly = true

	output, err := a.policyExecutor.Execute(ctx, input)
	if err != nil {
		return nil, fmt.Errorf("policy check failed: %w", err)
	}
	return output.PolicyResult, nil
}

// lastUserContent returns the Content of the most recent user message in
// messages, or "" if there is none. Used by both the one-shot Invoke path
// (to extract the prompt) and the policy gate (to pass real input to
// prompt_filter / token_limit).
func lastUserContent(messages []Message) string {
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Role == "user" {
			return messages[i].Content
		}
	}
	return ""
}

// Ensure AgentOneShotInvoker implements the interface at compile time.
var _ EndpointInvoker = (*AgentOneShotInvoker)(nil)
