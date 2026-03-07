package handlers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// OAuth2Handler handles type=oauth2 steps.
// Implements the full OAuth 2.0 Authorization Code flow.
type OAuth2Handler struct{}

func (h *OAuth2Handler) Validate(step *nodeops.SetupStep) error {
	if step.OAuth2 == nil {
		return fmt.Errorf("oauth2 config is required for type 'oauth2'")
	}
	if step.OAuth2.AuthURL == "" {
		return fmt.Errorf("oauth2.auth_url is required")
	}
	if step.OAuth2.TokenURL == "" {
		return fmt.Errorf("oauth2.token_url is required")
	}
	return nil
}

func (h *OAuth2Handler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	cfg := step.OAuth2

	// Step 1: Resolve client credentials
	clientID, err := resolveClientCredential(cfg.ClientID, cfg.ClientIDEnv, "Client ID", step.Name, ctx)
	if err != nil {
		return nil, err
	}
	clientSecret, err := resolveClientCredential(cfg.ClientSecret, cfg.ClientSecretEnv, "Client Secret", step.Name, ctx)
	if err != nil {
		return nil, err
	}

	// Step 2: Start callback server
	listener, err := startCallbackListener(cfg.CallbackPort)
	if err != nil {
		return nil, fmt.Errorf("failed to start callback server: %w", err)
	}
	defer listener.Close()

	port := listener.Addr().(*net.TCPAddr).Port
	redirectURI := fmt.Sprintf("http://localhost:%d/callback", port)

	// Generate state for CSRF protection
	stateBytes := make([]byte, 16)
	if _, err := rand.Read(stateBytes); err != nil {
		return nil, fmt.Errorf("failed to generate state: %w", err)
	}
	state := hex.EncodeToString(stateBytes)

	// Step 3: Build authorization URL
	authURL, err := buildAuthURL(cfg, clientID, redirectURI, state)
	if err != nil {
		return nil, fmt.Errorf("failed to build auth URL: %w", err)
	}

	// Open browser
	ctx.IO.Status(fmt.Sprintf("Opening browser for authorization..."))
	if err := ctx.IO.OpenBrowser(authURL); err != nil {
		ctx.IO.Status(fmt.Sprintf("Please open this URL in your browser:\n  %s", authURL))
	}
	ctx.IO.Status("Waiting for authorization callback...")

	// Step 4: Wait for callback
	callbackCh := make(chan callbackResult, 1)
	server := &http.Server{
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/callback" {
				http.NotFound(w, r)
				return
			}

			code := r.URL.Query().Get("code")
			cbState := r.URL.Query().Get("state")
			cbError := r.URL.Query().Get("error")

			if cbError != "" {
				w.Header().Set("Content-Type", "text/html")
				fmt.Fprintf(w, "<html><body><h2>Authorization Failed</h2><p>%s</p><p>You can close this window.</p></body></html>", cbError)
				callbackCh <- callbackResult{err: fmt.Errorf("authorization denied: %s", cbError)}
				return
			}

			w.Header().Set("Content-Type", "text/html")
			fmt.Fprintf(w, "<html><body><h2>Authorization Successful</h2><p>You can close this window and return to the terminal.</p></body></html>")
			callbackCh <- callbackResult{code: code, state: cbState}
		}),
	}

	go server.Serve(listener)

	var cb callbackResult
	select {
	case cb = <-callbackCh:
	case <-time.After(5 * time.Minute):
		server.Shutdown(context.Background())
		return nil, fmt.Errorf("authorization timed out after 5 minutes")
	}

	server.Shutdown(context.Background())

	if cb.err != nil {
		return nil, cb.err
	}

	// Validate state
	if cb.state != state {
		return nil, fmt.Errorf("state mismatch: possible CSRF attack")
	}

	// Step 5: Token exchange
	tokenResp, err := exchangeToken(cfg.TokenURL, cb.code, redirectURI, clientID, clientSecret)
	if err != nil {
		return nil, fmt.Errorf("token exchange failed: %w", err)
	}

	// Step 6: Build result
	result := &setupflow.StepResult{
		Response: tokenResp,
		Metadata: make(map[string]string),
	}

	// Extract access_token as primary value
	var tokenData map[string]any
	if err := json.Unmarshal(tokenResp, &tokenData); err == nil {
		if at, ok := tokenData["access_token"].(string); ok {
			result.Value = at
		}
		if ei, ok := tokenData["expires_in"].(float64); ok {
			result.Metadata["expires_in"] = fmt.Sprintf("%d", int64(ei))
		}
	}

	return result, nil
}

type callbackResult struct {
	code  string
	state string
	err   error
}

func resolveClientCredential(direct, envKey, label, stepName string, ctx *setupflow.SetupContext) (string, error) {
	if direct != "" {
		return direct, nil
	}
	if envKey != "" {
		// Try .env file first
		envPath := ctx.EndpointDir + "/.env"
		envVars, _ := nodeops.ReadEnvFile(envPath)
		for _, v := range envVars {
			if v.Key == envKey {
				return v.Value, nil
			}
		}
		// Try system env
		if val := os.Getenv(envKey); val != "" {
			return val, nil
		}
	}

	// Prompt user
	value, err := ctx.IO.Prompt(fmt.Sprintf("Enter OAuth %s for %s:", label, stepName), setupflow.PromptOpts{
		Secret: strings.Contains(strings.ToLower(label), "secret"),
	})
	if err != nil {
		return "", err
	}
	if value == "" {
		return "", fmt.Errorf("OAuth %s is required", label)
	}
	return value, nil
}

func startCallbackListener(port int) (net.Listener, error) {
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	return net.Listen("tcp", addr)
}

func buildAuthURL(cfg *nodeops.OAuth2Config, clientID, redirectURI, state string) (string, error) {
	u, err := url.Parse(cfg.AuthURL)
	if err != nil {
		return "", err
	}

	q := u.Query()
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("response_type", "code")
	q.Set("scope", strings.Join(cfg.Scopes, " "))
	q.Set("state", state)
	for k, v := range cfg.ExtraParams {
		q.Set(k, v)
	}
	u.RawQuery = q.Encode()

	return u.String(), nil
}

func exchangeToken(tokenURL, code, redirectURI, clientID, clientSecret string) (json.RawMessage, error) {
	data := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {code},
		"redirect_uri":  {redirectURI},
		"client_id":     {clientID},
		"client_secret": {clientSecret},
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.PostForm(tokenURL, data)
	if err != nil {
		return nil, fmt.Errorf("token request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1MB limit
	if err != nil {
		return nil, fmt.Errorf("failed to read token response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("token endpoint returned %d: %s", resp.StatusCode, string(body))
	}

	return json.RawMessage(body), nil
}
