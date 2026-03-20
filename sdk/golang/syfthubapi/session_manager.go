package syfthubapi

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"
)

// DefaultMaxSessions is the default maximum number of concurrent agent sessions.
const DefaultMaxSessions = 100

// AgentSessionManager tracks active agent sessions on the Space side.
// It maps session IDs to AgentSession instances, handles session creation,
// message routing, and cleanup.
type AgentSessionManager struct {
	sessions    map[string]*AgentSession
	registry    *EndpointRegistry
	logger      *slog.Logger
	maxSessions int
	mu          sync.RWMutex

	// reaperCancel stops the reaper goroutine when called.
	reaperCancel context.CancelFunc
}

// NewAgentSessionManager creates a new session manager with the given maximum
// session limit. Pass 0 to use DefaultMaxSessions.
func NewAgentSessionManager(registry *EndpointRegistry, logger *slog.Logger, maxSessions int) *AgentSessionManager {
	if maxSessions <= 0 {
		maxSessions = DefaultMaxSessions
	}
	return &AgentSessionManager{
		sessions:    make(map[string]*AgentSession),
		registry:    registry,
		logger:      logger,
		maxSessions: maxSessions,
	}
}

// AgentSessionStartPayload is the decrypted payload of an agent_session_start message.
type AgentSessionStartPayload struct {
	SessionID    string      `json:"session_id"`
	Prompt       string      `json:"prompt"`
	EndpointSlug string      `json:"endpoint_slug"`
	Messages     []Message   `json:"messages,omitempty"`
	Config       AgentConfig `json:"config"`
}

// AgentUserMessagePayload is the decrypted payload of an agent_user_message.
type AgentUserMessagePayload struct {
	SessionID string      `json:"session_id"`
	Message   UserMessage `json:"message"`
}

// AgentSessionCancelPayload is the decrypted payload of an agent_session_cancel.
type AgentSessionCancelPayload struct {
	SessionID string `json:"session_id"`
}

// StartSession creates a new agent session and spawns the handler goroutine.
// Returns the session for the caller to set up NATS relay.
func (m *AgentSessionManager) StartSession(
	payload AgentSessionStartPayload,
	user *UserContext,
) (*AgentSession, error) {
	// Look up the agent endpoint
	ep, ok := m.registry.Get(payload.EndpointSlug)
	if !ok {
		return nil, fmt.Errorf("endpoint not found: %s", payload.EndpointSlug)
	}

	if ep.Type != EndpointTypeAgent {
		return nil, fmt.Errorf("endpoint %s is not an agent endpoint", payload.EndpointSlug)
	}

	// Enforce policies before starting session.
	reqCtx := &RequestContext{
		User:         user,
		EndpointSlug: payload.EndpointSlug,
		EndpointType: EndpointTypeAgent,
	}
	policyResult, err := ep.CheckPolicies(context.Background(), reqCtx)
	if err != nil {
		return nil, fmt.Errorf("policy check failed: %w", err)
	}
	if policyResult != nil && !policyResult.Allowed {
		m.logger.Warn("[AGENT] Session denied by policy",
			"endpoint", payload.EndpointSlug,
			"user", user.Username,
			"policy_name", policyResult.PolicyName,
			"reason", policyResult.Reason,
		)
		return nil, fmt.Errorf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason)
	}

	handler, err := ep.GetAgentHandler()
	if err != nil {
		return nil, err
	}

	// Create session — long-lived WebSocket sessions use Background context
	// (cancelled explicitly via CancelSession or session.Cancel).
	session := NewAgentSession(
		context.Background(),
		payload.SessionID,
		payload.Prompt,
		payload.Messages,
		payload.Config,
		user,
		payload.EndpointSlug,
	)

	// Register session (enforce max sessions limit)
	m.mu.Lock()
	if len(m.sessions) >= m.maxSessions {
		m.mu.Unlock()
		session.Cancel()
		return nil, fmt.Errorf("max sessions limit reached (%d)", m.maxSessions)
	}
	m.sessions[session.ID] = session
	m.mu.Unlock()

	m.logger.Info("[AGENT] Session started",
		"session_id", session.ID,
		"endpoint", payload.EndpointSlug,
		"user", user.Username,
	)

	// Set cleanup callback for session map removal and logging.
	session.OnDone = func() {
		m.mu.Lock()
		delete(m.sessions, session.ID)
		m.mu.Unlock()

		m.logger.Info("[AGENT] Session ended", "session_id", session.ID)
	}

	// Spawn handler goroutine via the canonical lifecycle method.
	session.RunHandler(handler)

	return session, nil
}

