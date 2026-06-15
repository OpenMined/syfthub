// Package mcpbridge re-exposes a stdio MCP server as a streamable-HTTP
// http.Handler so a container endpoint can reach it through the egress broker.
//
// The trust split mirrors egressbroker: a stdio MCP server (e.g. the GitHub or
// Linear MCP server) runs ON THE HOST, holding whatever PAT/credential it
// needs. The container never speaks stdio to it and never holds its secret;
// instead the container makes streamable-HTTP MCP requests to a loopback relay,
// which the broker routes to this Bridge. The Bridge is a transparent tool
// proxy: it lists the upstream server's tools, exposes the identical set over
// HTTP, and forwards each tools/call to the upstream stdio child verbatim.
//
// One Bridge instance owns exactly one upstream child and serves one logical
// MCP server. Hosts that broker the same server for several endpoints create
// one Bridge per (endpoint, server) so a stateful child (e.g. a browser
// automation server) never shares session state across endpoints.
//
// Scope: tools only. Resources, prompts, sampling and dynamic listChanged
// notifications are intentionally not forwarded yet.
package mcpbridge

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os/exec"
	"sync"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// implementation identifies this bridge to MCP peers (both the upstream child,
// as a client, and the container, as a server).
var implementation = &mcp.Implementation{Name: "syfthub-mcp-bridge", Version: "0.1.0"}

// Config describes one stdio MCP server to bridge. Command is the host-side
// argv; Env is the explicit child environment (credentials live here — they
// stay on the host); Dir is the working directory (optional).
type Config struct {
	Command []string
	Env     map[string]string
	Dir     string
}

// Bridge runs one upstream MCP server and exposes its tools over
// streamable HTTP. Construct with NewStdio (production) or newWithTransport
// (tests), then Start, then mount Handler() behind the broker.
type Bridge struct {
	name      string
	logger    *slog.Logger
	transport mcp.Transport

	mu      sync.Mutex
	session *mcp.ClientSession
	handler http.Handler
	started bool
	closed  bool
}

// NewStdio builds a Bridge that runs Command as a stdio MCP child. name is the
// registry name (used only for logging/labels). The child is not spawned until
// Start.
func NewStdio(name string, cfg Config, logger *slog.Logger) (*Bridge, error) {
	if logger == nil {
		logger = slog.Default()
	}
	if len(cfg.Command) == 0 {
		return nil, fmt.Errorf("mcpbridge: %q has empty command", name)
	}
	// #nosec G204 — Command comes from the host-only MCP registry, authored by
	// the desktop user; it is never sourced from container or network input.
	cmd := exec.Command(cfg.Command[0], cfg.Command[1:]...)
	cmd.Dir = cfg.Dir
	cmd.Env = childEnv(cfg.Env)
	return &Bridge{
		name:      name,
		logger:    logger,
		transport: &mcp.CommandTransport{Command: cmd},
	}, nil
}

// NewHTTP builds a Bridge that connects to a remote streamable-HTTP MCP server
// at url. oauth is optional: when non-nil it drives the credential (OAuth)
// for outgoing requests — the go-sdk client performs the bearer attach/refresh,
// and (on a 401) the handler's Authorize. A nil oauth means the server needs no
// auth (or is brokered some other way). The connection is not opened until Start.
func NewHTTP(name, url string, oauth auth.OAuthHandler, logger *slog.Logger) (*Bridge, error) {
	if logger == nil {
		logger = slog.Default()
	}
	if url == "" {
		return nil, fmt.Errorf("mcpbridge: %q has empty url", name)
	}
	return &Bridge{
		name:   name,
		logger: logger,
		transport: &mcp.StreamableClientTransport{
			Endpoint:     url,
			OAuthHandler: oauth,
		},
	}, nil
}

// newWithTransport builds a Bridge over an arbitrary MCP transport. The test
// seam — production always goes through NewStdio / NewHTTP.
func newWithTransport(name string, t mcp.Transport, logger *slog.Logger) *Bridge {
	if logger == nil {
		logger = slog.Default()
	}
	return &Bridge{name: name, logger: logger, transport: t}
}

