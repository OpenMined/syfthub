package mcpbridge

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// fakeUpstream serves a tiny MCP server (one echo tool) over the given
// transport, standing in for a real stdio MCP child. Returns a cancel func.
func fakeUpstream(t *testing.T, transport mcp.Transport) {
	t.Helper()
	srv := mcp.NewServer(&mcp.Implementation{Name: "fake", Version: "1.0.0"}, nil)
	srv.AddTool(
		&mcp.Tool{
			Name:        "echo",
			Description: "Echo the message back.",
			InputSchema: map[string]any{
				"type":       "object",
				"properties": map[string]any{"message": map[string]any{"type": "string"}},
				"required":   []any{"message"},
			},
		},
		func(_ context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			var args struct {
				Message string `json:"message"`
			}
			_ = json.Unmarshal(req.Params.Arguments, &args)
			return &mcp.CallToolResult{
				Content: []mcp.Content{&mcp.TextContent{Text: "echo: " + args.Message}},
			}, nil
		},
	)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	ss, err := srv.Connect(ctx, transport, nil)
	if err != nil {
		t.Fatalf("fake upstream connect: %v", err)
	}
	t.Cleanup(func() { _ = ss.Close() })
}

// startBridge wires a Bridge to an in-memory fake upstream and serves its HTTP
// handler, returning a connected MCP client session that talks to the bridge
// over streamable HTTP — i.e. exactly the path a containerized runner takes.
func startBridge(t *testing.T) *mcp.ClientSession {
	t.Helper()
	serverT, clientT := mcp.NewInMemoryTransports()
	fakeUpstream(t, serverT)

	b := newWithTransport("fake", clientT, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	t.Cleanup(cancel)
	if err := b.Start(ctx); err != nil {
		t.Fatalf("bridge start: %v", err)
	}
	t.Cleanup(func() { _ = b.Close() })

	ts := httptest.NewServer(b.Handler())
	t.Cleanup(ts.Close)

	client := mcp.NewClient(&mcp.Implementation{Name: "container", Version: "1.0.0"}, nil)
	cs, err := client.Connect(ctx, &mcp.StreamableClientTransport{Endpoint: ts.URL}, nil)
	if err != nil {
		t.Fatalf("container connect to bridge: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })
	return cs
}

func TestBridgeListsUpstreamTools(t *testing.T) {
	cs := startBridge(t)
	res, err := cs.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatalf("list tools: %v", err)
	}
	if len(res.Tools) != 1 || res.Tools[0].Name != "echo" {
		t.Fatalf("tools = %+v, want one tool named echo", res.Tools)
	}
	if res.Tools[0].Description != "Echo the message back." {
		t.Errorf("description not forwarded: %q", res.Tools[0].Description)
	}
	// The upstream JSON Schema must pass through so the model sees the real shape.
	schema, _ := json.Marshal(res.Tools[0].InputSchema)
	if want := `"message"`; !containsSub(string(schema), want) {
		t.Errorf("input schema %s missing %s", schema, want)
	}
}

func TestBridgeForwardsToolCall(t *testing.T) {
	cs := startBridge(t)
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "echo",
		Arguments: map[string]any{"message": "hi"},
	})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}
	if res.IsError {
		t.Fatalf("unexpected tool error: %+v", res)
	}
	if len(res.Content) != 1 {
		t.Fatalf("content = %+v, want one item", res.Content)
	}
	tc, ok := res.Content[0].(*mcp.TextContent)
	if !ok || tc.Text != "echo: hi" {
		t.Errorf("result = %+v, want text 'echo: hi'", res.Content[0])
	}
}

func TestBridgeToolErrorAfterClose(t *testing.T) {
	serverT, clientT := mcp.NewInMemoryTransports()
	fakeUpstream(t, serverT)
	b := newWithTransport("fake", clientT, nil)
	ctx := context.Background()
	if err := b.Start(ctx); err != nil {
		t.Fatalf("start: %v", err)
	}
	ts := httptest.NewServer(b.Handler())
	t.Cleanup(ts.Close)
	client := mcp.NewClient(&mcp.Implementation{Name: "container", Version: "1.0.0"}, nil)
	cs, err := client.Connect(ctx, &mcp.StreamableClientTransport{Endpoint: ts.URL}, nil)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })

	// Killing the upstream session makes subsequent calls surface as tool
	// errors (IsError) rather than protocol breaks, so the agent can react.
	_ = b.Close()
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "echo", Arguments: map[string]any{"message": "x"}})
	if err != nil {
		t.Fatalf("call after close returned protocol error, want tool error: %v", err)
	}
	if !res.IsError {
		t.Errorf("call after close: IsError = false, want true")
	}
}

func containsSub(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
