// Package mcpoauth implements the client side of the MCP authorization spec
// (OAuth 2.1) for brokering remote MCP servers that require OAuth — e.g. the
// figma MCP server. It performs discovery (RFC 9728 protected-resource metadata
// + RFC 8414 authorization-server metadata), Dynamic Client Registration
// (RFC 7591), and the PKCE authorization-code flow (RFC 7636) with a resource
// indicator (RFC 8707), then persists the resulting tokens and serves them
// (auto-refreshing) as an auth.OAuthHandler the go-sdk MCP client uses.
//
// The package is pure logic: the interactive "open a browser and capture the
// redirect" step is injected as a Fetch callback, so the desktop supplies the
// real browser/loopback glue while tests supply a simulated authorization
// server. Tokens never leave the host.
package mcpoauth

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/modelcontextprotocol/go-sdk/oauthex"
)

// ErrAuthNotRequired is returned by Discover when the server answers an
// unauthenticated request without a 401 — it needs no OAuth.
var ErrAuthNotRequired = errors.New("mcpoauth: server does not require authorization")

// ErrRegistrationForbidden is returned (wrapped) by Register when the
// authorization server rejects dynamic client registration as unauthorized —
// e.g. figma, which gates DCR to known clients. Callers detect it with
// errors.Is and direct the user to an out-of-band authorization path.
var ErrRegistrationForbidden = errors.New("mcpoauth: authorization server refused dynamic client registration")

// orDefault returns c, or the package's default HTTP client when c is nil.
func orDefault(c *http.Client) *http.Client {
	if c == nil {
		return &http.Client{Timeout: 30 * time.Second}
	}
	return c
}

// Discovered is the OAuth configuration discovered for an MCP server.
type Discovered struct {
	Resource             string   // canonical resource identifier (RFC 8707)
	AuthServer           string   // authorization server issuer
	AuthEndpoint         string   // authorization endpoint
	TokenEndpoint        string   // token endpoint
	RegistrationEndpoint string   // DCR endpoint ("" if unsupported)
	Scopes               []string // requested scopes
}

const initializeProbe = `{"jsonrpc":"2.0","id":1,"method":"initialize",` +
	`"params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"syfthub","version":"0"}}}`

// Discover probes the MCP server and resolves its OAuth endpoints. It sends an
// MCP initialize; a 401 carries the protected-resource metadata pointer (or we
// fall back to the well-known path), from which we resolve the authorization
// server. Any non-401 response means no OAuth is required (ErrAuthNotRequired).
func Discover(ctx context.Context, serverURL string, c *http.Client) (*Discovered, error) {
	c = orDefault(c)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, serverURL, bytes.NewReader([]byte(initializeProbe)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	resp, err := c.Do(req)
	if err != nil {
		return nil, fmt.Errorf("mcpoauth: probe %s: %w", serverURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		return nil, ErrAuthNotRequired
	}

	metadataURL := resourceMetadataURL(resp.Header.Values("WWW-Authenticate"), serverURL)
	prm, err := oauthex.GetProtectedResourceMetadata(ctx, metadataURL, serverURL, c)
	if err != nil {
		return nil, fmt.Errorf("mcpoauth: protected resource metadata: %w", err)
	}
	if len(prm.AuthorizationServers) == 0 {
		return nil, fmt.Errorf("mcpoauth: %s lists no authorization servers", metadataURL)
	}
	issuer := prm.AuthorizationServers[0]
	asm, err := auth.GetAuthServerMetadata(ctx, issuer, c)
	if err != nil {
		return nil, fmt.Errorf("mcpoauth: authorization server metadata for %s: %w", issuer, err)
	}
	if asm.AuthorizationEndpoint == "" || asm.TokenEndpoint == "" {
		return nil, fmt.Errorf("mcpoauth: %s is missing authorization/token endpoints", issuer)
	}

	scopes := prm.ScopesSupported
	if len(scopes) == 0 {
		scopes = asm.ScopesSupported
	}
	return &Discovered{
		Resource:             prm.Resource,
		AuthServer:           issuer,
		AuthEndpoint:         asm.AuthorizationEndpoint,
		TokenEndpoint:        asm.TokenEndpoint,
		RegistrationEndpoint: asm.RegistrationEndpoint,
		Scopes:               scopes,
	}, nil
}

// resourceMetadataURL extracts the resource_metadata pointer from a Bearer
// WWW-Authenticate challenge, falling back to the well-known path at the
// server's origin when absent.
func resourceMetadataURL(headers []string, serverURL string) string {
	if challenges, err := oauthex.ParseWWWAuthenticate(headers); err == nil {
		for _, ch := range challenges {
			if strings.EqualFold(ch.Scheme, "bearer") {
				if v := ch.Params["resource_metadata"]; v != "" {
					return v
				}
			}
		}
	}
	if u, err := url.Parse(serverURL); err == nil {
		return u.Scheme + "://" + u.Host + "/.well-known/oauth-protected-resource"
	}
	return serverURL
}

// ClientCreds is an OAuth client registration result.
type ClientCreds struct {
	ClientID     string
	ClientSecret string // empty for public (PKCE-only) clients
}

// Register performs Dynamic Client Registration against the discovered AS,
// registering a public native client (PKCE, no secret) bound to redirectURI.
// Returns an error when the AS does not advertise a registration endpoint —
// the caller must then supply a pre-registered client.
func Register(ctx context.Context, d *Discovered, redirectURI, clientName string, c *http.Client) (*ClientCreds, error) {
	if d.RegistrationEndpoint == "" {
		return nil, fmt.Errorf("mcpoauth: %s does not support dynamic client registration", d.AuthServer)
	}
	c = orDefault(c)
	meta := &oauthex.ClientRegistrationMetadata{
		RedirectURIs:            []string{redirectURI},
		TokenEndpointAuthMethod: "none", // public client; PKCE secures the exchange
		GrantTypes:              []string{"authorization_code", "refresh_token"},
		ResponseTypes:           []string{"code"},
		ClientName:              clientName,
		Scope:                   strings.Join(d.Scopes, " "),
	}
	resp, err := oauthex.RegisterClient(ctx, d.RegistrationEndpoint, meta, c)
	if err != nil {
		// Classify "the AS refused us" here, where the registration step is
		// unambiguous, so callers can errors.Is instead of sniffing message text.
		msg := err.Error()
		if strings.Contains(msg, "401") || strings.Contains(msg, "403") ||
			strings.Contains(msg, "unauthorized") || strings.Contains(msg, "forbidden") {
			return nil, fmt.Errorf("%w: %v", ErrRegistrationForbidden, err)
		}
		return nil, fmt.Errorf("mcpoauth: dynamic client registration: %w", err)
	}
	return &ClientCreds{ClientID: resp.ClientID, ClientSecret: resp.ClientSecret}, nil
}
