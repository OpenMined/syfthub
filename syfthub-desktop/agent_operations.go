// Package main: chat agent session bindings.
//
// Every agent session is a direct peer-to-peer connection: the desktop's
// syfthubapi AgentDialer publishes encrypted messages to the host's NATS space
// subject and receives the host's encrypted event stream on a private peer
// channel — there is no aggregator in the path. This file relays the
// AgentClientSession's typed events onto the Wails "agent:event" channel and
// tracks user-initiated cancellation.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// AgentStreamEvent is emitted on "agent:event" for every event from an agent session.
type AgentStreamEvent struct {
	Type      string         `json:"type"`
	SessionID string         `json:"sessionId"`
	Data      map[string]any `json:"data,omitempty"`
}

// agentStartTimeout caps token acquisition plus the session-start dial.
const agentStartTimeout = 30 * time.Second

// StartAgentSession opens a direct peer-to-peer agent session for the given
// endpoint path ("owner/slug"): it resolves the satellite token, peer channel,
// and the host's encryption key from the hub, then dials the host over NATS
// and returns the session ID. Streaming events flow asynchronously through the
// "agent:event" Wails channel.
//
// Any previous session is cancelled before the new one starts so the frontend
// only ever has one live transcript.
func (a *App) StartAgentSession(endpointPath string, prompt string) (string, error) {
	return a.startAgentSessionInternal(endpointPath, prompt, nil, "")
}

// StartAgentSessionWithCredential is the payment-retry variant. After a prior
// session emitted agent.payment_required and the consumer signed an mppx
// credential via WalletPayChallenge, the frontend re-opens the session with
// that wire-format credential attached so the host's mppx gate can verify and
// the per-turn policy short-circuits to allow.
//
// credentialWire is the string produced by mppx.SerializeCredential
// (typically prefixed with "Payment "); empty falls back to a normal start.
func (a *App) StartAgentSessionWithCredential(endpointPath string, prompt string, credentialWire string) (string, error) {
	return a.startAgentSessionInternal(endpointPath, prompt, nil, credentialWire)
}

// StartAgentSessionWithHistory is the continuation variant: the agent receives
// `history` as the prior conversation context before `prompt`. This is how the
// chat UI resumes a thread from an approved sent-review — the held turn (user
// message + agent's real reply) becomes the conversation history of the new
// live session so the agent sees the full thread, not just the new prompt.
//
// historyJSON is a JSON-encoded []agenttypes.Message; we keep it as a string
// at the Wails surface because the generated TypeScript bindings handle JSON
// blobs more predictably than nested struct slices.
func (a *App) StartAgentSessionWithHistory(endpointPath string, prompt string, historyJSON string) (string, error) {
	var history []agenttypes.Message
	if historyJSON != "" {
		if err := json.Unmarshal([]byte(historyJSON), &history); err != nil {
			return "", fmt.Errorf("invalid history payload: %w", err)
		}
	}
	// Validate role values defensively — the host's policy engine sees these
	// verbatim, and an unknown role could behave unpredictably. We trust the
	// frontend but draw a single line of defense.
	for i, m := range history {
		switch m.Role {
		case "user", "assistant", "system":
		default:
			return "", fmt.Errorf("history[%d]: unsupported role %q", i, m.Role)
		}
	}
	return a.startAgentSessionInternal(endpointPath, prompt, history, "")
}

