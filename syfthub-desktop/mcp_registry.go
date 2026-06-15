// Package main — host MCP server registry.
//
// The registry is the host-only catalog of MCP tool servers the desktop knows
// how to run, including their credentials (PATs, API keys). It lives in a
// 0600 file under the desktop dir and is NEVER exposed to containers: when an
// endpoint is allowed to use a server (frontmatter sandbox.expose_mcp), the
// egress broker brokers it host-side (see mcp_host.go) so the credential stays
// here. Bindings that surface the registry to the frontend return names and
// status only — never command env or headers.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpoauth"
)

const (
	mcpTransportStdio = "stdio"
	mcpTransportHTTP  = "http"

	mcpSourceManual       = "manual"
	mcpSourceClaude       = "import:claude"
	mcpSourceClaudePlugin = "import:claude-plugin"

	// Auth modes for http servers.
	mcpAuthNone   = "none"   // public / brokered some other way
	mcpAuthHeader = "header" // static credential in Headers (e.g. a PAT)
	mcpAuthOAuth  = "oauth"  // OAuth flow (host obtains + refreshes the token)
)

// mcpServerDef defines one MCP server. Command/Env (stdio) and URL/Headers
// (http) may carry credentials — they stay host-side and are never serialized
// to the frontend (see mcpServerInfo).
type mcpServerDef struct {
	Name      string            `json:"name"`
	Transport string            `json:"transport"` // "stdio" | "http"
	Command   []string          `json:"command,omitempty"`
	Env       map[string]string `json:"env,omitempty"`
	URL       string            `json:"url,omitempty"`
	Headers   map[string]string `json:"headers,omitempty"`
	Enabled   bool              `json:"enabled"`
	Source    string            `json:"source,omitempty"` // provenance, for the UI
	// Auth selects how an http server is credentialed: "header" (static, in
	// Headers), "oauth" (host runs the OAuth flow), or "none"/"" (public). Set
	// to "oauth" when the user connects an OAuth server; otherwise inferred
	// from Headers (see authMode).
	Auth string `json:"auth,omitempty"`
}

// authMode resolves the effective auth mode for an http server: explicit Auth
// wins; otherwise "header" when static headers are present, else "none".
func (d mcpServerDef) authMode() string {
	if d.Auth != "" {
		return d.Auth
	}
	if len(d.Headers) > 0 {
		return mcpAuthHeader
	}
	return mcpAuthNone
}

// validate checks the definition is well-formed for its transport. The name
// rule is mcpoauth's (the name becomes a broker route prefix /mcp/<name>/, an
// env-var value, AND the OAuth token-store key — one validator keeps a
// registry-valid name always storable).
func (d mcpServerDef) validate() error {
	if !mcpoauth.ValidServerName(d.Name) {
		return fmt.Errorf("mcp server name %q must be lowercase letters/digits with '-' or '_'", d.Name)
	}
	switch d.Transport {
	case mcpTransportStdio:
		if len(d.Command) == 0 {
			return fmt.Errorf("mcp server %q: stdio transport needs a command", d.Name)
		}
	case mcpTransportHTTP:
		if !strings.HasPrefix(d.URL, "http://") && !strings.HasPrefix(d.URL, "https://") {
			return fmt.Errorf("mcp server %q: http transport needs an http(s) url", d.Name)
		}
	default:
		return fmt.Errorf("mcp server %q: unknown transport %q", d.Name, d.Transport)
	}
	return nil
}

type mcpRegistryFile struct {
	Servers []mcpServerDef `json:"servers"`
}

// mcpRegistry is the persistent server catalog. All access is serialized; the
// file is the source of truth (re-read on each load) so an external edit is
// picked up.
type mcpRegistry struct {
	path string
	mu   sync.Mutex
}

func newMCPRegistry(dir string) *mcpRegistry {
	return &mcpRegistry{path: filepath.Join(dir, "mcp", "servers.json")}
}

// load reads the registry, returning an empty slice when the file is absent.
func (r *mcpRegistry) load() ([]mcpServerDef, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.loadLocked()
}

func (r *mcpRegistry) loadLocked() ([]mcpServerDef, error) {
	data, err := os.ReadFile(r.path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var f mcpRegistryFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("mcp registry %s: %w", r.path, err)
	}
	return f.Servers, nil
}