// Start connects to the upstream MCP server, snapshots its tool list, and
// builds the HTTP handler that re-exposes those tools. It is an error to Start
// twice. On any failure the upstream connection is torn down.
func (b *Bridge) Start(ctx context.Context) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.started {
		return fmt.Errorf("mcpbridge: %q already started", b.name)
	}
	if b.closed {
		return fmt.Errorf("mcpbridge: %q is closed", b.name)
	}

	client := mcp.NewClient(implementation, nil)
	session, err := client.Connect(ctx, b.transport, nil)
	if err != nil {
		return fmt.Errorf("mcpbridge: %q connect upstream: %w", b.name, err)
	}

	tools, err := listAllTools(ctx, session)
	if err != nil {
		_ = session.Close()
		return fmt.Errorf("mcpbridge: %q list tools: %w", b.name, err)
	}

	srv := mcp.NewServer(implementation, nil)
	names := make([]string, 0, len(tools))
	for _, t := range tools {
		// Re-expose each upstream tool verbatim (name, description, schema) and
		// forward calls to the upstream child. The raw AddTool form passes the
		// upstream's JSON Schema through untouched — we are a proxy, not a
		// validator.
		srv.AddTool(&mcp.Tool{
			Name:         t.Name,
			Title:        t.Title,
			Description:  t.Description,
			InputSchema:  t.InputSchema,
			OutputSchema: t.OutputSchema,
			Annotations:  t.Annotations,
		}, b.forward(t.Name))
		names = append(names, t.Name)
	}

	b.session = session
	// Stateless + JSON responses: tool calling is client→server only (no
	// server→client requests, which stateless mode forbids), so this keeps the
	// container-side MCP client trivial — a plain JSON-RPC POST returns a JSON
	// response, no session-id handshake or SSE framing required — while
	// remaining compatible with full streamable-HTTP clients (e.g. claude).
	b.handler = mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Logger: b.logger, Stateless: true, JSONResponse: true},
	)
	b.started = true
	b.logger.Info("mcp bridge started", "server", b.name, "tools", len(names))
	return nil
}

// forward returns a ToolHandler that proxies one tool call to the upstream
// child. A transport-level failure (child died, etc.) is surfaced as a tool
// error result so the agent sees it and can react, not as a protocol break.
func (b *Bridge) forward(name string) mcp.ToolHandler {
	return func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		b.mu.Lock()
		session := b.session
		b.mu.Unlock()
		if session == nil {
			return toolError(fmt.Sprintf("mcp server %q unavailable", b.name)), nil
		}
		// Arguments is the raw JSON received from the container; it marshals back
		// to the identical bytes for the upstream call.
		res, err := session.CallTool(ctx, &mcp.CallToolParams{
			Name:      name,
			Arguments: req.Params.Arguments,
		})
		if err != nil {
			b.logger.Warn("mcp bridge call failed", "server", b.name, "tool", name, "error", err)
			return toolError(fmt.Sprintf("mcp server %q call %q failed: %v — reload the endpoint to restart it", b.name, name, err)), nil
		}
		return res, nil
	}
}

// Handler returns the streamable-HTTP handler exposing the upstream's tools.
// nil until Start succeeds.
func (b *Bridge) Handler() http.Handler {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.handler
}

// Close terminates the upstream child (closing its stdin, which the SDK's
// CommandTransport follows with SIGTERM). Safe to call more than once.
func (b *Bridge) Close() error {
	b.mu.Lock()
	session := b.session
	b.session = nil
	b.handler = nil
	b.closed = true
	b.mu.Unlock()
	if session != nil {
		return session.Close()
	}
	return nil
}

// listAllTools pages through the upstream tools/list until the cursor is empty.
func listAllTools(ctx context.Context, session *mcp.ClientSession) ([]*mcp.Tool, error) {
	var out []*mcp.Tool
	params := &mcp.ListToolsParams{}
	for {
		res, err := session.ListTools(ctx, params)
		if err != nil {
			return nil, err
		}
		out = append(out, res.Tools...)
		if res.NextCursor == "" {
			return out, nil
		}
		params.Cursor = res.NextCursor
	}
}

// toolError builds a CallToolResult flagged as a tool error with a text body —
// the MCP-spec way to report a tool failure the model can see and self-correct
// from (as opposed to a protocol error, which it cannot).
func toolError(msg string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: msg}},
	}
}
