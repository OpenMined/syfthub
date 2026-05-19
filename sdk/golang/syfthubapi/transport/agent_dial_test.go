package transport

import (
	"encoding/json"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// TestBuildRequestEnvelope_RoundTrip verifies the client builds a v2 envelope
// the host can decode and decrypt.
func TestBuildRequestEnvelope_RoundTrip(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "sess-1"

	clientCipher, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	hostCipher, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	start := syfthubapi.AgentSessionStartPayload{
		SessionID:    sid,
		Prompt:       "hello",
		EndpointSlug: "code-assistant",
	}
	raw, err := buildRequestEnvelope(
		clientCipher, clientPub, syfthubapi.MsgTypeAgentSessionStart,
		sid, "corr-1", "peer-xyz", "sat-token", start,
	)
	if err != nil {
		t.Fatalf("buildRequestEnvelope: %v", err)
	}

	// Host side: decode the wrapper, then decrypt with the request key.
	var env syfthubapi.AgentEnvelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatal(err)
	}
	if env.Protocol != syfthubapi.AgentProtocolV2 {
		t.Errorf("protocol = %q, want %q", env.Protocol, syfthubapi.AgentProtocolV2)
	}
	if env.Type != syfthubapi.MsgTypeAgentSessionStart {
		t.Errorf("type = %q", env.Type)
	}
	if env.ReplyTo != "peer-xyz" {
		t.Errorf("reply_to = %q", env.ReplyTo)
	}
	if env.SatelliteToken != "sat-token" {
		t.Errorf("satellite_token = %q", env.SatelliteToken)
	}
	if env.SenderPublicKey != clientPub {
		t.Errorf("sender_public_key mismatch")
	}

	plaintext, err := hostCipher.DecryptRequest(env.Nonce, env.EncryptedPayload, env.CorrelationID)
	if err != nil {
		t.Fatalf("host decrypt: %v", err)
	}
	var got syfthubapi.AgentSessionStartPayload
	if err := json.Unmarshal(plaintext, &got); err != nil {
		t.Fatal(err)
	}
	if got.SessionID != sid || got.Prompt != "hello" || got.EndpointSlug != "code-assistant" {
		t.Fatalf("payload mismatch: %+v", got)
	}
}

// TestParseEventEnvelope_RoundTrip verifies the client decodes a host event.
func TestParseEventEnvelope_RoundTrip(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "sess-2"

	clientCipher, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	hostCipher, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	// Host builds an encrypted agent_event envelope.
	eventPayload := syfthubapi.AgentEventPayload{
		SessionID: sid,
		EventType: "agent.message",
		Sequence:  3,
		Data:      json.RawMessage(`{"content":"hi there","is_complete":true}`),
	}
	plaintext, err := json.Marshal(eventPayload)
	if err != nil {
		t.Fatal(err)
	}
	corr := sid + "-3"
	nonce, ct, err := hostCipher.EncryptResponse(plaintext, corr)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(syfthubapi.AgentEnvelope{
		Protocol:         syfthubapi.AgentProtocolV2,
		Type:             syfthubapi.MsgTypeAgentEvent,
		CorrelationID:    corr,
		SessionID:        sid,
		SenderPublicKey:  hostPub,
		Nonce:            nonce,
		EncryptedPayload: ct,
	})
	if err != nil {
		t.Fatal(err)
	}

	ev, terminal, err := parseEventEnvelope(clientCipher, raw)
	if err != nil {
		t.Fatalf("parseEventEnvelope: %v", err)
	}
	if terminal {
		t.Error("agent.message should not be terminal")
	}
	msg, ok := ev.(*agenttypes.MessageEvent)
	if !ok {
		t.Fatalf("expected *MessageEvent, got %T", ev)
	}
	if msg.Content != "hi there" || !msg.IsComplete {
		t.Fatalf("event content mismatch: %+v", msg)
	}
}

// TestParseEventEnvelope_Terminal verifies session.completed is flagged terminal.
func TestParseEventEnvelope_Terminal(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "sess-3"

	clientCipher, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	hostCipher, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	eventPayload := syfthubapi.AgentEventPayload{
		SessionID: sid,
		EventType: "session.completed",
		Sequence:  9,
		Data:      json.RawMessage(`{"session_id":"sess-3"}`),
	}
	plaintext, _ := json.Marshal(eventPayload)
	corr := sid + "-9"
	nonce, ct, err := hostCipher.EncryptResponse(plaintext, corr)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(syfthubapi.AgentEnvelope{
		Protocol:         syfthubapi.AgentProtocolV2,
		Type:             syfthubapi.MsgTypeAgentEvent,
		CorrelationID:    corr,
		SessionID:        sid,
		SenderPublicKey:  hostPub,
		Nonce:            nonce,
		EncryptedPayload: ct,
	})

	_, terminal, err := parseEventEnvelope(clientCipher, raw)
	if err != nil {
		t.Fatal(err)
	}
	if !terminal {
		t.Error("session.completed must be flagged terminal")
	}
}

// TestParseEventEnvelope_NonEvent verifies non-event messages are ignored.
func TestParseEventEnvelope_NonEvent(t *testing.T) {
	clientKey, _ := newTestIdentity(t)
	_, hostPub := newTestIdentity(t)
	clientCipher, err := NewSessionCipher(clientKey, hostPub, "s")
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(syfthubapi.AgentEnvelope{
		Protocol: syfthubapi.AgentProtocolV2,
		Type:     "something_else",
	})
	ev, terminal, err := parseEventEnvelope(clientCipher, raw)
	if ev != nil || terminal || err != nil {
		t.Fatalf("non-event should be ignored, got ev=%v terminal=%v err=%v", ev, terminal, err)
	}
}

func TestNewAgentDialer_Validation(t *testing.T) {
	key, _ := newTestIdentity(t)
	if _, err := NewAgentDialer(nil, key, nil); err == nil {
		t.Error("expected error for nil connection")
	}
	if _, err := NewAgentDialer(&NATSConn{}, nil, nil); err == nil {
		t.Error("expected error for nil identity key")
	}
}