// RouteMessage routes an incoming user message to the correct session's recvCh.
func (m *AgentSessionManager) RouteMessage(payload AgentUserMessagePayload) error {
	m.mu.RLock()
	session, ok := m.sessions[payload.SessionID]
	m.mu.RUnlock()

	if !ok {
		return fmt.Errorf("session not found: %s", payload.SessionID)
	}

	if !session.DeliverMessage(payload.Message) {
		m.logger.Warn("[AGENT] Session receive channel full, dropping message",
			"session_id", payload.SessionID,
		)
	}

	return nil
}

// CancelSession cancels a session's context, causing the handler goroutine to return.
func (m *AgentSessionManager) CancelSession(sessionID string) error {
	m.mu.RLock()
	session, ok := m.sessions[sessionID]
	m.mu.RUnlock()

	if !ok {
		return fmt.Errorf("session not found: %s", sessionID)
	}

	m.logger.Info("[AGENT] Cancelling session", "session_id", sessionID)
	session.Cancel()
	return nil
}

// GetSession returns a session by ID, or nil if not found.
func (m *AgentSessionManager) GetSession(sessionID string) *AgentSession {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.sessions[sessionID]
}

// StartReaper launches a background goroutine that periodically scans for stale
// or orphaned sessions (done channel closed, or context cancelled) and removes
// them from the sessions map. The reaper stops when ctx is cancelled.
// It is safe to call StartReaper at most once; subsequent calls are no-ops.
func (m *AgentSessionManager) StartReaper(ctx context.Context, interval time.Duration) {
	m.mu.Lock()
	if m.reaperCancel != nil {
		m.mu.Unlock()
		return // already running
	}
	reaperCtx, cancel := context.WithCancel(ctx)
	m.reaperCancel = cancel
	m.mu.Unlock()

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		m.logger.Info("[AGENT] Session reaper started", "interval", interval)
		for {
			select {
			case <-reaperCtx.Done():
				m.logger.Info("[AGENT] Session reaper stopped")
				return
			case <-ticker.C:
				m.reapStaleSessions()
			}
		}
	}()
}

// StopReaper stops the reaper goroutine if running.
func (m *AgentSessionManager) StopReaper() {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.reaperCancel != nil {
		m.reaperCancel()
		m.reaperCancel = nil
	}
}

// CancelAllSessions cancels every active session. Used during graceful shutdown
// to ensure agent handler goroutines terminate and subprocesses are cleaned up.
func (m *AgentSessionManager) CancelAllSessions() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for id, session := range m.sessions {
		session.Cancel()
		delete(m.sessions, id)
	}
	if len(m.sessions) == 0 {
		m.logger.Info("[AGENT] All sessions cancelled for shutdown")
	}
}

// reapStaleSessions scans all sessions and removes those whose Done channel is
// closed or whose context has been cancelled. For cancelled-but-not-done sessions,
// it also calls Cancel() to nudge the handler goroutine.
func (m *AgentSessionManager) reapStaleSessions() {
	m.mu.Lock()
	defer m.mu.Unlock()

	reaped := 0
	for id, session := range m.sessions {
		// Check if done channel is closed (handler already returned).
		select {
		case <-session.Done():
			delete(m.sessions, id)
			reaped++
			continue
		default:
		}

		// Check if context is cancelled (session should be winding down).
		if session.Context().Err() != nil {
			session.Cancel()
			delete(m.sessions, id)
			reaped++
		}
	}

	if reaped > 0 {
		m.logger.Info("[AGENT] Reaped stale sessions",
			"reaped", reaped,
			"remaining", len(m.sessions),
		)
	}
}
