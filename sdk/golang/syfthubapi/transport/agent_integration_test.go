package transport

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"testing"
	"time"

	natsserver "github.com/nats-io/nats-server/v2/server"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// runEmbeddedNATS starts an in-process NATS server on a random free port.
func runEmbeddedNATS(t *testing.T) *natsserver.Server {
	t.Helper()
	s, err := natsserver.NewServer(&natsserver.Options{
		Host:   "127.0.0.1",
		Port:   -1, // random free port
		NoLog:  true,
		NoSigs: true,
	})
	if err != nil {
		t.Fatalf("create embedded NATS server: %v", err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("embedded NATS server not ready")
	}
	return s
}

// fakeAgentHandler is a minimal AgentSessionHandler: every StartSession spawns
// an agent that emits one message and completes.
type fakeAgentHandler struct {
	reply string
}

func (f *fakeAgentHandler) StartSession(payload syfthubapi.AgentSessionStartPayload, user *syfthubapi.UserContext) (*syfthubapi.AgentSession, error) {
	sess := syfthubapi.NewAgentSession(context.Background(), syfthubapi.AgentSessionParams{
		ID:           payload.SessionID,
		Prompt:       payload.Prompt,
		EndpointSlug: payload.EndpointSlug,
		User:         user,
	})
	reply := f.reply
	sess.RunHandler(func(ctx context.Context, s *syfthubapi.AgentSession) error {
		data, _ := json.Marshal(map[string]any{"content": reply, "is_complete": true})
		return s.Send(syfthubapi.AgentEventPayload{
			EventType: syfthubapi.EventTypeAgentMessage,
			Data:      data,
		})
	})
	return sess, nil
}

func (f *fakeAgentHandler) RouteMessage(syfthubapi.AgentUserMessagePayload) error { return nil }
func (f *fakeAgentHandler) CancelSession(string) error                            { return nil }
func (f *fakeAgentHandler) GetSession(string) (*syfthubapi.AgentSession, bool)    { return nil, false }

// TestAgentSessionEndToEnd runs a full v2 direct peer-to-peer agent session
// over an embedded NATS server: the AgentDialer (client) publishes an encrypted
// agent_session_start, the NATSTransport agent bridge (host) verifies the
// token, runs the agent, and relays an encrypted agent_event stream back. It
// exercises the entire path — identity-keyed crypto, the v2 wire envelope, NATS
// pub/sub, the bridge dispatch, and typed event decoding — with no aggregator.
func TestAgentSessionEndToEnd(t *testing.T) {
	srv := runEmbeddedNATS(t)
	defer srv.Shutdown()
	natsURL := srv.ClientURL()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	const hostUser = "hostalice"
	hostCreds := &syfthubapi.NATSCredentials{URL: natsURL, Subject: spaceSubjectPrefix + hostUser}

	// --- HOST: a NATSTransport agent bridge over the shared connection ---
	hostConn, err := NewNATSConn(hostCreds, "itest-host", logger)
	if err != nil {
		t.Fatalf("host NATSConn: %v", err)
	}
	defer hostConn.Close()

	hostT, err := NewNATSTransport(hostConn, &Config{
		SpaceURL:        "tunneling:" + hostUser,
		NATSCredentials: hostCreds,
		Logger:          logger,
	})
	if err != nil {
		t.Fatalf("NewNATSTransport: %v", err)
	}
	hostT.SetAgentHandler(&fakeAgentHandler{reply: "hello from host"})
	hostT.SetTokenVerifier(func(_ context.Context, _ string) (*syfthubapi.UserContext, error) {
		return &syfthubapi.UserContext{Sub: "u1", Username: hostUser, Role: "user"}, nil
	})

	ctx := t.Context()
	go func() { _ = hostT.Start(ctx) }()
	defer func() { _ = hostT.Stop(context.Background()) }()

	// Let the host's subscription register on the server before publishing.
	time.Sleep(200 * time.Millisecond)

	// --- CLIENT: an AgentDialer over its own connection ---
	clientKey, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("client keypair: %v", err)
	}
	clientConn, err := NewNATSConn(&syfthubapi.NATSCredentials{URL: natsURL}, "itest-client", logger)
	if err != nil {
		t.Fatalf("client NATSConn: %v", err)
	}
	defer clientConn.Close()

	dialer, err := NewAgentDialer(clientConn, clientKey, logger)
	if err != nil {
		t.Fatalf("NewAgentDialer: %v", err)
	}

	sess, err := dialer.Dial(ctx, DialParams{
		TargetUsername:   hostUser,
		HostPublicKeyB64: hostT.PublicKeyB64(),
		PeerChannel:      "itest-channel",
		SatelliteToken:   "fake-satellite-token",
		Prompt:           "hello host",
		EndpointSlug:     "agent1",
	})
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	defer sess.Close()

	// --- collect events until the stream closes (terminal event) ---
	var events []agenttypes.AgentEvent
	timeout := time.After(10 * time.Second)
collect:
	for {
		select {
		case ev, ok := <-sess.Events():
			if !ok {
				break collect
			}
			events = append(events, ev)
		case <-timeout:
			t.Fatalf("timed out waiting for events; got %d so far", len(events))
		}
	}

	// --- assert the message and the terminal event made the round trip ---
	var gotMessage, gotCompleted bool
	for _, ev := range events {
		switch e := ev.(type) {
		case *agenttypes.MessageEvent:
			if e.Content == "hello from host" {
				gotMessage = true
			}
		case *agenttypes.SessionCompletedEvent:
			gotCompleted = true
		}
	}
	if !gotMessage {
		t.Errorf("did not receive the expected agent.message event (got %d events)", len(events))
	}
	if !gotCompleted {
		t.Errorf("did not receive session.completed (got %d events)", len(events))
	}
}
