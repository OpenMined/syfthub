package syfthubapi

// AgentProtocolV2 is the protocol tag carried by every v2 (direct
// peer-to-peer) agent session NATS message. It replaces the aggregator-relayed
// v1 tunnel protocol for interactive agent sessions.
const AgentProtocolV2 = "syfthub-agent/v2"

// AgentEnvelope is the v2 NATS message wrapper for a direct peer-to-peer agent
// session. Both peers hold an X25519 identity key; EncryptedPayload is an
// AES-256-GCM ciphertext of the message-type-specific payload
// (AgentSessionStartPayload, AgentUserMessagePayload, AgentSessionCancelPayload,
// AgentUserAttachmentPayload, or AgentEventPayload). The wrapper fields are
// plaintext so the recipient can derive the session key and decrypt.
//
// Request messages (agent_session_start / agent_user_message /
// agent_session_cancel / agent_user_attachment) flow client→host on
// syfthub.spaces.{host}; agent_event messages flow host→client on
// syfthub.peer.{peer_channel}.
type AgentEnvelope struct {
	// Protocol is always AgentProtocolV2.
	Protocol string `json:"protocol"`

	// Type is the message type: MsgTypeAgentSessionStart, MsgTypeAgentUserMessage,
	// MsgTypeAgentSessionCancel, MsgTypeAgentUserAttachment, or MsgTypeAgentEvent.
	Type string `json:"type"`

	// CorrelationID uniquely identifies this message and is bound as the
	// AES-GCM additional authenticated data. Events use "{session_id}-{sequence}".
	CorrelationID string `json:"correlation_id"`

	// SessionID is the agent session this message belongs to.
	SessionID string `json:"session_id"`

	// ReplyTo is the peer channel the sender listens on for events. Set on
	// agent_session_start; the host relays events to syfthub.peer.{ReplyTo}.
	ReplyTo string `json:"reply_to,omitempty"`

	// SatelliteToken proves the caller's identity to the host. Set on
	// agent_session_start.
	SatelliteToken string `json:"satellite_token,omitempty"`

	// SenderPublicKey is the sender's X25519 identity public key (base64url,
	// raw 32 bytes). The recipient derives the session key from it.
	SenderPublicKey string `json:"sender_public_key"`

	// Nonce is the base64url AES-256-GCM nonce (12 bytes).
	Nonce string `json:"nonce"`

	// EncryptedPayload is the base64url AES-256-GCM ciphertext+tag.
	EncryptedPayload string `json:"encrypted_payload"`
}
