package syfthub

import (
	"context"
	"fmt"
	"net/url"
	"sync"
)

// AuthResource handles authentication operations.
//
// Example usage:
//
//	// Register a new user
//	user, err := client.Auth.Register(ctx, &RegisterRequest{
//	    Username: "john",
//	    Email:    "john@example.com",
//	    Password: "secret123",
//	    FullName: "John Doe",
//	})
//
//	// Login
//	user, err := client.Auth.Login(ctx, "john", "secret123")
//
//	// Get current user
//	me, err := client.Auth.Me(ctx)
//
//	// Change password
//	err = client.Auth.ChangePassword(ctx, "secret123", "newsecret456")
//
//	// Logout
//	err = client.Auth.Logout(ctx)
//
// maxTokenFetchConcurrency limits parallel token-fetch goroutines in
// GetSatelliteTokens and GetGuestSatelliteTokens.
const maxTokenFetchConcurrency = 10

type AuthResource struct {
	http *httpClient
}

// newAuthResource creates a new AuthResource.
func newAuthResource(http *httpClient) *AuthResource {
	return &AuthResource{http: http}
}

// Register registers a new user.
//
// If an accounting service URL is configured, the backend handles accounting
// integration using a "try-create-first" approach:
//
// Accounting Password Behavior:
//   - Not provided: A secure password is auto-generated and a new
//     accounting account is created.
//   - Provided (new user): The account is created with your chosen password.
//   - Provided (existing user): Your password is validated and accounts
//     are linked.
//
// Errors:
//   - ValidationError: If registration data is invalid
//   - UserAlreadyExistsError: If username or email already exists in SyftHub
//   - AccountingAccountExistsError: If email exists in accounting service
//     and no accounting_password was provided
//   - InvalidAccountingPasswordError: If the provided accounting password
//     doesn't match an existing accounting account
//   - AccountingServiceUnavailableError: If the accounting service is unreachable
func (a *AuthResource) Register(ctx context.Context, req *RegisterRequest) (*RegisterResult, error) {
	payload := map[string]interface{}{
		"username":  req.Username,
		"email":     req.Email,
		"password":  req.Password,
		"full_name": req.FullName,
	}
	if req.AccountingPassword != nil {
		payload["accounting_password"] = *req.AccountingPassword
	}

	var response struct {
		User                      User   `json:"user"`
		AccessToken               string `json:"access_token"`
		RefreshToken              string `json:"refresh_token"`
		TokenType                 string `json:"token_type"`
		RequiresEmailVerification bool   `json:"requires_email_verification"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/register", payload, &response, WithoutAuth())
	if err != nil {
		return nil, err
	}

	// Store tokens if present (not withheld for email verification)
	a.storeAuthTokens(response.AccessToken, response.RefreshToken, response.TokenType)

	return &RegisterResult{
		User:                      response.User,
		RequiresEmailVerification: response.RequiresEmailVerification,
	}, nil
}

// Login logs in with username and password.
//
// Errors:
//   - AuthenticationError: If credentials are invalid
func (a *AuthResource) Login(ctx context.Context, username, password string) (*User, error) {
	// OAuth2 password flow uses form data
	formData := url.Values{}
	formData.Set("username", username)
	formData.Set("password", password)

	var response struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
		TokenType    string `json:"token_type"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/login", nil, &response, WithoutAuth(), WithFormData(formData))
	if err != nil {
		return nil, err
	}

	// Store tokens
	a.storeAuthTokens(response.AccessToken, response.RefreshToken, response.TokenType)

	// Fetch and return user info
	return a.Me(ctx)
}

// Logout logs out and invalidates tokens.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (a *AuthResource) Logout(ctx context.Context) error {
	err := a.http.Post(ctx, "/api/v1/auth/logout", nil, nil)
	if err != nil {
		return err
	}
	a.http.ClearTokens()
	return nil
}