func (r *mcpRegistry) saveLocked(servers []mcpServerDef) error {
	if err := os.MkdirAll(filepath.Dir(r.path), 0o700); err != nil {
		return err
	}
	sort.Slice(servers, func(i, j int) bool { return servers[i].Name < servers[j].Name })
	data, err := json.MarshalIndent(mcpRegistryFile{Servers: servers}, "", "  ")
	if err != nil {
		return err
	}
	return writeFileAtomic0600(r.path, data)
}

// writeFileAtomic0600 writes data to path via a sibling temp file + rename, so
// a crash mid-write can never leave a torn file behind. 0600 because these
// files may carry credentials.
func writeFileAtomic0600(path string, data []byte) error {
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

// get returns the named server definition.
func (r *mcpRegistry) get(name string) (mcpServerDef, bool, error) {
	servers, err := r.load()
	if err != nil {
		return mcpServerDef{}, false, err
	}
	for _, s := range servers {
		if s.Name == name {
			return s, true, nil
		}
	}
	return mcpServerDef{}, false, nil
}

// mutate applies fn to the named server under lock and saves the registry.
// Returns an error if no server matches name.
func (r *mcpRegistry) mutate(name string, fn func(*mcpServerDef)) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	servers, err := r.loadLocked()
	if err != nil {
		return err
	}
	for i := range servers {
		if servers[i].Name == name {
			fn(&servers[i])
			return r.saveLocked(servers)
		}
	}
	return fmt.Errorf("mcp server %q not found", name)
}

// setEnabled flips the enabled flag for one server.
func (r *mcpRegistry) setEnabled(name string, on bool) error {
	return r.mutate(name, func(s *mcpServerDef) { s.Enabled = on })
}

// setAuth sets a server's auth mode (e.g. "oauth" after a successful connect).
func (r *mcpRegistry) setAuth(name, auth string) error {
	return r.mutate(name, func(s *mcpServerDef) { s.Auth = auth })
}

// mergeServerDef inserts def into servers, or replaces an existing entry with
// the same Name while preserving that entry's Enabled flag (so re-importing
// never silently re-enables a server the user turned off). The single
// definition of the merge rule, shared by upsert and applyImports.
func mergeServerDef(servers []mcpServerDef, def mcpServerDef) []mcpServerDef {
	for i := range servers {
		if servers[i].Name == def.Name {
			def.Enabled = servers[i].Enabled
			servers[i] = def
			return servers
		}
	}
	return append(servers, def)
}

// upsert inserts or replaces a single server definition (see mergeServerDef for
// the merge rule).
func (r *mcpRegistry) upsert(def mcpServerDef) error {
	if err := def.validate(); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	servers, err := r.loadLocked()
	if err != nil {
		return err
	}
	return r.saveLocked(mergeServerDef(servers, def))
}

// claudeMCPServer is one entry in a Claude mcpServers map (in ~/.claude.json or
// a plugin's .mcp.json). Extra keys (e.g. _meta) are ignored.
type claudeMCPServer struct {
	Type    string            `json:"type"`
	URL     string            `json:"url"`
	Headers map[string]string `json:"headers"`
	Command string            `json:"command"`
	Args    []string          `json:"args"`
	Env     map[string]string `json:"env"`
}

// claudeMCPFile is any JSON file carrying an mcpServers map.
type claudeMCPFile struct {
	MCPServers map[string]claudeMCPServer `json:"mcpServers"`
}

// installedPlugins is the subset of ~/.claude/plugins/installed_plugins.json we
// read: plugin id → install records (we only need each record's installPath).
type installedPlugins struct {
	Plugins map[string][]struct {
		InstallPath string `json:"installPath"`
	} `json:"plugins"`
}

