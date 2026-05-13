package syfthubapi

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"slices"
	"sync"
	"time"
)

// DefaultMaxSessions is the default maximum number of concurrent agent sessions.
const DefaultMaxSessions = 100

// SessionStatus represents the state of an agent session in external registries.
type SessionStatus string

const SessionStatusRunning SessionStatus = "running"

// SessionRegistrar is notified of session lifecycle events so external registries
// (e.g., JetStream KV) can track active sessions. All methods must be safe for
// concurrent use. Errors are logged but do not block session operations.
type SessionRegistrar interface {
	RegisterSession(meta SessionMeta) error
	DeregisterSession(sessionID string) error
}

// SessionMeta contains metadata about an active agent session.
type SessionMeta struct {
	SessionID    string        `json:"session_id"`
	EndpointSlug string        `json:"endpoint_slug"`
	Username     string        `json:"username"`
	Status       SessionStatus `json:"status"`
	StartedAt    time.Time     `json:"started_at"`
}

// AgentSessionManager tracks active agent sessions on the Space side.
// It maps session IDs to AgentSession instances, handles session creation,
// message routing, and cleanup.
type AgentSessionManager struct {
	sessions    map[string]*AgentSession
	registry    *EndpointRegistry
	logger      *slog.Logger
	maxSessions int
	registrar   SessionRegistrar
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

// SetRegistrar sets an optional registrar that is notified of session lifecycle events.
func (m *AgentSessionManager) SetRegistrar(r SessionRegistrar) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.registrar = r
}

// deregisterSession notifies the external registrar that a session has ended.
// Safe to call when registrar is nil or the session was already deregistered.
func (m *AgentSessionManager) deregisterSession(sessionID string) {
	if m.registrar != nil {
		if err := m.registrar.DeregisterSession(sessionID); err != nil {
			m.logger.Debug("[AGENT] Failed to deregister session from external registry",
				"session_id", sessionID, "error", err)
		}
	}
}

// AgentSessionStartPayload is the decrypted payload of an agent_session_start message.
type AgentSessionStartPayload struct {
	SessionID    string      `json:"session_id"`
	Prompt       string      `json:"prompt"`
	EndpointSlug string      `json:"endpoint_slug"`
	Messages     []Message   `json:"messages,omitempty"`
	Config       AgentConfig `json:"config"`

	// PaymentCredential is the on-chain payment proof (e.g., Tempo/PathUSD tx hash
	// or signed challenge response) supplied by the caller to satisfy a
	// TransactionPolicy payment challenge for the agent session intent.
	PaymentCredential string `json:"payment_credential,omitempty"`

	// Capabilities lists optional protocol extensions the caller supports.
	// See docs/architecture/attachments.md for the "attachments" capability.
	// Hosts MUST NOT emit attachment events unless this list contains
	// AttachmentCapability AND the endpoint has accepts_attachments=true.
	Capabilities []string `json:"capabilities,omitempty"`

	// SessionAttachmentKey is the base64-encoded 32-byte AES key the
	// aggregator generated for this session. HOST + aggregator both wrap
	// per-file content keys with KEKs derived from this key (HKDF info =
	// "syfthub-attachment-v1" || file_id). Only meaningful when the
	// "attachments" capability is present.
	SessionAttachmentKey string `json:"session_attachment_key,omitempty"`
}

