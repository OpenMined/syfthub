package syfthub

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"
)

// recordingAggregator is a tiny WebSocket server stub that records the first
// N WS frames it receives and emits a session.created envelope + any events
// the test schedules. It lets us exercise the CLIENT SDK's attachment send +
// receive paths end-to-end (over a real WS) without needing the real
// aggregator + NATS + HOST chain.
func newRecordingAggregator(t *testing.T, scriptedEvents []map[string]any) (url string, received chan []byte, cleanup func()) {
	t.Helper()
	received = make(chan []byte, 16)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
			InsecureSkipVerify: true,
		})
		if err != nil {
			t.Logf("accept: %v", err)
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "test done")

		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()

		// First inbound: session.start
		_, data, err := conn.Read(ctx)
		if err != nil {
			t.Logf("read session.start: %v", err)
			return
		}
		received <- data

		// Respond with session.created so the SDK proceeds.
		_ = conn.Write(ctx, websocket.MessageText, mustJSON(map[string]any{
			"type":       "session.created",
			"session_id": "sess-test-1",
			"payload": map[string]any{
				"session_id": "sess-test-1",
			},
		}))

		// Emit scripted events.
		for _, evt := range scriptedEvents {
			_ = conn.Write(ctx, websocket.MessageText, mustJSON(evt))
		}

		// Drain any subsequent inbound frames the test wants to inspect.
		for {
			_, data, err := conn.Read(ctx)
			if err != nil {
				return
			}
			received <- data
		}
	}))

	// Patch URL scheme to ws://
	wsURL := strings.Replace(srv.URL, "http://", "ws://", 1)
	return wsURL, received, srv.Close
}

func mustJSON(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return b
}

func TestAttachmentEventParsedFromInlineFrame(t *testing.T) {
	body := []byte("hello world")
	sum := sha256.Sum256(body)
	scripted := []map[string]any{
		{
			"type":       "agent.attachment",
			"session_id": "sess-test-1",
			"payload": map[string]any{
				"file_id":          "att-42",
				"name":             "hello.txt",
				"mime":             "text/plain",
				"size_bytes":       int64(len(body)),
				"plaintext_sha256": hex.EncodeToString(sum[:]),
				"transport":        "inline",
				"inline_data_b64":  base64.StdEncoding.EncodeToString(body),
			},
		},
		{
			"type":       "session.completed",
			"session_id": "sess-test-1",
			"payload":    map[string]any{"session_id": "sess-test-1"},
		},
	}
	url, _, cleanup := newRecordingAggregator(t, scripted)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	// Send session.start so the server emits scripted events.
	if err := conn.Write(ctx, websocket.MessageText, mustJSON(map[string]any{
		"type": "session.start",
		"payload": map[string]any{
			"prompt":          "hi",
			"endpoint":        map[string]string{"owner": "alice", "slug": "bot"},
			"satellite_token": "x",
			"capabilities":    []string{"attachments"},
		},
	})); err != nil {
		t.Fatalf("write session.start: %v", err)
	}
	// Read & discard session.created
	if _, _, err := conn.Read(ctx); err != nil {
		t.Fatalf("read session.created: %v", err)
	}

	client := newAgentSessionClient(conn, "sess-test-1")
	defer client.Close()

	var got *AttachmentEvent
	for ev := range client.Events() {
		if att, ok := ev.(*AttachmentEvent); ok {
			got = att
			break
		}
	}
	if got == nil {
		t.Fatal("did not receive AttachmentEvent")
	}
	if got.FileID != "att-42" || got.Transport != "inline" || got.SizeBytes != int64(len(body)) {
		t.Fatalf("unexpected attachment: %+v", got)
	}
	decoded, err := got.Bytes()
	if err != nil {
		t.Fatalf("Bytes: %v", err)
	}
	if string(decoded) != string(body) {
		t.Fatalf("body mismatch: %q vs %q", decoded, body)
	}
}

func TestSendAttachmentBuildsCorrectFrame(t *testing.T) {
	url, received, cleanup := newRecordingAggregator(t, nil)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	// session.start
	_ = conn.Write(ctx, websocket.MessageText, mustJSON(map[string]any{"type": "session.start"}))
	<-received // drain session.start
	if _, _, err := conn.Read(ctx); err != nil {
		t.Fatalf("read session.created: %v", err)
	}

	client := newAgentSessionClient(conn, "sess-test-1")
	defer client.Close()

	body := []byte("attached body")
	fileID, err := client.SendAttachmentBytes(ctx, body, AttachmentOpts{Name: "f.bin", MIME: "application/octet-stream"})
	if err != nil {
		t.Fatalf("SendAttachmentBytes: %v", err)
	}
	if !strings.HasPrefix(fileID, "att-") {
		t.Fatalf("file_id missing prefix: %q", fileID)
	}

	select {
	case raw := <-received:
		var frame struct {
			Type    string          `json:"type"`
			Payload json.RawMessage `json:"payload"`
		}
		if err := json.Unmarshal(raw, &frame); err != nil {
			t.Fatalf("parse frame: %v", err)
		}
		if frame.Type != "user.attachment" {
			t.Fatalf("unexpected frame type: %q", frame.Type)
		}
		var att AttachmentEvent
		if err := json.Unmarshal(frame.Payload, &att); err != nil {
			t.Fatalf("parse attachment: %v", err)
		}
		if att.FileID != fileID || att.Transport != "inline" {
			t.Fatalf("attachment mismatch: %+v", att)
		}
		got, err := att.Bytes()
		if err != nil {
			t.Fatal(err)
		}
		if string(got) != string(body) {
			t.Fatalf("body mismatch: %q vs %q", got, body)
		}
		sum := sha256.Sum256(body)
		if att.PlaintextSHA256 != hex.EncodeToString(sum[:]) {
			t.Fatalf("sha mismatch in frame")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no frame received within timeout")
	}
}

func TestSendAttachmentRejectsOversize(t *testing.T) {
	// Build a fake AgentSessionClient — we don't need the WS for this test
	// since the size check fires before any send.
	srv, cleanup := startEchoListener(t)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	conn, _, err := websocket.Dial(ctx, srv, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "")

	client := newAgentSessionClient(conn, "sess-test-1")
	defer client.Close()

	oversize := make([]byte, InlineAttachmentMaxBytes+1)
	_, err = client.SendAttachmentBytes(ctx, oversize, AttachmentOpts{})
	if err == nil {
		t.Fatal("expected error for oversize attachment")
	}
}

func startEchoListener(t *testing.T) (string, func()) {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			t.Logf("accept: %v", err)
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		for {
			_, _, err := conn.Read(ctx)
			if err != nil {
				return
			}
		}
	}))
	return strings.Replace(srv.URL, "http://", "ws://", 1), srv.Close
}

// Suppress unused import warning when running on older toolchains.
var _ = net.Dial
