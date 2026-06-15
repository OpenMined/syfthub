package mcpbridge

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// rawCall posts one JSON-RPC request to the bridge handler exactly as a
// dependency-free runner client would (plain application/json, no session-id
// handshake), and returns the decoded JSON-RPC response.
func rawCall(t *testing.T, base, method string, params any) map[string]any {
	t.Helper()
	body, _ := json.Marshal(map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  method,
		"params":  params,
	})
	req, _ := http.NewRequest("POST", base, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s: %v", method, err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("%s: status %d: %s", method, resp.StatusCode, raw)
	}
	// Stateless+JSON returns application/json; tolerate an SSE frame just in
	// case, mirroring what the Python client does.
	payload := raw
	if bytes.HasPrefix(bytes.TrimSpace(raw), []byte("event:")) ||
		bytes.Contains(raw, []byte("\ndata:")) || bytes.HasPrefix(raw, []byte("data:")) {
		for line := range strings.SplitSeq(string(raw), "\n") {
			if strings.HasPrefix(line, "data:") {
				payload = []byte(strings.TrimSpace(line[len("data:"):]))
			}
		}
	}
	var out map[string]any
	if err := json.Unmarshal(payload, &out); err != nil {
		t.Fatalf("%s: decode %s: %v", method, payload, err)
	}
	return out
}

// TestBridgeRawJSONRPCClient proves a dependency-free client (the shape the
// research-agent runner uses) can list and call tools against the bridge with
// plain JSON-RPC POSTs — no MCP session handshake, no SSE parsing.
func TestBridgeRawJSONRPCClient(t *testing.T) {
	serverT, clientT := mcp.NewInMemoryTransports()
	fakeUpstream(t, serverT)
	b := newWithTransport("fake", clientT, nil)
	if err := b.Start(context.Background()); err != nil {
		t.Fatalf("start: %v", err)
	}
	t.Cleanup(func() { _ = b.Close() })
	ts := httptest.NewServer(b.Handler())
	t.Cleanup(ts.Close)

	// A stateless server auto-initializes a temporary session, so tools/list
	// works without a prior initialize handshake.
	list := rawCall(t, ts.URL, "tools/list", map[string]any{})
	result, _ := list["result"].(map[string]any)
	tools, _ := result["tools"].([]any)
	if len(tools) != 1 {
		t.Fatalf("tools/list returned %d tools, want 1: %v", len(tools), list)
	}

	call := rawCall(t, ts.URL, "tools/call", map[string]any{
		"name":      "echo",
		"arguments": map[string]any{"message": "raw"},
	})
	res, _ := call["result"].(map[string]any)
	content, _ := res["content"].([]any)
	if len(content) == 0 {
		t.Fatalf("tools/call returned no content: %v", call)
	}
	first, _ := content[0].(map[string]any)
	if text, _ := first["text"].(string); text != "echo: raw" {
		t.Errorf("tools/call text = %v, want 'echo: raw'", first)
	}
}