// HasCapability returns true if the payload declared the named capability.
func (p *AgentSessionStartPayload) HasCapability(cap string) bool {
	return slices.Contains(p.Capabilities, cap)
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
	ep, ok := m.registry.Get(payload.EndpointSlug)
	if !ok {
		return nil, fmt.Errorf("endpoint not found: %s", payload.EndpointSlug)
	}

	if ep.Type != EndpointTypeAgent {
		return nil, fmt.Errorf("endpoint %s is not an agent endpoint", payload.EndpointSlug)
	}

	// Enforce policies before starting session.
	reqCtx := &RequestContext{
		User:              user,
		EndpointSlug:      payload.EndpointSlug,
		EndpointType:      EndpointTypeAgent,
		PaymentCredential: payload.PaymentCredential,
	}
	policyResult, err := ep.CheckPolicies(context.Background(), reqCtx)
	if err != nil {
		return nil, fmt.Errorf("policy check failed: %w", err)
	}
	if policyResult != nil {
		// A "pending" result with a payment_challenge means a transaction-style
		// policy is asking the caller to obtain a payment credential and retry.
		// Surface this as a typed error so the NATS bridge can emit a
		// PAYMENT_REQUIRED tunnel response with the challenge details.
		if policyResult.Pending {
			if challenge, ok := PaymentChallengeFromMetadata(policyResult.Metadata); ok {
				m.logger.Info("[AGENT] Session pending payment",
					"endpoint", payload.EndpointSlug,
					"user", user.Username,
					"policy_name", policyResult.PolicyName,
				)
				return nil, &PaymentRequiredError{
					Challenge: challenge,
					Details:   CopyPaymentMetadata(policyResult.Metadata),
				}
			}
		}
		if !policyResult.Allowed {
			m.logger.Warn("[AGENT] Session denied by policy",
				"endpoint", payload.EndpointSlug,
				"user", user.Username,
				"policy_name", policyResult.PolicyName,
				"reason", policyResult.Reason,
			)
			return nil, fmt.Errorf("access denied by policy %q: %s", policyResult.PolicyName, policyResult.Reason)
		}
	}

	handler, err := ep.GetAgentHandler()
	if err != nil {
		return nil, err
	}

	// Provision a per-session tempdir for attachments when both peers have
	// opted in. The caller advertises support via Capabilities; the endpoint
	// owner explicitly opts in via AcceptsAttachments. Either side missing
	// disables attachments for this session (handler can check
	// session.AttachmentsEnabled()).
	var attachDir string
	if ep.AcceptsAttachments && payload.HasCapability(AttachmentCapability) {
		dir, derr := os.MkdirTemp("", "syft-att-"+payload.SessionID+"-")
		if derr != nil {
			return nil, fmt.Errorf("create attachment tempdir: %w", derr)
		}
		// 0700 enforced by MkdirTemp on Unix; double-check for portability.
		_ = os.Chmod(dir, 0o700)
		attachDir = dir
	}

	// Create session — long-lived WebSocket sessions use Background context
	// (cancelled explicitly via CancelSession or session.Cancel).
	session := NewAgentSession(context.Background(), AgentSessionParams{
		ID:            payload.SessionID,
		Prompt:        payload.Prompt,
		EndpointSlug:  payload.EndpointSlug,
		Messages:      payload.Messages,
		Config:        payload.Config,
		User:          user,
		Capabilities:  payload.Capabilities,
		AttachmentDir: attachDir,
	})

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

	// Notify external registrar (e.g., JetStream KV).
	if m.registrar != nil {
		if err := m.registrar.RegisterSession(SessionMeta{
			SessionID:    session.ID,
			EndpointSlug: payload.EndpointSlug,
			Username:     user.Username,
			Status:       SessionStatusRunning,
			StartedAt:    time.Now(),
		}); err != nil {
			m.logger.Warn("[AGENT] Failed to register session in external registry",
				"session_id", session.ID, "error", err)
		}
	}

	// Set cleanup callback for session map removal and logging.
	// Only deregister from the external registry if the session was still tracked
	// in the map — avoids double-deregister when CancelAllSessions or the reaper
	// has already cleaned it up.
	session.OnDone = func() {
		m.mu.Lock()
		_, stillTracked := m.sessions[session.ID]
		delete(m.sessions, session.ID)
		m.mu.Unlock()

		if stillTracked {
			m.deregisterSession(session.ID)
		}

		if session.AttachmentDir != "" {
			if err := os.RemoveAll(session.AttachmentDir); err != nil {
				m.logger.Warn("[AGENT] Failed to clean up attachment tempdir",
					"session_id", session.ID, "dir", session.AttachmentDir, "error", err)
			}
		}

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

// GetSession returns a session by ID. The boolean is false if the session
// is unknown. The two-return-value signature satisfies AgentSessionHandler.
func (m *AgentSessionManager) GetSession(sessionID string) (*AgentSession, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, ok := m.sessions[sessionID]
	return s, ok
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
		m.deregisterSession(id)
		delete(m.sessions, id)
	}
	m.logger.Info("[AGENT] All sessions cancelled for shutdown")
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
			m.deregisterSession(id)
			delete(m.sessions, id)
			reaped++
			continue
		default:
		}

		// Check if context is cancelled (session should be winding down).
		if session.Context().Err() != nil {
			session.Cancel()
			m.deregisterSession(id)
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