// Refresh manually refreshes the access token.
//
// This is usually handled automatically on 401 responses,
// but can be called explicitly if needed.
//
// Errors:
//   - AuthenticationError: If refresh token is invalid/expired
func (a *AuthResource) Refresh(ctx context.Context) error {
	tokens := a.http.GetTokens()
	if tokens == nil {
		return newAuthenticationError("No tokens available to refresh")
	}

	var response struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
		TokenType    string `json:"token_type"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/refresh", map[string]string{
		"refresh_token": tokens.RefreshToken,
	}, &response, WithoutAuth())
	if err != nil {
		return err
	}

	// Update stored tokens
	a.storeAuthTokens(response.AccessToken, response.RefreshToken, response.TokenType)

	return nil
}

// Me returns the current authenticated user.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (a *AuthResource) Me(ctx context.Context) (*User, error) {
	var user User
	err := a.http.Get(ctx, "/api/v1/auth/me", &user)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// ChangePassword changes the current user's password.
//
// Errors:
//   - AuthenticationError: If current password is wrong
//   - ValidationError: If new password doesn't meet requirements
func (a *AuthResource) ChangePassword(ctx context.Context, currentPassword, newPassword string) error {
	return a.http.Put(ctx, "/api/v1/auth/me/password", map[string]string{
		"current_password": currentPassword,
		"new_password":     newPassword,
	}, nil)
}

// GetAuthConfig returns the platform's authentication configuration.
//
// No authentication required. Use this to determine whether email
// verification or password reset is available.
func (a *AuthResource) GetAuthConfig(ctx context.Context) (*AuthConfig, error) {
	var config AuthConfig
	err := a.http.Get(ctx, "/api/v1/auth/config", &config, WithoutAuth())
	if err != nil {
		return nil, err
	}
	return &config, nil
}

// VerifyOTP verifies a registration OTP and returns auth tokens.
//
// After registering when email verification is required, call this with
// the 6-digit code sent to the user's email.
//
// Idempotent: if the user is already verified, tokens are issued immediately.
func (a *AuthResource) VerifyOTP(ctx context.Context, req *VerifyOTPRequest) (*User, error) {
	var response struct {
		User         User   `json:"user"`
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
		TokenType    string `json:"token_type"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/register/verify-otp", req, &response, WithoutAuth())
	if err != nil {
		return nil, err
	}

	a.storeAuthTokens(response.AccessToken, response.RefreshToken, response.TokenType)

	return &response.User, nil
}

// storeAuthTokens persists the access/refresh tokens from an auth response on
// the client, defaulting the token type to "bearer". No-op if either token is
// empty (e.g. an endpoint that doesn't issue a session).
func (a *AuthResource) storeAuthTokens(accessToken, refreshToken, tokenType string) {
	if accessToken == "" || refreshToken == "" {
		return
	}
	if tokenType == "" {
		tokenType = "bearer"
	}
	a.http.SetTokens(&AuthTokens{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    tokenType,
	})
}

// ResendOTP resends the registration OTP code.
//
// Rate-limited. Always succeeds to prevent email enumeration.
func (a *AuthResource) ResendOTP(ctx context.Context, email string) error {
	return a.http.Post(ctx, "/api/v1/auth/register/resend-otp",
		map[string]string{"email": email}, nil, WithoutAuth())
}

// RequestEmailOTP sends a passwordless sign-in code to an email address.
//
// This is the first step of the magic-link-style email sign-in: the server
// emails a 6-digit code. The account is provisioned lazily on first successful
// VerifyEmailOTP, so this call neither requires nor reveals whether an account
// already exists.
//
// Errors:
//   - APIError (503): If email-based sign-in is not available (SMTP not configured)
//   - APIError (429): If rate-limited
func (a *AuthResource) RequestEmailOTP(ctx context.Context, email string) error {
	return a.http.Post(ctx, "/api/v1/auth/email-otp/request",
		map[string]string{"email": email}, nil, WithoutAuth())
}

