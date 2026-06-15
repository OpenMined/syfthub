package egressbroker

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// RoutingSource picks a credential by request path so a single per-endpoint
// socket can serve both runner shapes without the host needing to know which
// runner an endpoint is: Anthropic-native paths (/v1/messages — claude) use
// Anthropic; everything else (/chat/completions — basic-agent) uses OpenAI.
type RoutingSource struct {
	Anthropic CredentialSource // claude OAuth (shared host credentials.json)
	OpenAI    CredentialSource // per-endpoint host API key
}

// Resolve routes by path. A nil branch means "not configured" for that shape.
func (rs RoutingSource) Resolve(r *http.Request) (Credential, error) {
	if r != nil && isAnthropicNative(r.URL.Path) {
		if rs.Anthropic == nil {
			return Credential{}, ErrNoCredential
		}
		return rs.Anthropic.Resolve(r)
	}
	if rs.OpenAI == nil {
		return Credential{}, ErrNoCredential
	}
	return rs.OpenAI.Resolve(r)
}

func isAnthropicNative(path string) bool {
	return strings.Contains(path, "/v1/messages") || strings.Contains(path, "/v1/complete")
}

// StaticHeaderSource injects fixed auth headers and forwards to a fixed
// upstream, regardless of the request. It brokers an HTTP upstream whose
// credentials are constant and host-held — e.g. an HTTP MCP server reached
// with a PAT (plus, for some servers, a tenant/org header). The header values
// never enter the container; the container sends an unauthenticated request to
// the relay and this swaps in the secrets.
type StaticHeaderSource struct {
	Upstream string            // scheme+host(+base path); request path is appended
	Headers  map[string]string // e.g. {"Authorization": "Bearer <pat>"}; nil/empty ⇒ no auth injected
}

// Resolve returns the fixed credential. An empty Upstream means "not
// configured" (ErrNoCredential), surfaced to the caller as a 502.
func (s StaticHeaderSource) Resolve(_ *http.Request) (Credential, error) {
	if s.Upstream == "" {
		return Credential{}, ErrNoCredential
	}
	return Credential{Upstream: s.Upstream, Headers: s.Headers}, nil
}

// StaticKeySource brokers an OpenAI-compatible agent (e.g. basic-agent). The
// real key is read live via keyFn (so a host-store update takes effect without
// a restart), and the upstream is detected from the key prefix — mirroring the
// runner's _detect_backend so the brokered provider matches what the runner
// would have chosen with the real key.
type StaticKeySource struct {
	keyFn func() (string, error)
}

// NewStaticKeySource builds a source whose key is produced by keyFn on each
// request. keyFn returning "" (or ErrNoCredential) means "not configured".
func NewStaticKeySource(keyFn func() (string, error)) *StaticKeySource {
	return &StaticKeySource{keyFn: keyFn}
}

// Resolve reads the real key and maps it to an upstream + Bearer auth. The
// upstream bases include the provider's version prefix because basic-agent
// appends "/chat/completions" to its base URL (which we point at the broker).
func (s *StaticKeySource) Resolve(_ *http.Request) (Credential, error) {
	key, err := s.keyFn()
	if err != nil {
		return Credential{}, err
	}
	key = strings.TrimSpace(key)
	if key == "" {
		return Credential{}, ErrNoCredential
	}
	return Credential{
		Upstream: detectUpstream(key),
		Headers:  map[string]string{"Authorization": "Bearer " + key},
	}, nil
}

// keyPrefixes is the key-prefix → provider taxonomy. Both detectUpstream and
// RedactKey iterate it, so the upstream the broker forwards to and the sentinel
// prefix it hands the runner stay consistent. The runner's own prefix sniffing
// (basic-agent/runner.py:_detect_backend) only uses the prefix to pick a model
// default; its upstream choice is dead under brokering, since the broker
// overrides the base URL to the relay. So the runner's table need not match
// this one — only the redacted sentinel prefix must line up with what the
// runner expects. Anthropic is reached via its OpenAI-compatible endpoint, so
// every upstream is an OpenAI-shaped base.
var keyPrefixes = []struct {
	Prefix   string
	Upstream string
}{
	{"sk-ant-", "https://api.anthropic.com/v1"},
	{"sk-or-", "https://openrouter.ai/api/v1"},
}

// defaultUpstream is where keys with no recognized provider prefix go.
const defaultUpstream = "https://api.openai.com/v1"

