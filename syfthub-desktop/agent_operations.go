package main

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

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

// agentSessionLog bundles the parameters for emitAgentSessionLog.
// The session-identity fields (slug through startTime) are invariant across
// a session's lifetime; outcome fields vary per call.
type agentSessionLog struct {
	slug            string
	sessionID       string
	prompt          string
	user            *syfthubapi.UserContext
	startTime       time.Time
	responseContent string
	failed          bool
	failError       string
	policyResult    *syfthubapi.PolicyResultOutput
	// transcript is the full conversational history captured by the SDK
	// (user + assistant messages, interleaved). Empty for pre-session
	// failures, in which case emitAgentSessionLog falls back to a single
	// user message constructed from prompt.
	transcript []syfthubapi.Message
}

// requireAPI returns the core API, or an error if the app is not running.
func (a *App) requireAPI() (*syfthubapi.SyftAPI, error) {
	core, err := a.requireCore()
	if err != nil {
		return nil, fmt.Errorf("app not running: %w", err)
	}
	api := core.API()
	if api == nil {
		return nil, fmt.Errorf("API not initialized")
	}
	return api, nil
}

// requireAgentSessionManager returns the AgentSessionManager, or an error if
// the app or API is not ready.
func (a *App) requireAgentSessionManager() (*syfthubapi.AgentSessionManager, error) {
	api, err := a.requireAPI()
	if err != nil {
		return nil, err
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return nil, fmt.Errorf("agent session manager not initialized")
	}
	return sm, nil
}

// checkAgentPolicy runs policy evaluation for an agent endpoint before starting
// a session. Returns (nil, nil) if no policies are configured.
// Accepts the API directly so the caller can reuse an existing reference.
func (a *App) checkAgentPolicy(api *syfthubapi.SyftAPI, slug string, user *syfthubapi.UserContext) (*syfthubapi.PolicyResultOutput, error) {
	registry := api.Registry()
	if registry == nil {
		return nil, fmt.Errorf("registry not initialized")
	}

	endpoint, ok := registry.Get(slug)
	if !ok {
		return nil, fmt.Errorf("endpoint not found: %s", slug)
	}

	reqCtx := &syfthubapi.RequestContext{
		User:         user,
		EndpointSlug: slug,
		EndpointType: syfthubapi.EndpointTypeAgent,
	}
	return endpoint.CheckPolicies(context.Background(), reqCtx)
}

