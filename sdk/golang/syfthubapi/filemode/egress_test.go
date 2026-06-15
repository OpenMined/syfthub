package filemode

import (
	"slices"
	"strings"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
)

func TestStripCredentialEnv(t *testing.T) {
	in := []string{
		"API_KEY=sk-ant-real",
		"ANTHROPIC_API_KEY=sk-ant-2",
		"OPENAI_API_KEY=sk-3",
		"ANTHROPIC_AUTH_TOKEN=tok",
		"SYSTEM_PROMPT=hello",
		"AGENT_MODEL=gpt-4o-mini",
	}
	got := stripCredentialEnv(in, nil)
	want := []string{"SYSTEM_PROMPT=hello", "AGENT_MODEL=gpt-4o-mini"}
	if !slices.Equal(got, want) {
		t.Errorf("stripCredentialEnv = %v, want %v", got, want)
	}

	// Any key the provision injects as a sentinel is stripped too, even when
	// it is not in the static credential list — the host owns the credential
	// vocabulary.
	got = stripCredentialEnv([]string{"GEMINI_API_KEY=real", "SYSTEM_PROMPT=hello"},
		map[string]string{"GEMINI_API_KEY": "sentinel"})
	if !slices.Equal(got, []string{"SYSTEM_PROMPT=hello"}) {
		t.Errorf("sentinel-keyed strip = %v, want real GEMINI_API_KEY dropped", got)
	}
}

// envValue returns the value for KEY in a KEY=value slice, or "" if absent.
func envValue(env []string, key string) (string, bool) {
	for _, kv := range env {
		if k, v, ok := strings.Cut(kv, "="); ok && k == key {
			return v, true
		}
	}
	return "", false
}

func TestBrokeredEnvAddsMCPVarsOnlyWhenServersBrokered(t *testing.T) {
	// No MCP servers brokered → no MCP discovery vars.
	hv, relay := brokeredEnv([]string{"API_KEY=sk-real", "SYSTEM_PROMPT=hi"}, &EgressProvision{
		HandlerEnv: map[string]string{"ANTHROPIC_AUTH_TOKEN": "sentinel"},
	})
	if _, ok := envValue(hv, containermode.EnvMCPBaseURL); ok {
		t.Errorf("MCP base URL set with no servers: %v", hv)
	}
	if _, ok := envValue(hv, containermode.EnvMCPServers); ok {
		t.Errorf("MCP servers set with no servers: %v", hv)
	}
	// Relay vars are always present and never in the handler-visible set.
	if _, ok := envValue(relay, containermode.EnvEgressSock); !ok {
		t.Errorf("relay missing egress sock: %v", relay)
	}

	// MCP servers brokered → discovery vars appear, handler-visible.
	hv2, _ := brokeredEnv([]string{"API_KEY=sk-real"}, &EgressProvision{
		HandlerEnv: map[string]string{"ANTHROPIC_AUTH_TOKEN": "sentinel"},
		MCPServers: []string{"github", "linear"},
	})
	base, ok := envValue(hv2, containermode.EnvMCPBaseURL)
	if !ok || base != "http://127.0.0.1:"+containermode.EgressLoopbackPort+containermode.EgressMCPPath {
		t.Errorf("MCP base URL = %q (ok=%v)", base, ok)
	}
	if servers, _ := envValue(hv2, containermode.EnvMCPServers); servers != "github,linear" {
		t.Errorf("MCP servers = %q, want github,linear", servers)
	}
	// The real credential is still stripped even with MCP enabled.
	if _, ok := envValue(hv2, "API_KEY"); ok {
		t.Errorf("real API_KEY leaked into handler env: %v", hv2)
	}
}

func TestIsCredentialMount(t *testing.T) {
	cases := []struct {
		source, target string
		want           bool
	}{
		// Credential named on the target.
		{"/data/x", "/home/runner/.claude/.credentials.json", true},
		{"/data/x", "/home/runner/work/credentials.json", true},
		{"/data/work", "/home/runner/work", false},
		{"/data/gh", "/home/runner/.config/gh", false},
		// Credential smuggled in via the host source under an innocent target.
		{"/Users/me/.aws/credentials", "/home/runner/volumes/creds", true},
		{"/Users/me/.ssh/id_rsa", "/home/runner/volumes/k", true},
		{"/Users/me/.netrc", "/home/runner/volumes/n", true},
		{"/Users/me/.claude/.credentials.json", "/home/runner/volumes/c", true},
		// Ordinary data mounts pass.
		{"/Users/me/datasets/papers", "/home/runner/volumes/papers", false},
		{"/Users/me/project/config", "/home/runner/volumes/config", false},
	}
	for _, c := range cases {
		if got := isCredentialMount(c.source, c.target); got != c.want {
			t.Errorf("isCredentialMount(%q, %q) = %v, want %v", c.source, c.target, got, c.want)
		}
	}
}
