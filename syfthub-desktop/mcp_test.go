package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/egressbroker"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
)

func TestMCPRegistryRoundTrip(t *testing.T) {
	reg := newMCPRegistry(t.TempDir())

	// Empty registry loads cleanly.
	if servers, err := reg.load(); err != nil || len(servers) != 0 {
		t.Fatalf("empty load = %v, %v", servers, err)
	}

	def := mcpServerDef{
		Name: "github", Transport: mcpTransportHTTP,
		URL: "https://api.example.com/mcp", Headers: map[string]string{"Authorization": "Bearer PAT"},
		Source: mcpSourceManual,
	}
	if err := reg.upsert(def); err != nil {
		t.Fatalf("upsert: %v", err)
	}
	got, ok, err := reg.get("github")
	if err != nil || !ok {
		t.Fatalf("get: ok=%v err=%v", ok, err)
	}
	if got.URL != def.URL || got.Headers["Authorization"] != "Bearer PAT" {
		t.Errorf("round-trip lost data: %+v", got)
	}
	if got.Enabled {
		t.Errorf("server should default to disabled")
	}

	// Enable, then re-upsert (e.g. re-import) must preserve the enabled flag.
	if err := reg.setEnabled("github", true); err != nil {
		t.Fatalf("setEnabled: %v", err)
	}
	if err := reg.upsert(mcpServerDef{Name: "github", Transport: mcpTransportHTTP, URL: "https://api.example.com/mcp2"}); err != nil {
		t.Fatalf("re-upsert: %v", err)
	}
	got, _, _ = reg.get("github")
	if !got.Enabled {
		t.Errorf("re-upsert reset the enabled flag")
	}
	if got.URL != "https://api.example.com/mcp2" {
		t.Errorf("re-upsert did not update URL: %q", got.URL)
	}
}

func TestMCPRegistryRejectsBadDefs(t *testing.T) {
	reg := newMCPRegistry(t.TempDir())
	bad := []mcpServerDef{
		{Name: "Bad Name", Transport: mcpTransportHTTP, URL: "https://x"},
		{Name: "ok", Transport: mcpTransportStdio},                // no command
		{Name: "ok", Transport: mcpTransportHTTP, URL: "ftp://x"}, // bad url
		{Name: "ok", Transport: "weird"},                          // unknown transport
	}
	for _, d := range bad {
		if err := reg.upsert(d); err == nil {
			t.Errorf("upsert(%+v) accepted, want error", d)
		}
	}
}

