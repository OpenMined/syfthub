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

// requireAgentSessionManager returns the AgentSessionManager, or an error if
// the app or API is not ready. Extracts the repeated core→API→SM nil-check chain.
func (a *App) requireAgentSessionManager() (*syfthubapi.AgentSessionManager, error) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return nil, fmt.Errorf("app not running")
	}
	api := core.API()
	if api == nil {
		return nil, fmt.Errorf("API not initialized")
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return nil, fmt.Errorf("agent session manager not initialized")
	}
	return sm, nil
}

// StartAgentSession starts an interactive agent session through the shared
// AgentSessionManager. All session logic (endpoint lookup, policy enforcement,
// handler invocation) is handled by the manager — the same code path used by
// remote NATS sessions. This method only adds the Wails event transport adapter.
func (a *App) StartAgentSession(slug string, prompt string) (string, error) {
	sm, err := a.requireAgentSessionManager()
	if err != nil {
		return "", err
	}

	// Cancel any existing session before starting a new one.
	a.agentMu.Lock()
	if a.agentSessionID != "" {
		_ = sm.CancelSession(a.agentSessionID)
		a.agentSessionID = ""
	}
	a.agentMu.Unlock()

	sessionID := uuid.New().String()
	userCtx := &syfthubapi.UserContext{Username: "local"}

	session, err := sm.StartSession(syfthubapi.AgentSessionStartPayload{
		SessionID:    sessionID,
		Prompt:       prompt,
		EndpointSlug: slug,
	}, userCtx)
	if err != nil {
		return "", fmt.Errorf("failed to start agent session: %w", err)
	}

	a.agentMu.Lock()
	a.agentSessionID = session.ID
	a.agentMu.Unlock()

	// Emit session started event to frontend.
	runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
		Type:      "session.started",
		SessionID: session.ID,
	})

	// Drain events from the session and relay to frontend via Wails events.
	// This is the transport adapter — the only part that differs from the NATS
	// relay in agentNATSBridge.relayEvents().
	go func() {
		sawTerminal := false
		for event := range session.SendCh() {
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
				SessionID: session.ID,
				Data:      data,
			})
		}

		// Ensure the frontend always receives a terminal event to exit "Running" state.
		if !sawTerminal {
			runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
				Type:      "session.completed",
				SessionID: session.ID,
			})
		}

		a.agentMu.Lock()
		if a.agentSessionID == session.ID {
			a.agentSessionID = ""
		}
		a.agentMu.Unlock()
	}()

	return session.ID, nil
}

// SendAgentMessage sends a user message to the active agent session via the
// shared AgentSessionManager.
func (a *App) SendAgentMessage(content string) error {
	sm, err := a.requireAgentSessionManager()
	if err != nil {
		return err
	}

	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentMu.Unlock()

	if sessionID == "" {
		return fmt.Errorf("no active agent session")
	}

	return sm.RouteMessage(syfthubapi.AgentUserMessagePayload{
		SessionID: sessionID,
		Message: syfthubapi.UserMessage{
			Type:    "user_message",
			Content: content,
		},
	})
}

// StopAgentSession cancels the active agent session via the shared
// AgentSessionManager.
func (a *App) StopAgentSession() error {
	sm, err := a.requireAgentSessionManager()
	if err != nil {
		return nil // Idempotent: if app/API not ready, nothing to stop.
	}

	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentSessionID = ""
	a.agentMu.Unlock()

	if sessionID == "" {
		return nil
	}

	return sm.CancelSession(sessionID)
}