func detectUpstream(key string) string {
	for _, p := range keyPrefixes {
		if strings.HasPrefix(key, p.Prefix) {
			return p.Upstream
		}
	}
	return defaultUpstream
}

// RedactKey keeps the provider prefix of a real key (so the runner's
// prefix-based provider detection picks the same provider the broker forwards
// to) while removing the secret body. The result is the sentinel credential
// the container carries.
func RedactKey(real string) string {
	for _, p := range keyPrefixes {
		if strings.HasPrefix(real, p.Prefix) {
			return p.Prefix + "redacted"
		}
	}
	if strings.HasPrefix(real, "sk-") {
		return "sk-redacted"
	}
	return "redacted"
}

// ClaudeOAuthSource brokers the claude-agent. It serves the host's
// subscription OAuth token from ~/.claude/.credentials.json, so a token
// refreshed by the host's own `claude` is picked up immediately: the file is
// stat'ed per request but re-read and re-parsed only when its mtime/size
// changes (Resolve sits on the per-request broker hot path). The token is
// injected as a Bearer; claude (run with --bare) sends a sentinel
// Authorization header that this replaces. The credentials file is never
// mounted into the container.
type ClaudeOAuthSource struct {
	path  string
	nowMS func() int64 // injectable clock for tests

	mu        sync.Mutex
	cached    claudeCreds
	cachedTag fileTag
	hasCache  bool
}

// fileTag identifies one on-disk version of the credentials file.
type fileTag struct {
	modTime time.Time
	size    int64
}

// NewClaudeOAuthSource reads the OAuth credential from path
// (e.g. ~/.claude/.credentials.json).
func NewClaudeOAuthSource(path string) *ClaudeOAuthSource {
	return &ClaudeOAuthSource{path: path, nowMS: func() int64 { return time.Now().UnixMilli() }}
}

// claudeCreds matches the subset of ~/.claude/.credentials.json we use.
type claudeCreds struct {
	ClaudeAiOauth struct {
		AccessToken string `json:"accessToken"`
		ExpiresAt   int64  `json:"expiresAt"` // epoch milliseconds
	} `json:"claudeAiOauth"`
}

// Resolve reads the access token, checks expiry, and returns an Anthropic
// upstream + Bearer. claude appends /v1/messages itself, so the upstream has no
// path prefix. Anthropic's OAuth-specific request headers (anthropic-version,
// anthropic-beta) are emitted by claude and preserved by the proxy untouched.
func (s *ClaudeOAuthSource) Resolve(_ *http.Request) (Credential, error) {
	cj, err := s.load()
	if err != nil {
		return Credential{}, err
	}
	tok := strings.TrimSpace(cj.ClaudeAiOauth.AccessToken)
	if tok == "" {
		return Credential{}, ErrNoCredential
	}
	if cj.ClaudeAiOauth.ExpiresAt > 0 && s.nowMS() >= cj.ClaudeAiOauth.ExpiresAt {
		return Credential{}, ErrCredentialExpired
	}
	return Credential{
		Upstream: "https://api.anthropic.com",
		Headers:  map[string]string{"Authorization": "Bearer " + tok},
	}, nil
}

// load returns the parsed credentials, re-reading the file only when its
// mtime/size differs from the cached parse.
func (s *ClaudeOAuthSource) load() (claudeCreds, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	info, err := os.Stat(s.path)
	if err != nil {
		s.hasCache = false
		if os.IsNotExist(err) {
			return claudeCreds{}, ErrNoCredential
		}
		return claudeCreds{}, fmt.Errorf("egressbroker: stat claude credentials %q: %w", s.path, err)
	}
	tag := fileTag{modTime: info.ModTime(), size: info.Size()}
	if s.hasCache && tag == s.cachedTag {
		return s.cached, nil
	}

	data, err := os.ReadFile(s.path)
	if err != nil {
		s.hasCache = false
		if os.IsNotExist(err) {
			return claudeCreds{}, ErrNoCredential
		}
		return claudeCreds{}, fmt.Errorf("egressbroker: read claude credentials %q: %w", s.path, err)
	}
	var cj claudeCreds
	if err := json.Unmarshal(data, &cj); err != nil {
		s.hasCache = false
		return claudeCreds{}, fmt.Errorf("egressbroker: parse claude credentials: %w", err)
	}
	s.cached, s.cachedTag, s.hasCache = cj, tag, true
	return cj, nil
}