// importFromClaude discovers MCP servers from a user's Claude setup and upserts
// each as a (disabled-by-default) registry entry, so exposing one to an endpoint
// is a deliberate act. It reads two sources:
//   - claudeJSON (~/.claude.json) top-level mcpServers — the Local/User servers.
//   - pluginsDir (~/.claude/plugins) — each installed plugin's .mcp.json, which
//     is how plugin-provided servers (e.g. figma) are declared; these never
//     appear in ~/.claude.json.
//
// Missing files are not errors (a user may have only one source); a malformed
// file that exists is. Returns the import count and the names skipped
// (unsupported shape / unsafe name).
func (r *mcpRegistry) importFromClaude(claudeJSON, pluginsDir string) (imported int, skipped []string, err error) {
	type batch struct {
		servers map[string]claudeMCPServer
		source  string
	}
	var batches []batch

	servers, ok, err := readMCPFile(claudeJSON)
	if err != nil {
		return 0, nil, err
	}
	if ok {
		batches = append(batches, batch{servers, mcpSourceClaude})
	}

	plugins, err := readPluginMCPFiles(pluginsDir)
	if err != nil {
		return 0, nil, err
	}
	for _, servers := range plugins {
		batches = append(batches, batch{servers, mcpSourceClaudePlugin})
	}

	if len(batches) == 0 {
		return 0, nil, fmt.Errorf("no Claude MCP config found (looked in %s and %s)", claudeJSON, pluginsDir)
	}

	// All upserts land in one load→apply→save transaction, so importing M
	// servers rewrites the registry file once, not M times.
	r.mu.Lock()
	defer r.mu.Unlock()
	existing, err := r.loadLocked()
	if err != nil {
		return 0, nil, err
	}
	for _, b := range batches {
		var i int
		var sk []string
		existing, i, sk = applyImports(existing, b.servers, b.source)
		imported += i
		skipped = append(skipped, sk...)
	}
	if imported == 0 {
		return 0, skipped, nil
	}
	if err := r.saveLocked(existing); err != nil {
		return 0, nil, err
	}
	return imported, skipped, nil
}

// applyImports merges a Claude mcpServers map into servers, tagging each entry
// with source. New entries are disabled by default; a replaced entry keeps its
// prior Enabled flag (re-importing never silently re-enables a server the user
// turned off). Pure transform — locking and persistence are the caller's.
func applyImports(servers []mcpServerDef, imports map[string]claudeMCPServer, source string) (out []mcpServerDef, imported int, skipped []string) {
	for name, s := range imports {
		def := mcpServerDef{Name: name, Enabled: false, Source: source}
		switch {
		case s.URL != "":
			def.Transport = mcpTransportHTTP
			def.URL = s.URL
			def.Headers = s.Headers
		case s.Command != "":
			def.Transport = mcpTransportStdio
			def.Command = append([]string{s.Command}, s.Args...)
			def.Env = s.Env
		default:
			skipped = append(skipped, name)
			continue
		}
		if err := def.validate(); err != nil {
			skipped = append(skipped, name)
			continue
		}
		servers = mergeServerDef(servers, def)
		imported++
	}
	return servers, imported, skipped
}

// readMCPFile reads an mcpServers map from a JSON file. ok is false when the
// file is absent or declares no servers; a parse error of an existing file is
// returned.
func readMCPFile(path string) (servers map[string]claudeMCPServer, ok bool, err error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}
		return nil, false, err
	}
	var f claudeMCPFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, false, fmt.Errorf("parse %s: %w", path, err)
	}
	return f.MCPServers, len(f.MCPServers) > 0, nil
}

// readPluginMCPFiles returns the mcpServers map from each installed plugin that
// ships an .mcp.json. A missing plugins dir/manifest yields no servers (not an
// error); a plugin whose .mcp.json is absent or empty is skipped.
func readPluginMCPFiles(pluginsDir string) ([]map[string]claudeMCPServer, error) {
	manifest := filepath.Join(pluginsDir, "installed_plugins.json")
	data, err := os.ReadFile(manifest)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var ip installedPlugins
	if err := json.Unmarshal(data, &ip); err != nil {
		return nil, fmt.Errorf("parse %s: %w", manifest, err)
	}
	var out []map[string]claudeMCPServer
	for _, recs := range ip.Plugins {
		for _, rec := range recs {
			if rec.InstallPath == "" {
				continue
			}
			servers, ok, err := readMCPFile(filepath.Join(rec.InstallPath, ".mcp.json"))
			if err != nil || !ok {
				continue // unparsable or no servers — skip this plugin
			}
			out = append(out, servers)
			break // first install record with an .mcp.json wins
		}
	}
	return out, nil
}
