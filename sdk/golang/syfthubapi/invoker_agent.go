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
	codec   EndpointCodec // ModelCodec — agents parse/format like models
	handler AgentHandler
	// policyExecutor is retained only so Close() can release it. Policy
	// evaluation itself is woven into `handler` by AgentExecutor.
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

	// Policy enforcement is woven into the handler by AgentExecutor (when the
	// endpoint declares policies) — see Endpoint.SetHandler. The invoker just
	// runs the handler; a policy denial arrives as an event in the stream.
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

// lastUserContent returns the Content of the most recent user message in
// messages, or "" if there is none. Used by the one-shot Invoke path to
// extract the prompt for the temporary session.
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