// StartAgentSession starts an interactive agent session through the shared
// AgentSessionManager. All session logic (endpoint lookup, policy enforcement,
// handler invocation) is handled by the manager — the same code path used by
// remote NATS sessions. This method only adds the Wails event transport adapter.
func (a *App) StartAgentSession(slug string, prompt string) (string, error) {
	api, err := a.requireAPI()
	if err != nil {
		return "", err
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return "", fmt.Errorf("agent session manager not initialized")
	}

	// Cancel any existing session before starting a new one. Mark it as
	// user-cancelled so its trailing "signal: killed" failure is suppressed.
	a.agentMu.Lock()
	if a.agentSessionID != "" {
		a.agentCancelledID = a.agentSessionID
		_ = sm.CancelSession(a.agentSessionID)
		a.agentSessionID = ""
	}
	a.agentMu.Unlock()

	sessionID := uuid.New().String()
	userCtx := a.currentUserContext()

	logInfo := agentSessionLog{
		slug:      slug,
		sessionID: sessionID,
		prompt:    prompt,
		user:      userCtx,
		startTime: time.Now(),
	}

	// failLog emits a RequestLog entry for a denied/failed session start and
	// returns the formatted error. policyResult may be nil when the failure
	// is not policy-related.
	failLog := func(msg string, policyResult *syfthubapi.PolicyResultOutput) {
		l := logInfo
		l.failed = true
		l.failError = msg
		l.policyResult = policyResult
		a.emitAgentSessionLog(l)
	}

	// Check policies before starting the session. The session manager also
	// checks policies internally, but by checking here first we can emit a
	// structured log entry with the full policy info (name, reason, etc.)
	// that matches the log format used by model/data_source endpoints.
	policyResult, err := a.checkAgentPolicy(api, slug, userCtx)
	if err != nil {
		failLog(fmt.Sprintf("policy check failed: %v", err), nil)
		return "", fmt.Errorf("failed to start agent session: %w", err)
	}
	if policyResult != nil && !policyResult.Allowed {
		errMsg := fmt.Sprintf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason)
		failLog(errMsg, policyResult)
		return "", fmt.Errorf("failed to start agent session: %s", errMsg)
	}

	// Endpoint opt-in via YAML accepts_attachments is the real gate.
	session, err := sm.StartSession(syfthubapi.AgentSessionStartPayload{
		SessionID:    sessionID,
		Prompt:       prompt,
		EndpointSlug: slug,
		Capabilities: []string{syfthubapi.AttachmentCapability},
	}, userCtx)
	if err != nil {
		failLog(err.Error(), nil)
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
		var messageBuf strings.Builder
		sessionFailed := false
		var failError string

		for event := range session.SendCh() {
			var data map[string]any
			if event.Data != nil {
				if err := json.Unmarshal(event.Data, &data); err != nil {
					data = map[string]any{"raw": string(event.Data)}
				}
			}

			eventType := event.EventType
			switch event.EventType {
			case syfthubapi.EventTypeSessionCompleted:
				sawTerminal = true
			case syfthubapi.EventTypeSessionFailed:
				sawTerminal = true
				// "signal: killed" from a user-initiated cancel is not an error;
				// rewrite the relayed event and skip failure tracking.
				if a.consumeAgentCancelled(session.ID) {
					eventType = syfthubapi.EventTypeSessionCancelled
				} else {
					sessionFailed = true
					if e, ok := data["error"].(string); ok {
						failError = e
					}
				}
			case syfthubapi.EventTypeAgentMessage:
				if content, ok := data["content"].(string); ok {
					if messageBuf.Len() > 0 {
						messageBuf.WriteString("\n")
					}
					messageBuf.WriteString(content)
				}
			case syfthubapi.EventTypeAgentAttachment:
				if err := materializeAgentInlineAttachment(session.AttachmentDir, data); err != nil {
					runtime.LogWarning(a.ctx, fmt.Sprintf("agent.attachment materialize failed: %v", err))
				}
			}

			runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
				Type:      eventType,
				SessionID: session.ID,
				Data:      data,
			})
		}

		// Ensure the frontend always receives a terminal event to exit "Running"
		// state. If the user cancelled but no failed event arrived (e.g. the
		// handler returned nil after cleanup), prefer session.cancelled over
		// session.completed so the UI still reflects the explicit stop.
		if !sawTerminal {
			terminalType := syfthubapi.EventTypeSessionCompleted
			if a.consumeAgentCancelled(session.ID) {
				terminalType = syfthubapi.EventTypeSessionCancelled
			}
			runtime.EventsEmit(a.ctx, "agent:event", AgentStreamEvent{
				Type:      terminalType,
				SessionID: session.ID,
			})
		}

		a.agentMu.Lock()
		if a.agentSessionID == session.ID {
			a.agentSessionID = ""
		}
		// Clear any lingering cancellation marker so it cannot leak across
		// sessions (defense in depth — consumeAgentCancelled normally clears it).
		if a.agentCancelledID == session.ID {
			a.agentCancelledID = ""
		}
		a.agentMu.Unlock()

		// Determine functional success: if the agent produced message output,
		// the session succeeded from the user's perspective even if the handler
		// returned an error during subprocess cleanup (e.g., "signal: killed"
		// from normal process termination after the agent finished its work).
		logFailed := sessionFailed && messageBuf.Len() == 0

		// Emit a RequestLog so agent sessions appear in the Logs tab alongside
		// model/data_source request logs. Pass the policy result so that
		// allowed-but-evaluated policies are recorded in the log, and the
		// SDK-captured transcript so the log carries the full conversation
		// (initial prompt + all user follow-ups + all assistant messages)
		// rather than just the first user input.
		l := logInfo
		l.responseContent = messageBuf.String()
		l.failed = logFailed
		l.failError = failError
		l.policyResult = policyResult
		l.transcript = session.Transcript()
		a.emitAgentSessionLog(l)
	}()

	return session.ID, nil
}

