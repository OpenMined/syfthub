package mcpoauth

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"golang.org/x/oauth2"
)

var (
	// ErrNotConnected is returned by Handler when the server has no stored token.
	ErrNotConnected = errors.New("mcpoauth: server not connected — authorize it in the host")
	// ErrReconnectRequired is returned when a stored token is unusable and
	// cannot be refreshed (refresh token missing/revoked) — the user must
	// re-run Connect. The MCP client surfaces this rather than popping a browser.
	ErrReconnectRequired = errors.New("mcpoauth: authorization expired — reconnect this server in the host")
)

// refreshBuffer refreshes a token this long before its actual expiry.
const refreshBuffer = 60 * time.Second

// Handler loads a server's stored token and returns a non-interactive
// auth.OAuthHandler for the go-sdk MCP client: it attaches the bearer and
// refreshes via the refresh token (re-sending the resource indicator),
// persisting rotated tokens. It never opens a browser; if refresh is
// impossible it returns ErrReconnectRequired so the bridge fails cleanly.
func Handler(ctx context.Context, store TokenStore, server string, c *http.Client) (auth.OAuthHandler, error) {
	rec, err := store.Load(server)
	if err != nil {
		return nil, err
	}
	if rec == nil || rec.Token == nil {
		return nil, ErrNotConnected
	}
	src := &refreshingSource{
		ctx:      ctx,
		cfg:      rec.config(),
		resource: rec.Resource,
		cur:      rec.Token,
		client:   orDefault(c),
		onChange: func(t *oauth2.Token) {
			rec.Token = t
			_ = store.Save(server, rec)
		},
	}
	return &storedHandler{ts: src}, nil
}

// NewHandler wraps any oauth2.TokenSource as a non-interactive auth.OAuthHandler
// for the go-sdk MCP client: it attaches the source's bearer and, on a 401,
// returns ErrReconnectRequired rather than opening a browser. Used for token
// sources the host obtains out-of-band (e.g. reusing Claude's MCP tokens).
func NewHandler(ts oauth2.TokenSource) auth.OAuthHandler {
	return &storedHandler{ts: ts}
}

// TokenValid reports whether a token is usable for at least refreshBuffer
// longer (non-nil, has an access token, not within the refresh window of
// expiry).
func TokenValid(t *oauth2.Token) bool { return fresh(t) }

// storedHandler implements auth.OAuthHandler over a fixed (refreshing) source.
type storedHandler struct{ ts oauth2.TokenSource }

func (h *storedHandler) TokenSource(context.Context) (oauth2.TokenSource, error) { return h.ts, nil }

func (h *storedHandler) Authorize(_ context.Context, _ *http.Request, resp *http.Response) error {
	if resp != nil && resp.Body != nil {
		resp.Body.Close()
	}
	return ErrReconnectRequired
}

var _ auth.OAuthHandler = (*storedHandler)(nil)

// refreshingSource serves the current access token, refreshing via the refresh
// token (with the resource indicator) when it is within refreshBuffer of expiry
// and persisting any rotated token. Thread-safe.
type refreshingSource struct {
	ctx      context.Context
	cfg      *oauth2.Config
	resource string
	client   *http.Client
	onChange func(*oauth2.Token)

	mu  sync.Mutex
	cur *oauth2.Token
}

func (s *refreshingSource) Token() (*oauth2.Token, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if fresh(s.cur) {
		return s.cur, nil
	}
	if s.cur == nil || s.cur.RefreshToken == "" {
		return nil, ErrReconnectRequired
	}
	tok, err := s.refresh()
	if err != nil {
		return nil, err
	}
	s.cur = tok
	if s.onChange != nil {
		s.onChange(tok)
	}
	return tok, nil
}

// fresh reports whether a token is usable for at least refreshBuffer longer.
func fresh(t *oauth2.Token) bool {
	if t == nil || t.AccessToken == "" {
		return false
	}
	if t.Expiry.IsZero() {
		return true
	}
	return time.Now().Add(refreshBuffer).Before(t.Expiry)
}

// refresh exchanges the refresh token for a new access token at the token
// endpoint, re-sending the resource indicator (RFC 8707). The refresh token is
// preserved when the server does not rotate it.
func (s *refreshingSource) refresh() (*oauth2.Token, error) {
	v := url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {s.cur.RefreshToken},
		"client_id":     {s.cfg.ClientID},
	}
	if s.cfg.ClientSecret != "" {
		v.Set("client_secret", s.cfg.ClientSecret)
	}
	if len(s.cfg.Scopes) > 0 {
		v.Set("scope", strings.Join(s.cfg.Scopes, " "))
	}
	if s.resource != "" {
		v.Set("resource", s.resource)
	}
	req, err := http.NewRequestWithContext(s.ctx, http.MethodPost, s.cfg.Endpoint.TokenURL, strings.NewReader(v.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("mcpoauth: refresh request: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		// A 4xx means the refresh token is dead — require a reconnect.
		if resp.StatusCode >= 400 && resp.StatusCode < 500 {
			return nil, ErrReconnectRequired
		}
		return nil, fmt.Errorf("mcpoauth: refresh failed: %s: %s", resp.Status, strings.TrimSpace(string(body)))
	}
	var tr struct {
		AccessToken  string `json:"access_token"`
		TokenType    string `json:"token_type"`
		RefreshToken string `json:"refresh_token"`
		ExpiresIn    int64  `json:"expires_in"`
	}
	if err := json.Unmarshal(body, &tr); err != nil {
		return nil, fmt.Errorf("mcpoauth: parse refresh response: %w", err)
	}
	if tr.AccessToken == "" {
		return nil, fmt.Errorf("mcpoauth: refresh response had no access token")
	}
	tok := &oauth2.Token{
		AccessToken:  tr.AccessToken,
		TokenType:    tr.TokenType,
		RefreshToken: tr.RefreshToken,
	}
	if tok.RefreshToken == "" {
		tok.RefreshToken = s.cur.RefreshToken // non-rotating server
	}
	if tr.ExpiresIn > 0 {
		tok.Expiry = time.Now().Add(time.Duration(tr.ExpiresIn) * time.Second)
	}
	return tok, nil
}

// Status describes a server's authorization state for the UI.
type Status string

const (
	StatusNotConnected Status = "not_connected"
	StatusConnected    Status = "connected"
	StatusExpired      Status = "expired" // access expired and no refresh token
)

// ServerStatus reports a server's stored authorization state.
func ServerStatus(store TokenStore, server string) (Status, error) {
	rec, err := store.Load(server)
	if err != nil {
		return StatusNotConnected, err
	}
	if rec == nil || rec.Token == nil || rec.Token.AccessToken == "" {
		return StatusNotConnected, nil
	}
	if !fresh(rec.Token) && rec.Token.RefreshToken == "" {
		return StatusExpired, nil
	}
	return StatusConnected, nil
}
