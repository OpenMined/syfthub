// Package main: chat agent session bindings.
//
// Every chat session is routed through the SyftHub aggregator via the hub
// WebSocket, which tunnels to the host running the agent over NATS. The
// AgentSessionClient owns the WebSocket; this file relays its typed events
// onto the Wails "agent:event" channel and tracks user-initiated cancellation.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// AgentStreamEvent is emitted on "agent:event" for every event from an agent session.
type AgentStreamEvent struct {
	Type      string         `json:"type"`
	SessionID string         `json:"sessionId"`
	Data      map[string]any `json:"data,omitempty"`
}

// agentStartTimeout caps the WebSocket handshake + session.created roundtrip.
const agentStartTimeout = 30 * time.Second

// StartAgentSession opens a network-routed agent session for the given endpoint
// path ("owner/slug"), blocks for the session.created handshake, and returns
// the session ID. Streaming events flow asynchronously through the "agent:event"
// Wails channel.
//
// Any previous session is cancelled before the new one starts so the frontend
// only ever has one live transcript.
func (a *App) StartAgentSession(endpointPath string, prompt string) (string, error) {
	a.mu.RLock()
	client := a.syftClient
	a.mu.RUnlock()
	if client == nil {
		return "", fmt.Errorf("hub client not initialized — log in to start an agent session")
	}

	// Swap out any previous session under the agent mutex. Marking the previous
	// session as cancelled BEFORE closing it ensures the drain goroutine rewrites
	// its terminal event to session.cancelled rather than session.failed. The
	// inbound attachment cache is dropped — it belonged to the old session and
	// fileIDs are scoped per-session.
	a.agentMu.Lock()
	prev := a.agentSession
	a.agentSession = nil
	a.agentAttachments = nil
	if prev != nil {
		a.agentCancelledID = prev.SessionID
	}
	a.agentMu.Unlock()

	if prev != nil {
		_ = prev.Close()
	}

	startCtx, cancel := context.WithTimeout(a.ctx, agentStartTimeout)
	defer cancel()

	session, err := client.Agent().StartSession(startCtx, &syfthub.AgentSessionRequest{
		Prompt:       prompt,
		Endpoint:     endpointPath,
		Capabilities: []string{syfthub.AttachmentCapability},
	})
	if err != nil {
		return "", fmt.Errorf("failed to start agent session: %w", err)
	}

	a.agentMu.Lock()
	a.agentSession = session
	a.agentAttachments = make(map[string]*agentAttachment)
	a.agentMu.Unlock()

	// The wire's session.created event has already been consumed by StartSession's
	// handshake; emit session.started so the frontend sees one event per lifecycle stage.
	runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
		Type:      "session.started",
		SessionID: session.SessionID,
	})

	go a.drainAgentSession(session)

	return session.SessionID, nil
}

// drainAgentSession reads typed events from the hub session client and relays
// them on the "agent:event" Wails channel. Exits when the session's Events()
// channel closes (terminal event received or WebSocket closed).
func (a *App) drainAgentSession(sc *syfthub.AgentSessionClient) {
	sessionID := sc.SessionID
	sawTerminal := false

	for ev := range sc.Events() {
		eventType := ev.EventType()

		// Cache inbound attachments before forwarding. Inline bytes are
		// decoded + verified here once so save/preview is a buffer read;
		// object-store entries hold the metadata for lazy DownloadAttachment.
		if att, ok := ev.(*syfthub.AttachmentEvent); ok {
			if err := a.cacheAgentAttachment(sessionID, att); err != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("attachment %s cache failed: %v", att.FileID, err))
			}
		}

		// Marshal-then-unmarshal converts the typed event to the {field: value}
		// map shape the frontend's switch on event.data already expects. The
		// SDK structs carry the correct json tags (e.g. ThinkingEvent.Content
		// → "content"), so this is a faithful conversion.
		var data map[string]any
		if raw, err := json.Marshal(ev); err == nil {
			_ = json.Unmarshal(raw, &data)
		}

		// Rewrite terminal events to session.cancelled when the user explicitly
		// stopped. Done inline so the frontend only ever sees one terminal
		// event per session.
		switch eventType {
		case "session.completed", "session.failed":
			sawTerminal = true
			if a.consumeAgentCancelled(sessionID) {
				eventType = "session.cancelled"
			}
		}

		runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
			Type:      eventType,
			SessionID: sessionID,
			Data:      data,
		})
	}

	// readLoop closes Events() before Errors(); the SDK pushes at most one read
	// error then returns. Drain it non-blocking so we can label an unclean close.
	var readErr error
	select {
	case e, ok := <-sc.Errors():
		if ok {
			readErr = e
		}
	default:
	}

	// Guarantee a terminal event so the frontend always exits "running".
	if !sawTerminal {
		terminal := "session.completed"
		var data map[string]any
		if a.consumeAgentCancelled(sessionID) {
			terminal = "session.cancelled"
		} else if readErr != nil {
			terminal = "session.failed"
			data = map[string]any{"error": readErr.Error()}
		}
		runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
			Type:      terminal,
			SessionID: sessionID,
			Data:      data,
		})
	}

	// Cleanup, guarded so a newer session that started in parallel isn't clobbered.
	a.agentMu.Lock()
	if a.agentSession == sc {
		a.agentSession = nil
		a.agentAttachments = nil
	}
	if a.agentCancelledID == sessionID {
		a.agentCancelledID = ""
	}
	a.agentMu.Unlock()
}

// SendAgentMessage sends a user-follow-up message to the active agent session
// over the existing WebSocket.
func (a *App) SendAgentMessage(content string) error {
	a.agentMu.Lock()
	sc := a.agentSession
	a.agentMu.Unlock()
	if sc == nil {
		return fmt.Errorf("no active agent session")
	}

	ctx, cancel := context.WithTimeout(a.ctx, 10*time.Second)
	defer cancel()
	return sc.SendMessage(ctx, content)
}

// StopAgentSession cancels the active agent session. The session ID is
// recorded so the drain goroutine rewrites the trailing terminal event
// into session.cancelled.
func (a *App) StopAgentSession() error {
	a.agentMu.Lock()
	sc := a.agentSession
	a.agentSession = nil
	a.agentAttachments = nil
	if sc != nil {
		a.agentCancelledID = sc.SessionID
	}
	a.agentMu.Unlock()

	if sc == nil {
		return nil
	}

	// Send user.cancel best-effort so the host stops promptly, then Close to
	// unblock the drain goroutine. Close() is graceful and synchronous.
	cancelCtx, cancel := context.WithTimeout(a.ctx, 2*time.Second)
	defer cancel()
	_ = sc.Cancel(cancelCtx)
	return sc.Close()
}

// consumeAgentCancelled returns true and clears the marker if sessionID matches
// the session the user explicitly stopped. The drain goroutine uses this to
// decide whether a session.failed/session.completed event should be rewritten
// to session.cancelled.
func (a *App) consumeAgentCancelled(sessionID string) bool {
	a.agentMu.Lock()
	defer a.agentMu.Unlock()
	if a.agentCancelledID != "" && a.agentCancelledID == sessionID {
		a.agentCancelledID = ""
		return true
	}
	return false
}