// emitAgentSessionLog builds a RequestLog for a completed (or denied) interactive
// agent session and writes it through the core log pipeline (FileLogStore +
// frontend notification). This gives agent endpoints the same log visibility as
// model/data_source endpoints.
func (a *App) emitAgentSessionLog(l agentSessionLog) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	if core == nil {
		return
	}

	processedAt := time.Now()

	// Prefer the SDK-captured transcript (full user+assistant history). Fall
	// back to a single-prompt slice for pre-session failures (policy denial,
	// session start error) where no AgentSession ever existed.
	messages := l.transcript
	if len(messages) == 0 {
		messages = []syfthubapi.Message{{Role: "user", Content: l.prompt}}
	}

	log := &syfthubapi.RequestLog{
		ID:            syfthubapi.NewRequestLogID(),
		Timestamp:     l.startTime,
		CorrelationID: l.sessionID,
		EndpointSlug:  l.slug,
		EndpointType:  string(syfthubapi.EndpointTypeAgent),
		User: &syfthubapi.LogUserInfo{
			ID:       l.user.Sub,
			Username: l.user.Username,
			Email:    l.user.Email,
			Role:     l.user.Role,
		},
		Request: &syfthubapi.LogRequest{
			Type:     string(syfthubapi.EndpointTypeAgent),
			Messages: messages,
			RawSize:  len(l.prompt),
		},
		Response: &syfthubapi.LogResponse{},
		Timing: &syfthubapi.LogTiming{
			ReceivedAt:  l.startTime,
			ProcessedAt: processedAt,
			DurationMs:  processedAt.Sub(l.startTime).Milliseconds(),
		},
	}

	if l.failed {
		log.Response.Success = false
		log.Response.Error = l.failError
	} else {
		log.Response.Success = true
		content, truncated := syfthubapi.TruncateForLog(l.responseContent)
		log.Response.Content = content
		log.Response.ContentTruncated = truncated
	}

	// Include structured policy info when available, matching the format
	// used by model/data_source logs from BuildRequestLog().
	if l.policyResult != nil {
		log.Policy = &syfthubapi.LogPolicy{
			Evaluated:  true,
			Allowed:    l.policyResult.Allowed,
			PolicyName: l.policyResult.PolicyName,
			Reason:     l.policyResult.Reason,
			Pending:    l.policyResult.Pending,
			Metadata:   l.policyResult.Metadata,
		}
	}

	core.WriteLog(context.Background(), log)
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
// AgentSessionManager. The session ID is recorded in agentCancelledID so the
// event drain goroutine can rewrite the trailing "signal: killed" failure
// into a session.cancelled event — a user-initiated stop is not an error.
func (a *App) StopAgentSession() error {
	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentSessionID = ""
	if sessionID != "" {
		a.agentCancelledID = sessionID
	}
	a.agentMu.Unlock()

	if sessionID == "" {
		return nil
	}

	sm, err := a.requireAgentSessionManager()
	if err != nil {
		return nil // App/API not ready; session ID already cleared above.
	}

	return sm.CancelSession(sessionID)
}

// consumeAgentCancelled returns true and clears the marker if sessionID
// matches the session the user explicitly stopped. The drain goroutine uses
// this to decide whether a session.failed event should be rewritten to
// session.cancelled.
func (a *App) consumeAgentCancelled(sessionID string) bool {
	a.agentMu.Lock()
	defer a.agentMu.Unlock()
	if a.agentCancelledID != "" && a.agentCancelledID == sessionID {
		a.agentCancelledID = ""
		return true
	}
	return false
}