// startAgentSessionInternal does the actual dial work. history may be nil for
// a fresh chat (the original StartAgentSession path) or carry prior turns for
// a continuation. credentialWire is the wire-format mppx credential the
// caller signed (empty for a fresh, unpaid session). The dial path is
// identical regardless — DialParams.Messages carries the history and
// DialParams.PaymentCredential carries the credential to the host's
// AgentSessionStartPayload.
func (a *App) startAgentSessionInternal(endpointPath, prompt string, history []agenttypes.Message, credentialWire string) (string, error) {
	a.mu.RLock()
	client := a.syftClient
	core := a.core
	a.mu.RUnlock()
	if client == nil {
		return "", fmt.Errorf("hub client not initialized — log in to start an agent session")
	}
	if core == nil {
		return "", fmt.Errorf("start the app before opening an agent session")
	}
	dialer := core.AgentDialer()
	if dialer == nil {
		return "", fmt.Errorf("agent sessions require NATS tunnel mode")
	}

	parts := strings.SplitN(endpointPath, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", fmt.Errorf("endpoint must be in 'owner/slug' format, got: %s", endpointPath)
	}
	owner, slug := parts[0], parts[1]

	// Swap out any previous session under the agent mutex. Marking the previous
	// session as cancelled BEFORE closing it ensures the drain goroutine rewrites
	// its terminal event to session.cancelled rather than session.failed. The
	// inbound attachment cache is dropped — fileIDs are scoped per-session.
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

	// Resolve the hub-issued credentials the dial needs: the satellite token
	// proves the caller's identity, the peer channel is the reply inbox, and
	// the host's encryption key seals the request. The three lookups are
	// independent, so fan them out concurrently.
	var (
		satResp  *syfthub.SatelliteTokenResponse
		peerResp *syfthub.PeerTokenResponse
		hostKey  string
	)
	g, gctx := errgroup.WithContext(startCtx)
	g.Go(func() (err error) { satResp, err = client.Auth.GetSatelliteToken(gctx, owner); return })
	g.Go(func() (err error) { peerResp, err = client.Auth.GetPeerToken(gctx, []string{owner}); return })
	g.Go(func() (err error) { hostKey, err = client.Auth.GetEncryptionPublicKey(gctx, owner); return })
	if err := g.Wait(); err != nil {
		return "", fmt.Errorf("failed to resolve session credentials: %w", err)
	}

	session, err := dialer.Dial(startCtx, transport.DialParams{
		TargetUsername:    owner,
		HostPublicKeyB64:  hostKey,
		PeerChannel:       peerResp.PeerChannel,
		SatelliteToken:    satResp.TargetToken,
		Prompt:            prompt,
		EndpointSlug:      slug,
		Messages:          history,
		Capabilities:      []string{agenttypes.AttachmentCapability},
		PaymentCredential: credentialWire,
	})
	if err != nil {
		return "", fmt.Errorf("failed to start agent session: %w", err)
	}

	a.agentMu.Lock()
	a.agentSession = session
	a.agentAttachments = make(map[string]*agentAttachment)
	a.agentMu.Unlock()

	// Emit session.started so the frontend sees one event per lifecycle stage.
	runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
		Type:      "session.started",
		SessionID: session.SessionID,
	})

	go a.drainAgentSession(session)

	return session.SessionID, nil
}

// drainAgentSession reads typed events from the agent session client and
// relays them on the "agent:event" Wails channel. Exits when the session's
// Events() channel closes (terminal event received or connection closed).
func (a *App) drainAgentSession(sc *transport.AgentClientSession) {
	sessionID := sc.SessionID
	sawTerminal := false

	for ev := range sc.Events() {
		eventType := ev.EventType()

		// Cache inbound attachments before forwarding. Inline bytes are
		// decoded + verified once here so save/preview is a buffer read.
		if att, ok := ev.(*agenttypes.AttachmentEvent); ok {
			if err := a.cacheAgentAttachment(sessionID, att); err != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("attachment %s cache failed: %v", att.FileID, err))
			}
		}

		// Marshal-then-unmarshal converts the typed event to the {field: value}
		// map shape the frontend's switch on event.data expects.
		var data map[string]any
		if raw, err := json.Marshal(ev); err == nil {
			_ = json.Unmarshal(raw, &data)
		}

		// Rewrite terminal events to session.cancelled when the user explicitly
		// stopped, so the frontend only ever sees one terminal event per session.
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

	// run() closes Events() before Errors(); drain a trailing read error
	// non-blocking so an unclean close can be labelled.
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

// SendAgentMessage sends a user follow-up message to the active agent session.
func (a *App) SendAgentMessage(content string) error {
	a.agentMu.Lock()
	sc := a.agentSession
	a.agentMu.Unlock()
	if sc == nil {
		return fmt.Errorf("no active agent session")
	}
	return sc.SendMessage(content)
}

// SendAgentMessageWithCredential sends a user follow-up carrying a per-turn
// mppx payment credential. Use this after WalletPayChallenge produces a
// credential in response to a mid-session agent.payment_required event:
// the chat workflow resends the SAME content with the credential attached
// so the producer's per-turn policy can verify it and allow the turn.
//
// Returns "no active session" if the session has already terminated — the
// caller should fall back to StartAgentSessionWithCredential in that case.
func (a *App) SendAgentMessageWithCredential(content, credentialWire string) error {
	a.agentMu.Lock()
	sc := a.agentSession
	a.agentMu.Unlock()
	if sc == nil {
		return fmt.Errorf("no active agent session")
	}
	return sc.SendMessageWithCredential(content, credentialWire)
}

// StopAgentSession cancels the active agent session. The session ID is
// recorded so the drain goroutine rewrites the trailing terminal event into
// session.cancelled.
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

	// Ask the host to stop, then close locally to unblock the drain goroutine.
	_ = sc.Cancel()
	return sc.Close()
}

// consumeAgentCancelled returns true and clears the marker if sessionID matches
// the session the user explicitly stopped. The drain goroutine uses this to
// decide whether a terminal event should be rewritten to session.cancelled.
func (a *App) consumeAgentCancelled(sessionID string) bool {
	a.agentMu.Lock()
	defer a.agentMu.Unlock()
	if a.agentCancelledID != "" && a.agentCancelledID == sessionID {
		a.agentCancelledID = ""
		return true
	}
	return false
}
