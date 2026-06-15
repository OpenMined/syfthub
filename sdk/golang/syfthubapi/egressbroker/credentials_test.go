package egressbroker

import (
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"testing"
)

func TestRoutingSource(t *testing.T) {
	anth := fixedSource{cred: Credential{Upstream: "https://api.anthropic.com", Headers: map[string]string{"Authorization": "A"}}}
	oai := fixedSource{cred: Credential{Upstream: "https://api.openai.com/v1", Headers: map[string]string{"Authorization": "B"}}}
	rs := RoutingSource{Anthropic: anth, OpenAI: oai}

	req := func(p string) *http.Request { r, _ := http.NewRequest("POST", "http://x"+p, nil); return r }

	if c, _ := rs.Resolve(req("/v1/messages")); c.Headers["Authorization"] != "A" {
		t.Errorf("/v1/messages routed to %q, want anthropic", c.Headers["Authorization"])
	}
	if c, _ := rs.Resolve(req("/chat/completions")); c.Headers["Authorization"] != "B" {
		t.Errorf("/chat/completions routed to %q, want openai", c.Headers["Authorization"])
	}
	// Missing branch → ErrNoCredential.
	only := RoutingSource{OpenAI: oai}
	if _, err := only.Resolve(req("/v1/messages")); !errors.Is(err, ErrNoCredential) {
		t.Errorf("nil anthropic branch err = %v, want ErrNoCredential", err)
	}
}

func TestDetectUpstream(t *testing.T) {
	cases := map[string]string{
		"sk-ant-abc": "https://api.anthropic.com/v1",
		"sk-or-abc":  "https://openrouter.ai/api/v1",
		"sk-abc":     "https://api.openai.com/v1",
		"anything":   "https://api.openai.com/v1",
	}
	for key, want := range cases {
		if got := detectUpstream(key); got != want {
			t.Errorf("detectUpstream(%q) = %q, want %q", key, got, want)
		}
	}
}

func TestRedactKey(t *testing.T) {
	cases := map[string]string{
		"sk-ant-abc123": "sk-ant-redacted",
		"sk-or-abc123":  "sk-or-redacted",
		"sk-abc123":     "sk-redacted",
		"weird":         "redacted",
	}
	for in, want := range cases {
		if got := RedactKey(in); got != want {
			t.Errorf("RedactKey(%q) = %q, want %q", in, got, want)
		}
		// The redacted sentinel must route to the same upstream as the real
		// key — that is the whole point of keeping the prefix.
		if got := detectUpstream(RedactKey(in)); got != detectUpstream(in) {
			t.Errorf("RedactKey(%q) routes to %q, real key routes to %q", in, got, detectUpstream(in))
		}
	}
}

func TestStaticKeySource(t *testing.T) {
	src := NewStaticKeySource(func() (string, error) { return "  sk-ant-real  ", nil })
	cred, err := src.Resolve(nil)
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if cred.Upstream != "https://api.anthropic.com/v1" {
		t.Errorf("upstream = %q", cred.Upstream)
	}
	if cred.Headers["Authorization"] != "Bearer sk-ant-real" {
		t.Errorf("auth = %q", cred.Headers["Authorization"])
	}

	empty := NewStaticKeySource(func() (string, error) { return "", nil })
	if _, err := empty.Resolve(nil); !errors.Is(err, ErrNoCredential) {
		t.Errorf("empty key err = %v, want ErrNoCredential", err)
	}
}

func writeCreds(t *testing.T, token string, expiresAt int64) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), ".credentials.json")
	body := `{"claudeAiOauth":{"accessToken":"` + token + `","expiresAt":` + strconv.FormatInt(expiresAt, 10) + `,"refreshToken":"r","scopes":["a"]}}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write creds: %v", err)
	}
	return path
}

func TestClaudeOAuthSource(t *testing.T) {
	// Fresh token.
	src := NewClaudeOAuthSource(writeCreds(t, "tok123", 10_000))
	src.nowMS = func() int64 { return 5_000 } // before expiry
	cred, err := src.Resolve(nil)
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if cred.Upstream != "https://api.anthropic.com" {
		t.Errorf("upstream = %q, want https://api.anthropic.com (claude adds /v1/messages)", cred.Upstream)
	}
	if cred.Headers["Authorization"] != "Bearer tok123" {
		t.Errorf("auth = %q", cred.Headers["Authorization"])
	}

	// Expired.
	exp := NewClaudeOAuthSource(writeCreds(t, "tok", 1_000))
	exp.nowMS = func() int64 { return 2_000 }
	if _, err := exp.Resolve(nil); !errors.Is(err, ErrCredentialExpired) {
		t.Errorf("expired err = %v, want ErrCredentialExpired", err)
	}

	// Missing file.
	missing := NewClaudeOAuthSource(filepath.Join(t.TempDir(), "nope.json"))
	if _, err := missing.Resolve(nil); !errors.Is(err, ErrNoCredential) {
		t.Errorf("missing err = %v, want ErrNoCredential", err)
	}

	// Empty token.
	empty := NewClaudeOAuthSource(writeCreds(t, "", 10_000))
	empty.nowMS = func() int64 { return 1 }
	if _, err := empty.Resolve(nil); !errors.Is(err, ErrNoCredential) {
		t.Errorf("empty token err = %v, want ErrNoCredential", err)
	}
}
