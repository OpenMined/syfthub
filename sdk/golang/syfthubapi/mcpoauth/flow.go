package mcpoauth

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"net/http"

	"golang.org/x/oauth2"
)

// Flow is the PKCE authorization-code flow for one MCP server, carrying the
// RFC 8707 resource indicator that binds the token to that server.
type Flow struct {
	cfg      *oauth2.Config
	resource string
}

// NewFlow builds the flow from discovery + a (registered) client + the redirect
// URL the authorization server will send the code back to.
func NewFlow(d *Discovered, creds *ClientCreds, redirectURL string) *Flow {
	return &Flow{
		cfg: &oauth2.Config{
			ClientID:     creds.ClientID,
			ClientSecret: creds.ClientSecret,
			Endpoint:     oauth2.Endpoint{AuthURL: d.AuthEndpoint, TokenURL: d.TokenEndpoint},
			RedirectURL:  redirectURL,
			Scopes:       d.Scopes,
		},
		resource: d.Resource,
	}
}

// AuthCodeURL builds the URL to open in the browser, with the PKCE challenge and
// the resource indicator.
func (f *Flow) AuthCodeURL(state, verifier string) string {
	return f.cfg.AuthCodeURL(state,
		oauth2.S256ChallengeOption(verifier),
		oauth2.SetAuthURLParam("resource", f.resource),
	)
}

// Exchange swaps the authorization code for a token, proving the PKCE verifier
// and re-sending the resource indicator.
func (f *Flow) Exchange(ctx context.Context, code, verifier string) (*oauth2.Token, error) {
	return f.cfg.Exchange(ctx, code,
		oauth2.VerifierOption(verifier),
		oauth2.SetAuthURLParam("resource", f.resource),
	)
}

// Fetch directs the user to authURL (e.g. opens a browser), waits for the
// authorization server to redirect back to the flow's redirect URL, validates
// the returned state matches, and returns the authorization code. Supplied by
// the host (real browser + loopback server) or a test (simulated AS).
type Fetch func(ctx context.Context, authURL, state string) (code string, err error)

// ConnectParams configures one interactive Connect.
type ConnectParams struct {
	Server      string // registry name (store key)
	ServerURL   string // MCP endpoint URL
	RedirectURL string // loopback redirect the AS calls back
	ClientName  string // shown to the user at the AS consent screen
	Fetch       Fetch
	Store       TokenStore
	Client      *http.Client
}

// Connect runs the full interactive OAuth flow for an MCP server and persists
// the result. On success the server is authorized and Handler will serve its
// token. Returns ErrAuthNotRequired if the server needs no OAuth.
func Connect(ctx context.Context, p ConnectParams) (*Record, error) {
	d, err := Discover(ctx, p.ServerURL, p.Client)
	if err != nil {
		return nil, err
	}

	// Reuse a prior client registration for the same authorization server when
	// available, so re-connecting doesn't register a new client each time.
	creds := reuseClient(p.Store, p.Server, d.AuthServer)
	if creds == nil {
		creds, err = Register(ctx, d, p.RedirectURL, p.ClientName, p.Client)
		if err != nil {
			return nil, err
		}
	}

	flow := NewFlow(d, creds, p.RedirectURL)
	verifier := oauth2.GenerateVerifier()
	state, err := randomState()
	if err != nil {
		return nil, err
	}
	code, err := p.Fetch(ctx, flow.AuthCodeURL(state, verifier), state)
	if err != nil {
		return nil, err
	}
	tok, err := flow.Exchange(ctx, code, verifier)
	if err != nil {
		return nil, fmt.Errorf("mcpoauth: token exchange: %w", err)
	}

	rec := &Record{
		AuthServer:    d.AuthServer,
		AuthEndpoint:  d.AuthEndpoint,
		TokenEndpoint: d.TokenEndpoint,
		ClientID:      creds.ClientID,
		ClientSecret:  creds.ClientSecret,
		Scopes:        d.Scopes,
		Resource:      d.Resource,
		Token:         tok,
	}
	if err := p.Store.Save(p.Server, rec); err != nil {
		return nil, fmt.Errorf("mcpoauth: persist token: %w", err)
	}
	return rec, nil
}

// reuseClient returns the client registration from a prior record for the same
// authorization server, or nil to force a fresh registration.
func reuseClient(store TokenStore, server, authServer string) *ClientCreds {
	rec, err := store.Load(server)
	if err != nil || rec == nil || rec.ClientID == "" || rec.AuthServer != authServer {
		return nil
	}
	return &ClientCreds{ClientID: rec.ClientID, ClientSecret: rec.ClientSecret}
}

func randomState() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