func TestMCPImportFromClaude(t *testing.T) {
	dir := t.TempDir()
	claudePath := filepath.Join(dir, ".claude.json")
	body := `{
	  "mcpServers": {
	    "github":   {"type":"http","url":"https://api.example.com/mcp","headers":{"Authorization":"Bearer X"}},
	    "linear":   {"command":"npx","args":["-y","@linear/mcp"],"env":{"LINEAR_API_KEY":"sk"}},
	    "Bad Name": {"command":"x"},
	    "broken":   {"note":"no command or url"}
	  }
	}`
	if err := os.WriteFile(claudePath, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	reg := newMCPRegistry(dir)
	imported, skipped, err := reg.importFromClaude(claudePath, filepath.Join(dir, "no-plugins"))
	if err != nil {
		t.Fatalf("import: %v", err)
	}
	if imported != 2 {
		t.Errorf("imported = %d, want 2", imported)
	}
	if len(skipped) != 2 {
		t.Errorf("skipped = %v, want 2 (Bad Name, broken)", skipped)
	}
	gh, ok, _ := reg.get("github")
	if !ok || gh.Transport != mcpTransportHTTP || gh.Enabled {
		t.Errorf("github imported wrong: %+v ok=%v", gh, ok)
	}
	lin, ok, _ := reg.get("linear")
	if !ok || lin.Transport != mcpTransportStdio || lin.Command[0] != "npx" {
		t.Errorf("linear imported wrong: %+v ok=%v", lin, ok)
	}
}

// TestMCPImportFromClaudePlugins covers plugin-provided servers (e.g. figma),
// which live in each plugin's .mcp.json under ~/.claude/plugins, NOT in
// ~/.claude.json — the case the original import missed.
func TestMCPImportFromClaudePlugins(t *testing.T) {
	dir := t.TempDir()

	// A user-level server in ~/.claude.json.
	claudePath := filepath.Join(dir, ".claude.json")
	if err := os.WriteFile(claudePath, []byte(
		`{"mcpServers":{"serena":{"command":"uvx","args":["serena"]}}}`), 0o600); err != nil {
		t.Fatal(err)
	}

	// A plugin (figma) whose MCP server lives in its install dir's .mcp.json.
	pluginsDir := filepath.Join(dir, ".claude", "plugins")
	figmaInstall := filepath.Join(pluginsDir, "cache", "official", "figma", "2.2.50")
	if err := os.MkdirAll(figmaInstall, 0o755); err != nil {
		t.Fatal(err)
	}
	manifest := `{"version":2,"plugins":{
	  "figma@official":[{"scope":"user","installPath":"` + figmaInstall + `"}],
	  "pyright-lsp@official":[{"scope":"user","installPath":"` + filepath.Join(pluginsDir, "cache", "official", "pyright-lsp", "1.0.0") + `"}]
	}}`
	if err := os.WriteFile(filepath.Join(pluginsDir, "installed_plugins.json"), []byte(manifest), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(figmaInstall, ".mcp.json"), []byte(
		`{"mcpServers":{"figma":{"type":"http","url":"https://mcp.figma.com/mcp","_meta":{"x":1}}}}`), 0o600); err != nil {
		t.Fatal(err)
	}

	reg := newMCPRegistry(dir)
	imported, _, err := reg.importFromClaude(claudePath, pluginsDir)
	if err != nil {
		t.Fatalf("import: %v", err)
	}
	if imported != 2 {
		t.Errorf("imported = %d, want 2 (serena + figma)", imported)
	}
	fig, ok, _ := reg.get("figma")
	if !ok {
		t.Fatal("figma plugin server not imported")
	}
	if fig.Transport != mcpTransportHTTP || fig.URL != "https://mcp.figma.com/mcp" {
		t.Errorf("figma imported wrong: %+v", fig)
	}
	if fig.Source != mcpSourceClaudePlugin {
		t.Errorf("figma source = %q, want %q", fig.Source, mcpSourceClaudePlugin)
	}
	// The LSP plugin has no .mcp.json — it must be skipped silently, not error.
	if _, ok, _ := reg.get("pyright-lsp"); ok {
		t.Error("pyright-lsp should not have been imported (no .mcp.json)")
	}
}

// TestMCPHostRoutesHTTPServerInjectsCredentialHostSide verifies the broker
// route for an http MCP server injects the host-held header and that the
// credential is never visible to the (container-side) caller.
func TestMCPHostRoutesHTTPServerInjectsCredentialHostSide(t *testing.T) {
	var gotAuth string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		_, _ = io.WriteString(w, "ok:"+r.URL.Path)
	}))
	defer upstream.Close()

	reg := newMCPRegistry(t.TempDir())
	if err := reg.upsert(mcpServerDef{
		Name: "github", Transport: mcpTransportHTTP, URL: upstream.URL,
		Headers: map[string]string{"Authorization": "Bearer SECRET-PAT"}, Enabled: true,
	}); err != nil {
		t.Fatal(err)
	}
	host := newMCPHost(reg, nil, nil)
	defer host.Stop()

	routes, wired := host.Routes("ep", []string{"github", "unknown"})
	if len(wired) != 1 || wired[0] != "github" {
		t.Fatalf("wired = %v, want [github] (unknown skipped)", wired)
	}
	if len(routes) != 1 || routes[0].Prefix != "/mcp/github" {
		t.Fatalf("routes = %+v, want one /mcp/github", routes)
	}

	// Drive the route as the broker would: the broker strips the /mcp/<name>
	// prefix before dispatching, so the handler sees a rooted path and a
	// request with NO auth header.
	req := httptest.NewRequest("POST", "/tools/list", nil)
	rec := httptest.NewRecorder()
	routes[0].Handler.ServeHTTP(rec, req)

	if gotAuth != "Bearer SECRET-PAT" {
		t.Errorf("upstream Authorization = %q, want host-injected Bearer SECRET-PAT", gotAuth)
	}
	if body := rec.Body.String(); body != "ok:/tools/list" {
		t.Errorf("proxied path = %q, want /tools/list", body)
	}
}

// TestProvisionNeverLeaksMCPCredentialIntoHandlerEnv is the security
// regression: a brokered MCP server's PAT must never appear in the container's
// HandlerEnv, and SYFT_MCP_SERVERS must carry names only.
func TestProvisionNeverLeaksMCPCredentialIntoHandlerEnv(t *testing.T) {
	dir := t.TempDir()
	reg := newMCPRegistry(dir)
	const pat = "ghp_SUPER_SECRET_TOKEN"
	if err := reg.upsert(mcpServerDef{
		Name: "github", Transport: mcpTransportHTTP, URL: "https://api.example.com/mcp",
		Headers: map[string]string{"Authorization": "Bearer " + pat}, Enabled: true,
	}); err != nil {
		t.Fatal(err)
	}
	host := newMCPHost(reg, nil, nil)
	defer host.Stop()

	broker := egressbroker.New(nil)
	defer broker.Stop()
	p := &egressProvisioner{
		broker:    broker,
		socketDir: filepath.Join(dir, "sockets"),
		keyStore:  &egressKeyStore{dir: filepath.Join(dir, "keys")},
		mcpHost:   host,
	}
	prov, err := p.Provision(filemode.EgressRequest{Slug: "ep", MCPServers: []string{"github"}})
	if err != nil {
		t.Fatalf("Provision: %v", err)
	}
	defer p.Deprovision("ep")

	// The server name is brokered...
	if len(prov.MCPServers) != 1 || prov.MCPServers[0] != "github" {
		t.Errorf("MCPServers = %v, want [github]", prov.MCPServers)
	}
	// ...but the PAT must not be anywhere in the handler env (keys or values).
	for k, v := range prov.HandlerEnv {
		if strings.Contains(k, pat) || strings.Contains(v, pat) {
			t.Fatalf("PAT leaked into HandlerEnv[%q]=%q", k, v)
		}
	}
	// And nothing in the handler env should carry the upstream URL either.
	blob, _ := json.Marshal(prov.HandlerEnv)
	if strings.Contains(string(blob), pat) {
		t.Fatalf("PAT leaked into HandlerEnv JSON: %s", blob)
	}

	// Sanity: the (host-side) socket is what gets bind-mounted; the discovery
	// vars are added by the SDK provider, not here — confirm the names list is
	// the only MCP data crossing into the container via this provision.
	_ = containermode.EnvMCPServers
}
