// agent_dial.go implements the outbound side of a direct peer-to-peer agent
// session (tunnel protocol v2). AgentDialer opens sessions against a remote
// host by publishing to the host's NATS space subject and subscribing to a
// private reply channel; AgentClientSession is the live session handle.
//
// This is the client-side counterpart of the host-side agentNATSBridge in
// nats.go. Both ends are syfthubapi peers — there is no aggregator in the
// path. One AgentDialer, sharing the app's single NATSConn, may run many
// concurrent sessions.

package transport

import (
	"context"
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"slices"
	"sync"

	"github.com/google/uuid"
	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

const (
	spaceSubjectPrefix = "syfthub.spaces."
	peerSubjectPrefix  = "syfthub.peer."
)

// AgentDialer opens outbound P2P agent sessions over a shared NATS connection.
type AgentDialer struct {
	conn        *NATSConn
	identityKey *ecdh.PrivateKey
	identityPub string
	logger      *slog.Logger

	// transport is an optional reference to the same-process NATSTransport,
	// borrowed for its lazily-initialized JetStream Object Store handle.
	// Required for object_store-tier attachments on the client side; when
	// nil, attachment sends/receives larger than InlineMaxBytes fail.
	// Wire via WithAttachmentStore.
	transport *NATSTransport
}

// NewAgentDialer creates a dialer that signs sessions with the given X25519
// identity key and routes traffic over conn. The resulting dialer supports
// only inline-tier attachments. Call WithAttachmentStore to enable
// object_store-tier (large-file) attachment sends and receives.
func NewAgentDialer(conn *NATSConn, identityKey *ecdh.PrivateKey, logger *slog.Logger) (*AgentDialer, error) {
	if conn == nil {
		return nil, fmt.Errorf("nats connection is required")
	}
	if identityKey == nil {
		return nil, fmt.Errorf("identity key is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &AgentDialer{
		conn:        conn,
		identityKey: identityKey,
		identityPub: b64urlEncode(identityKey.PublicKey().Bytes()),
		logger:      logger,
	}, nil
}

// WithAttachmentStore attaches a NATSTransport whose lazily-initialized
// JetStream Object Store handle is borrowed by sessions opened by this dialer
// for object_store-tier (large-file) attachment transfers. Both peers in a
// session must share the same Object Store (typically because they speak to
// the same NATS cluster). Returns the dialer for chaining.
func (d *AgentDialer) WithAttachmentStore(transport *NATSTransport) *AgentDialer {
	d.transport = transport
	return d
}

// DialParams describes the agent session to open. The caller resolves the
// endpoint, satellite token, host identity key, and peer channel from the hub
// before dialing.
type DialParams struct {
	// SessionID is the session identifier; generated when empty.
	SessionID string
	// TargetUsername is the host's username. Requests publish to
	// syfthub.spaces.{TargetUsername}.
	TargetUsername string
	// HostPublicKeyB64 is the host's registered X25519 identity public key.
	HostPublicKeyB64 string
	// PeerChannel is the reply channel; events arrive on
	// syfthub.peer.{PeerChannel}.
	PeerChannel string
	// SatelliteToken proves the caller's identity to the host.
	SatelliteToken string
	// Prompt is the initial user prompt.
	Prompt string
	// EndpointSlug identifies the agent endpoint on the host.
	EndpointSlug string
	// Messages is optional prior conversation history.
	Messages []agenttypes.Message
	// Config is optional agent configuration.
	Config *agenttypes.AgentConfig
	// Capabilities lists optional protocol extensions (e.g. "attachments").
	Capabilities []string

	// SessionAttachmentKey is the 32-byte raw AES key shared between both
	// peers for wrapping per-file content keys with HKDF-derived KEKs. When
	// nil AND Capabilities contains AttachmentCapability, Dial mints a fresh
	// 32-byte key. The encoded form is sent (base64) in the session_start
	// payload so the host can construct the matching uploader/downloader.
	// Provide a non-nil value only for deterministic tests; production
	// callers should leave this nil.
	SessionAttachmentKey []byte

	// PaymentCredential is the wire-format mppx credential to ship in the
	// agent_session_start payload, used when the caller is restarting a
	// session in response to a prior agent.payment_required event. Empty
	// for fresh sessions; the host's policy chain will issue a challenge
	// and the caller is expected to dial again with a non-empty credential.
	PaymentCredential string
}

// Dial opens an agent session: it subscribes to the reply channel, publishes
// the encrypted agent_session_start, and returns a live session handle. Dial
// does not block on a host response — events surface on the returned session's
// Events() channel.
func (d *AgentDialer) Dial(ctx context.Context, p DialParams) (*AgentClientSession, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if p.TargetUsername == "" {
		return nil, fmt.Errorf("target username is required")
	}
	if p.HostPublicKeyB64 == "" {
		return nil, fmt.Errorf("host public key is required")
	}
	if p.PeerChannel == "" {
		return nil, fmt.Errorf("peer channel is required")
	}
	if p.EndpointSlug == "" {
		return nil, fmt.Errorf("endpoint slug is required")
	}

	sessionID := p.SessionID
	if sessionID == "" {
		sessionID = uuid.NewString()
	}

	cipher, err := NewSessionCipher(d.identityKey, p.HostPublicKeyB64, sessionID)
	if err != nil {
		return nil, fmt.Errorf("derive session cipher: %w", err)
	}

	// Mint the session attachment key when the caller requested the
	// "attachments" capability but didn't supply one explicitly. The same
	// 32-byte key is held client-side (for uploader/downloader construction)
	// and shipped, base64-encoded, in the session_start payload so the host
	// can build the matching encryptor.
	wantAttachments := slices.Contains(p.Capabilities, syfthubapi.AttachmentCapability)
	var sessionAESKey []byte
	if wantAttachments {
		sessionAESKey = p.SessionAttachmentKey
		if sessionAESKey == nil {
			sessionAESKey = make([]byte, 32)
			if _, err := rand.Read(sessionAESKey); err != nil {
				return nil, fmt.Errorf("mint session attachment key: %w", err)
			}
		} else if len(sessionAESKey) != 32 {
			return nil, fmt.Errorf("SessionAttachmentKey must be 32 bytes (got %d)", len(sessionAESKey))
		}
	}

	// Acquire the JetStream Object Store handle for object_store-tier
	// attachments. When the caller asked for attachments but we cannot
	// produce an object store, fail closed: advertising the capability
	// without backing storage means inline transfers work but any spill
	// over InlineMaxBytes blows up mid-send with an opaque error, after
	// the host has already minted state on the assumption that large
	// transfers are supported. Better to refuse at dial time so the
	// caller can either wire WithAttachmentStore or drop the capability.
	var attachmentStore AttachmentObjectStore
	if wantAttachments {
		if d.transport == nil {
			return nil, fmt.Errorf(
				"dialer has no attachment store — requested capability %q requires WithAttachmentStore(transport)",
				syfthubapi.AttachmentCapability)
		}
		store, storeErr := d.transport.getAttachmentObjectStore()
		if storeErr != nil {
			return nil, fmt.Errorf("acquire attachment object store: %w", storeErr)
		}
		attachmentStore = store
	}

	s := &AgentClientSession{
		SessionID:       sessionID,
		cipher:          cipher,
		senderPub:       d.identityPub,
		conn:            d.conn.Conn(),
		targetSubject:   spaceSubjectPrefix + p.TargetUsername,
		peerChannel:     p.PeerChannel,
		logger:          d.logger,
		inbox:           make(chan *nats.Msg, 256),
		events:          make(chan agenttypes.AgentEvent, 64),
		errs:            make(chan error, 8),
		done:            make(chan struct{}),
		sessionAESKey:   sessionAESKey,
		attachmentStore: attachmentStore,
	}

	// Subscribe to the reply channel before publishing so no early event is
	// missed.
	sub, err := s.conn.Subscribe(peerSubjectPrefix+p.PeerChannel, s.onMessage)
	if err != nil {
		return nil, fmt.Errorf("subscribe peer channel %q: %w", p.PeerChannel, err)
	}
	s.sub = sub

	startPayload := syfthubapi.AgentSessionStartPayload{
		SessionID:         sessionID,
		Prompt:            p.Prompt,
		EndpointSlug:      p.EndpointSlug,
		Messages:          p.Messages,
		Capabilities:      p.Capabilities,
		PaymentCredential: p.PaymentCredential,
	}
	if sessionAESKey != nil {
		startPayload.SessionAttachmentKey = base64.StdEncoding.EncodeToString(sessionAESKey)
	}
	if p.Config != nil {
		startPayload.Config = *p.Config
	}

	envelope, err := buildRequestEnvelope(
		cipher, d.identityPub, syfthubapi.MsgTypeAgentSessionStart,
		sessionID, uuid.NewString(), p.PeerChannel, p.SatelliteToken, startPayload,
	)
	if err != nil {
		_ = sub.Unsubscribe()
		return nil, err
	}
	if err := s.conn.Publish(s.targetSubject, envelope); err != nil {
		_ = sub.Unsubscribe()
		return nil, fmt.Errorf("publish agent_session_start: %w", err)
	}

	go s.run()
	return s, nil
}

// AgentClientSession is a live outbound agent session. Host events arrive on
// Events(); follow-up input is sent with SendMessage/Confirm/Deny; Cancel asks
// the host to stop; Close ends it locally.
type AgentClientSession struct {
	// SessionID is the unique session identifier.
	SessionID string

	cipher        *SessionCipher
	senderPub     string
	conn          *nats.Conn
	sub           *nats.Subscription
	targetSubject string
	peerChannel   string
	logger        *slog.Logger

	inbox  chan *nats.Msg
	events chan agenttypes.AgentEvent
	errs   chan error

	closeOnce sync.Once
	done      chan struct{}

	// Attachment state. sessionAESKey is the per-session 32-byte AES key
	// also shipped (base64) to the host in session_start; both peers derive
	// per-file KEKs from it. attachmentStore is the JetStream Object Store
	// handle borrowed from the dialer's transport (nil when the dialer was
	// constructed without WithAttachmentStore — in which case object_store
	// transfers fail). uploader/downloader are lazily built on first
	// large-file send/receive respectively.
	sessionAESKey   []byte
	attachmentStore AttachmentObjectStore
	upOnce          sync.Once
	uploader        syfthubapi.AttachmentUploader
	upErr           error
	dlOnce          sync.Once
	downloader      syfthubapi.AttachmentDownloader
	dlErr           error
}

// Events returns the channel of typed host events. It is closed when the
// session ends (terminal event, Cancel, or Close).
func (s *AgentClientSession) Events() <-chan agenttypes.AgentEvent { return s.events }

// Errors returns non-fatal decode/transport errors. Errors are also logged, so
// draining this channel is optional.
func (s *AgentClientSession) Errors() <-chan error { return s.errs }

// Done is closed when the session ends.
func (s *AgentClientSession) Done() <-chan struct{} { return s.done }

// SendMessage sends a follow-up user message to the agent.
func (s *AgentClientSession) SendMessage(content string) error {
	return s.sendUserMessage(syfthubapi.UserMessage{
		Type:    syfthubapi.UserMessageTypeMessage,
		Content: content,
	})
}

// SendMessageWithCredential sends a follow-up user message carrying a
// per-turn mppx payment credential. The producer's gateTurn passes the
// credential into the policy chain's per-turn PreVerify so an
// x402_pay_per_request endpoint can charge for each priced message. Use
// this after handling a mid-session agent.payment_required event:
// WalletPayChallenge signs a credential, then this method re-sends the
// same content carrying it.
func (s *AgentClientSession) SendMessageWithCredential(content, credential string) error {
	return s.sendUserMessage(syfthubapi.UserMessage{
		Type:              syfthubapi.UserMessageTypeMessage,
		Content:           content,
		PaymentCredential: credential,
	})
}

// Confirm approves a tool call awaiting confirmation.
func (s *AgentClientSession) Confirm(toolCallID string) error {
	return s.sendUserMessage(syfthubapi.UserMessage{
		Type:       syfthubapi.UserMessageTypeConfirm,
		ToolCallID: toolCallID,
	})
}

// Deny rejects a tool call awaiting confirmation.
func (s *AgentClientSession) Deny(toolCallID, reason string) error {
	return s.sendUserMessage(syfthubapi.UserMessage{
		Type:       syfthubapi.UserMessageTypeDeny,
		ToolCallID: toolCallID,
		Reason:     reason,
	})
}

func (s *AgentClientSession) sendUserMessage(m syfthubapi.UserMessage) error {
	return s.publishRequest(syfthubapi.MsgTypeAgentUserMessage,
		syfthubapi.AgentUserMessagePayload{SessionID: s.SessionID, Message: m})
}

// Cancel asks the host to end the session.
func (s *AgentClientSession) Cancel() error {
	return s.publishRequest(syfthubapi.MsgTypeAgentSessionCancel,
		syfthubapi.AgentSessionCancelPayload{SessionID: s.SessionID})
}

// Close ends the session locally — it unsubscribes and stops event delivery
// without notifying the host. Call Cancel first for a graceful stop.
func (s *AgentClientSession) Close() error {
	s.shutdown()
	return nil
}

func (s *AgentClientSession) publishRequest(msgType string, payload any) error {
	select {
	case <-s.done:
		return fmt.Errorf("agent session %s is closed", s.SessionID)
	default:
	}
	envelope, err := buildRequestEnvelope(
		s.cipher, s.senderPub, msgType, s.SessionID, uuid.NewString(), s.peerChannel, "", payload,
	)
	if err != nil {
		return err
	}
	if err := s.conn.Publish(s.targetSubject, envelope); err != nil {
		return fmt.Errorf("publish %s: %w", msgType, err)
	}
	return nil
}

// onMessage is the NATS subscription callback; it hands raw messages to run().
func (s *AgentClientSession) onMessage(msg *nats.Msg) {
	select {
	case s.inbox <- msg:
	case <-s.done:
	}
}

// run is the sole writer of events/errs and closes them when the session ends.
func (s *AgentClientSession) run() {
	defer close(s.events)
	defer close(s.errs)
	for {
		select {
		case <-s.done:
			return
		case msg := <-s.inbox:
			event, terminal, err := parseEventEnvelope(s.cipher, msg.Data)
			if err != nil {
				s.logger.Warn("agent client: dropped malformed event",
					"session_id", s.SessionID, "error", err)
				select {
				case s.errs <- err:
				default:
				}
				continue
			}
			if event == nil {
				continue
			}
			select {
			case s.events <- event:
			case <-s.done:
				return
			}
			if terminal {
				s.shutdown()
				return
			}
		}
	}
}

// shutdown unsubscribes and signals run() to stop. Idempotent.
func (s *AgentClientSession) shutdown() {
	s.closeOnce.Do(func() {
		if s.sub != nil {
			_ = s.sub.Unsubscribe()
		}
		close(s.done)
	})
}

// buildRequestEnvelope marshals payload, encrypts it for the request
// direction, and wraps it in a v2 AgentEnvelope ready to publish.
func buildRequestEnvelope(
	cipher *SessionCipher,
	senderPubB64, msgType, sessionID, correlationID, replyTo, satelliteToken string,
	payload any,
) ([]byte, error) {
	plaintext, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal %s payload: %w", msgType, err)
	}
	nonce, ciphertext, err := cipher.EncryptRequest(plaintext, correlationID)
	if err != nil {
		return nil, fmt.Errorf("encrypt %s payload: %w", msgType, err)
	}
	return json.Marshal(syfthubapi.AgentEnvelope{
		Protocol:         syfthubapi.AgentProtocolV2,
		Type:             msgType,
		CorrelationID:    correlationID,
		SessionID:        sessionID,
		ReplyTo:          replyTo,
		SatelliteToken:   satelliteToken,
		SenderPublicKey:  senderPubB64,
		Nonce:            nonce,
		EncryptedPayload: ciphertext,
	})
}

// parseEventEnvelope decodes a v2 AgentEnvelope received on the reply channel,
// decrypts the agent_event payload, and returns the typed event. It returns
// (nil, false, nil) for a non-event message; terminal is true for
// session.completed / session.failed.
func parseEventEnvelope(cipher *SessionCipher, raw []byte) (agenttypes.AgentEvent, bool, error) {
	var env syfthubapi.AgentEnvelope
	if err := json.Unmarshal(raw, &env); err != nil {
		return nil, false, fmt.Errorf("decode agent envelope: %w", err)
	}
	if env.Type != syfthubapi.MsgTypeAgentEvent {
		return nil, false, nil
	}
	plaintext, err := cipher.DecryptResponse(env.Nonce, env.EncryptedPayload, env.CorrelationID)
	if err != nil {
		return nil, false, fmt.Errorf("decrypt agent event: %w", err)
	}
	var payload syfthubapi.AgentEventPayload
	if err := json.Unmarshal(plaintext, &payload); err != nil {
		return nil, false, fmt.Errorf("decode agent event payload: %w", err)
	}
	ev, err := agenttypes.ParseAgentEvent(payload.EventType, payload.Data)
	if err != nil {
		return nil, false, err
	}
	terminal := payload.EventType == syfthubapi.EventTypeSessionCompleted ||
		payload.EventType == syfthubapi.EventTypeSessionFailed
	return ev, terminal, nil
}