// VerifyEmailOTP verifies a passwordless sign-in code and stores the resulting
// JWT session on the client.
//
// On the first successful verification for an email, the server provisions a
// passwordless account (username derived from the email, no password — like
// OAuth). Subsequent sign-ins reuse the same account. After this returns, the
// client is authenticated and can mint API tokens, etc.
//
// Errors:
//   - APIError (400): If the code is invalid or expired
//   - APIError (429): If the maximum number of attempts was exceeded
func (a *AuthResource) VerifyEmailOTP(ctx context.Context, email, code string) (*User, error) {
	var response struct {
		User         User   `json:"user"`
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
		TokenType    string `json:"token_type"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/email-otp/verify",
		map[string]string{"email": email, "code": code}, &response, WithoutAuth())
	if err != nil {
		return nil, err
	}

	a.storeAuthTokens(response.AccessToken, response.RefreshToken, response.TokenType)

	return &response.User, nil
}

// RequestPasswordReset requests a password-reset OTP.
//
// Always succeeds to prevent email enumeration. If SMTP is not
// configured on the server, this is a no-op.
func (a *AuthResource) RequestPasswordReset(ctx context.Context, email string) error {
	return a.http.Post(ctx, "/api/v1/auth/password-reset/request",
		map[string]string{"email": email}, nil, WithoutAuth())
}

// ConfirmPasswordReset verifies the password-reset OTP and sets a new password.
func (a *AuthResource) ConfirmPasswordReset(ctx context.Context, req *PasswordResetConfirmRequest) error {
	return a.http.Post(ctx, "/api/v1/auth/password-reset/confirm", req, nil, WithoutAuth())
}

// GetSatelliteToken gets a satellite token for a specific audience (target service).
//
// Satellite tokens are short-lived, RS256-signed JWTs that allow satellite
// services (like SyftAI-Space) to verify user identity without calling
// SyftHub for every request.
//
// Example:
//
//	// Get a token for querying alice's SyftAI-Space endpoints
//	tokenResponse, err := client.Auth.GetSatelliteToken(ctx, "alice")
//	fmt.Printf("Token expires in %d seconds\n", tokenResponse.ExpiresIn)
func (a *AuthResource) GetSatelliteToken(ctx context.Context, audience string) (*SatelliteTokenResponse, error) {
	var response SatelliteTokenResponse
	err := a.http.Get(ctx, "/api/v1/token", &response, WithQuery(url.Values{"aud": {audience}}))
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// GetSatelliteTokens gets satellite tokens for multiple audiences in parallel.
//
// This is useful when making requests to endpoints owned by different users.
// Tokens are cached and reused where possible.
//
// Example:
//
//	// Get tokens for multiple endpoint owners
//	tokens, err := client.Auth.GetSatelliteTokens(ctx, []string{"alice", "bob"})
//	fmt.Printf("Got %d tokens\n", len(tokens))
func (a *AuthResource) GetSatelliteTokens(ctx context.Context, audiences []string) (map[string]string, error) {
	return a.fetchSatelliteTokens(ctx, audiences, a.GetSatelliteToken)
}

// GetGuestSatelliteToken gets a satellite token for a specific audience without authentication.
func (a *AuthResource) GetGuestSatelliteToken(ctx context.Context, audience string) (*SatelliteTokenResponse, error) {
	var response SatelliteTokenResponse
	err := a.http.Get(ctx, "/api/v1/token/guest", &response, WithoutAuth(), WithQuery(url.Values{"aud": {audience}}))
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// GetGuestSatelliteTokens gets guest satellite tokens for multiple audiences in parallel.
// No authentication is required.
func (a *AuthResource) GetGuestSatelliteTokens(ctx context.Context, audiences []string) (map[string]string, error) {
	return a.fetchSatelliteTokens(ctx, audiences, a.GetGuestSatelliteToken)
}

// fetchSatelliteTokens deduplicates audiences, then fetches tokens in parallel
// (up to maxTokenFetchConcurrency at once) using the provided fetch function.
// Failed tokens are silently skipped — the aggregator will handle missing tokens.
func (a *AuthResource) fetchSatelliteTokens(
	ctx context.Context,
	audiences []string,
	fetch func(context.Context, string) (*SatelliteTokenResponse, error),
) (map[string]string, error) {
	// Deduplicate audiences
	seen := make(map[string]bool)
	uniqueAudiences := make([]string, 0, len(audiences))
	for _, aud := range audiences {
		if !seen[aud] {
			seen[aud] = true
			uniqueAudiences = append(uniqueAudiences, aud)
		}
	}

	tokenMap := make(map[string]string)
	if len(uniqueAudiences) == 0 {
		return tokenMap, nil
	}

	type result struct {
		audience string
		token    string
		err      error
	}

	results := make(chan result, len(uniqueAudiences))
	var wg sync.WaitGroup
	semaphore := make(chan struct{}, maxTokenFetchConcurrency)

	for _, aud := range uniqueAudiences {
		wg.Add(1)
		go func(audience string) {
			defer wg.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			resp, err := fetch(ctx, audience)
			if err != nil {
				results <- result{audience: audience, err: err}
				return
			}
			results <- result{audience: audience, token: resp.TargetToken}
		}(aud)
	}

	go func() {
		wg.Wait()
		close(results)
	}()

	var mu sync.Mutex
	for r := range results {
		if r.token != "" {
			mu.Lock()
			tokenMap[r.audience] = r.token
			mu.Unlock()
		}
	}

	return tokenMap, nil
}

// GetPeerToken gets a peer token for NATS communication with tunneling spaces.
//
// Peer tokens are short-lived credentials that allow the aggregator to
// communicate with tunneling SyftAI Spaces via NATS pub/sub.
//
// Example:
//
//	peer, err := client.Auth.GetPeerToken(ctx, []string{"alice", "bob"})
//	fmt.Printf("Peer channel: %s, expires in %d s\n", peer.PeerChannel, peer.ExpiresIn)
func (a *AuthResource) GetPeerToken(ctx context.Context, targetUsernames []string) (*PeerTokenResponse, error) {
	var response PeerTokenResponse
	err := a.http.Post(ctx, "/api/v1/peer-token", map[string]interface{}{
		"target_usernames": targetUsernames,
	}, &response)
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// GetEncryptionPublicKey returns the X25519 identity public key (base64url)
// that the given user's space has registered. A direct peer-to-peer agent
// session encrypts its requests to this key. No authentication is required —
// the encryption key is public.
func (a *AuthResource) GetEncryptionPublicKey(ctx context.Context, username string) (string, error) {
	var response struct {
		EncryptionPublicKey string `json:"encryption_public_key"`
	}
	if err := a.http.Get(ctx, "/api/v1/nats/encryption-key/"+username, &response, WithoutAuth()); err != nil {
		return "", err
	}
	if response.EncryptionPublicKey == "" {
		return "", fmt.Errorf("user %q has not registered an encryption key", username)
	}
	return response.EncryptionPublicKey, nil
}

// GetGuestPeerToken gets a peer token for NATS communication without authentication.
//
// Guest peer tokens are rate-limited by IP address. They use the same
// response format as authenticated peer tokens.
//
// Example:
//
//	peer, err := client.Auth.GetGuestPeerToken(ctx, []string{"alice"})
//	fmt.Printf("Guest peer channel: %s\n", peer.PeerChannel)
func (a *AuthResource) GetGuestPeerToken(ctx context.Context, targetUsernames []string) (*PeerTokenResponse, error) {
	var response PeerTokenResponse
	err := a.http.Post(ctx, "/api/v1/nats/guest-peer-token", map[string]interface{}{
		"target_usernames": targetUsernames,
	}, &response, WithoutAuth())
	if err != nil {
		return nil, err
	}
	return &response, nil
}
