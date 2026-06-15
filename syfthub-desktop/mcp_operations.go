// Package main — Wails bindings for the host MCP server registry.
//
// These surface the registry to the frontend so the user can see which MCP
// servers are configured, enable/disable them, and import from their Claude
// config. They deliberately expose names and status ONLY — never a server's
// command, env, url, or headers, any of which may carry a credential.
package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpoauth"
)

// MCPServerInfo is the secret-free view of a registry server for the frontend.
type MCPServerInfo struct {
	Name       string `json:"name"`
	Transport  string `json:"transport"` // "stdio" | "http"
	Enabled    bool   `json:"enabled"`
	Source     string `json:"source"`     // "manual" | "import:claude" | "import:claude-plugin"
	AuthMode   string `json:"authMode"`   // "none" | "header" | "oauth"
	AuthStatus string `json:"authStatus"` // oauth only: "not_connected" | "connected" | "expired"
}

// MCPImportResult summarizes an import-from-Claude run.
type MCPImportResult struct {
	Imported int      `json:"imported"`
	Skipped  []string `json:"skipped"`
}

func (a *App) mcpReg() *mcpRegistry {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.mcpRegistry
}

func (a *App) mcpOAuthMgr() *oauthManager {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.mcpOAuth
}

// ListMCPServers returns the configured MCP servers (names, status, and auth
// mode/status only — never secrets). Returns an empty slice when the registry
// is unavailable or empty.
func (a *App) ListMCPServers() ([]MCPServerInfo, error) {
	reg := a.mcpReg()
	if reg == nil {
		return []MCPServerInfo{}, nil
	}
	servers, err := reg.load()
	if err != nil {
		return nil, err
	}
	om := a.mcpOAuthMgr()
	out := make([]MCPServerInfo, 0, len(servers))
	for _, s := range servers {
		source := s.Source
		if source == "" {
			source = mcpSourceManual
		}
		info := MCPServerInfo{
			Name:      s.Name,
			Transport: s.Transport,
			Enabled:   s.Enabled,
			Source:    source,
			AuthMode:  s.authMode(),
		}
		if info.AuthMode == mcpAuthOAuth && om != nil {
			if st, err := om.Status(s.Name, s.URL); err == nil {
				info.AuthStatus = st
			}
		}
		out = append(out, info)
	}
	return out, nil
}

// ConnectMCPServer runs the interactive OAuth flow for a remote (http) MCP
// server: it opens the browser, captures the redirect, and persists the token
// host-side. On success the server is marked oauth and endpoints are reloaded
// so any that expose it pick it up. If the server turns out to need no auth,
// it is marked accordingly and left usable. Blocks until the flow completes.
func (a *App) ConnectMCPServer(name string) error {
	reg := a.mcpReg()
	om := a.mcpOAuthMgr()
	if reg == nil || om == nil {
		return fmt.Errorf("mcp not initialized")
	}
	def, ok, err := reg.get(name)
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("mcp server %q not found", name)
	}
	if def.Transport != mcpTransportHTTP {
		return fmt.Errorf("only http MCP servers use OAuth")
	}

	// If the user already authorized this server in Claude, reuse that token —
	// no second authorization needed (and the only path for servers like figma
	// that gate registration to Claude).
	if om.claudeHasToken(def.URL) {
		if err := reg.setAuth(name, mcpAuthOAuth); err != nil {
			return err
		}
		a.reloadAfterEndpointMutation("mcp:" + name)
		return nil
	}

	err = om.Connect(a.ctx, name, def.URL)
	if errors.Is(err, mcpoauth.ErrAuthNotRequired) {
		_ = reg.setAuth(name, mcpAuthNone)
		return fmt.Errorf("%q needs no authorization — it is ready to use", name)
	}
	if errors.Is(err, mcpoauth.ErrRegistrationForbidden) {
		return fmt.Errorf("%q does not allow direct registration — authorize it in Claude (it shares the same host), then SyftHub will reuse that connection", name)
	}
	if err != nil {
		return err
	}
	if err := reg.setAuth(name, mcpAuthOAuth); err != nil {
		return err
	}
	a.reloadAfterEndpointMutation("mcp:" + name)
	return nil
}

// DisconnectMCPServer clears a remote MCP server's stored OAuth tokens and
// reloads endpoints so any running bridge to it is torn down.
func (a *App) DisconnectMCPServer(name string) error {
	om := a.mcpOAuthMgr()
	if om == nil {
		return nil
	}
	if err := om.Disconnect(name); err != nil {
		return err
	}
	if a.ctx != nil {
		runtime.LogInfo(a.ctx, fmt.Sprintf("MCP server %q disconnected", name))
	}
	a.reloadAfterEndpointMutation("mcp:" + name)
	return nil
}

// SetMCPServerEnabled enables or disables a registered MCP server. The change
// takes effect the next time an endpoint that exposes it is (re)provisioned.
func (a *App) SetMCPServerEnabled(name string, enabled bool) error {
	reg := a.mcpReg()
	if reg == nil {
		return fmt.Errorf("mcp registry unavailable")
	}
	if err := reg.setEnabled(name, enabled); err != nil {
		return err
	}
	if a.ctx != nil {
		runtime.LogInfo(a.ctx, fmt.Sprintf("MCP server %q enabled=%v", name, enabled))
	}
	return nil
}

// ImportMCPServersFromClaudeConfig reads ~/.claude.json and upserts its
// mcpServers into the registry, disabled by default. Returns how many were
// imported and which were skipped (unsupported shape / unsafe name).
func (a *App) ImportMCPServersFromClaudeConfig() (*MCPImportResult, error) {
	reg := a.mcpReg()
	if reg == nil {
		return nil, fmt.Errorf("mcp registry unavailable")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, fmt.Errorf("resolve home dir: %w", err)
	}
	imported, skipped, err := reg.importFromClaude(
		filepath.Join(home, ".claude.json"),
		filepath.Join(home, ".claude", "plugins"),
	)
	if err != nil {
		return nil, err
	}
	if a.ctx != nil {
		runtime.LogInfo(a.ctx, fmt.Sprintf("Imported %d MCP server(s) from Claude config (skipped %d)", imported, len(skipped)))
	}
	return &MCPImportResult{Imported: imported, Skipped: skipped}, nil
}
