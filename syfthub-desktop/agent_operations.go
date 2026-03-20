package main

import (
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// AgentStreamEvent is emitted on "agent:event" for every event from an agent session.
type AgentStreamEvent struct {
	Type      string         `json:"type"`
	SessionID string         `json:"sessionId"`
	Data      map[string]any `json:"data,omitempty"`
}

// StartAgentSession starts a local interactive agent session.
// Events are streamed to the frontend via "agent:event" Wails events.
// Returns the session ID.
func (a *App) StartAgentSession(slug string, prompt string) (string, error) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return "", fmt.Errorf("app not running")
	}

	api := core.API()
	if api == nil {
		return "", fmt.Errorf("API not initialized")
	}

	// Look up the endpoint
	endpoint, ok := api.Registry().Get(slug)
	if !ok {
		return "", fmt.Errorf("endpoint not found: %s", slug)
	}

	handler, err := endpoint.GetAgentHandler()
	if err != nil {
		return "", fmt.Errorf("endpoint %s is not an agent: %w", slug, err)
	}

	// Enforce policies before starting the handler.
	userCtx := &syfthubapi.UserContext{Username: "local"}
	reqCtx := &syfthubapi.RequestContext{User: userCtx}
	policyResult, err := endpoint.CheckPolicies(a.ctx, reqCtx)
	if err != nil {
		return "", fmt.Errorf("policy check failed for %s: %w", slug, err)
	}
	if policyResult != nil && !policyResult.Allowed {
		return "", fmt.Errorf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason)
	}

	// Cancel any existing session
	a.agentMu.Lock()
	if a.agentCancel != nil {
		a.agentCancel()
	}

	sessionID := uuid.New().String()

	session := syfthubapi.NewAgentSession(
		a.ctx,
		sessionID,
		prompt,
		nil, // messages
		syfthubapi.AgentConfig{},
		userCtx,
		slug,
	)
	a.agentSession = session
	a.agentCancel = session.Cancel
	a.agentMu.Unlock()

	// Start handler (spawns goroutine, closes sendCh/done on completion)
	session.RunHandler(handler)

	// Emit session started
	runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
		Type:      "session.started",
		SessionID: sessionID,
	})

	// Drain events from the session and relay to frontend
	go func() {
		sawTerminal := false
		for event := range session.SendCh() {
			// Parse raw JSON data into map for frontend
			var data map[string]any
			if event.Data != nil {
				if err := json.Unmarshal(event.Data, &data); err != nil {
					data = map[string]any{"raw": string(event.Data)}
				}
			}

			if event.EventType == "session.completed" || event.EventType == "session.failed" {
				sawTerminal = true
			}

			runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
				Type:      event.EventType,
				SessionID: sessionID,
				Data:      data,
			})
		}

		// Ensure the frontend always receives a terminal event to exit "Running" state
		if !sawTerminal {
			runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
				Type:      "session.completed",
				SessionID: sessionID,
			})
		}

		// Clean up
		a.agentMu.Lock()
		if a.agentSession != nil && a.agentSession.ID == sessionID {
			a.agentSession = nil
			a.agentCancel = nil
		}
		a.agentMu.Unlock()
	}()

	return sessionID, nil
}

// SendAgentMessage sends a user message to the active agent session.
func (a *App) SendAgentMessage(content string) error {
	a.agentMu.Lock()
	session := a.agentSession
	a.agentMu.Unlock()

	if session == nil {
		return fmt.Errorf("no active agent session")
	}

	ok := session.DeliverMessage(syfthubapi.UserMessage{
		Type:    "user_message",
		Content: content,
	})
	if !ok {
		return fmt.Errorf("session message buffer full")
	}
	return nil
}

// StopAgentSession cancels the active agent session.
func (a *App) StopAgentSession() error {
	a.agentMu.Lock()
	defer a.agentMu.Unlock()

	if a.agentCancel != nil {
		a.agentCancel()
		a.agentCancel = nil
	}
	a.agentSession = nil
	return nil
}
