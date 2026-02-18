package syfthub

import (
	"context"
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
func (a *AuthResource) Register(ctx context.Context, req *RegisterRequest) (*User, error) {
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
		User         User   `json:"user"`
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
		TokenType    string `json:"token_type"`
	}

	err := a.http.Post(ctx, "/api/v1/auth/register", payload, &response, WithoutAuth())
	if err != nil {
		return nil, err
	}

	// Store tokens if present (auto-login after registration)
	if response.AccessToken != "" && response.RefreshToken != "" {
		tokenType := response.TokenType
		if tokenType == "" {
			tokenType = "bearer"
		}
		a.http.SetTokens(&AuthTokens{
			AccessToken:  response.AccessToken,
			RefreshToken: response.RefreshToken,
			TokenType:    tokenType,
		})
	}

	return &response.User, nil
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
	tokenType := response.TokenType
	if tokenType == "" {
		tokenType = "bearer"
	}
	a.http.SetTokens(&AuthTokens{
		AccessToken:  response.AccessToken,
		RefreshToken: response.RefreshToken,
		TokenType:    tokenType,
	})

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
	tokenType := response.TokenType
	if tokenType == "" {
		tokenType = "bearer"
	}
	a.http.SetTokens(&AuthTokens{
		AccessToken:  response.AccessToken,
		RefreshToken: response.RefreshToken,
		TokenType:    tokenType,
	})

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

	// Fetch tokens in parallel using goroutines
	type result struct {
		audience string
		token    string
		err      error
	}

	results := make(chan result, len(uniqueAudiences))
	var wg sync.WaitGroup

	// Limit concurrency to 10
	semaphore := make(chan struct{}, 10)

	for _, aud := range uniqueAudiences {
		wg.Add(1)
		go func(audience string) {
			defer wg.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			resp, err := a.GetSatelliteToken(ctx, audience)
			if err != nil {
				// Failed tokens are silently skipped - the aggregator will handle missing tokens
				results <- result{audience: audience, err: err}
				return
			}
			results <- result{audience: audience, token: resp.TargetToken}
		}(aud)
	}

	// Close results channel when all goroutines complete
	go func() {
		wg.Wait()
		close(results)
	}()

	// Collect successful results
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

// GetTransactionTokens gets transaction tokens for billing authorization.
//
// Transaction tokens are short-lived JWTs that pre-authorize endpoint owners
// (recipients) to charge the current user (sender) for usage. This enables
// billing workflows in the aggregator.
//
// Returns a map with "tokens" (owner -> token) and "errors" (owner -> error msg).
//
// Example:
//
//	response, err := client.Auth.GetTransactionTokens(ctx, []string{"alice", "bob"})
//	fmt.Printf("Got tokens for: %v\n", getKeys(response.Tokens))
func (a *AuthResource) GetTransactionTokens(ctx context.Context, ownerUsernames []string) (*TransactionTokensResponse, error) {
	// Deduplicate owners
	seen := make(map[string]bool)
	uniqueOwners := make([]string, 0, len(ownerUsernames))
	for _, owner := range ownerUsernames {
		if !seen[owner] {
			seen[owner] = true
			uniqueOwners = append(uniqueOwners, owner)
		}
	}

	if len(uniqueOwners) == 0 {
		return &TransactionTokensResponse{Tokens: make(map[string]string)}, nil
	}

	var response struct {
		Tokens map[string]string `json:"tokens"`
		Errors map[string]string `json:"errors"`
	}

	err := a.http.Post(ctx, "/api/v1/accounting/transaction-tokens", map[string]interface{}{
		"owner_usernames": uniqueOwners,
	}, &response)
	if err != nil {
		// Silent failure - chat can proceed without transaction tokens
		// Billing will not work, but the query can still execute
		return &TransactionTokensResponse{Tokens: make(map[string]string)}, nil
	}

	return &TransactionTokensResponse{Tokens: response.Tokens}, nil
}
