package syfthub

import (
	"context"
	"net/url"
)

// UsersResource handles user profile operations.
//
// Example usage:
//
//	// Update profile
//	user, err := client.Users.Update(ctx, &UpdateUserRequest{
//	    FullName: ptr("John D."),
//	})
//
//	// Check username availability
//	available, err := client.Users.CheckUsername(ctx, "newusername")
//	if available {
//	    fmt.Println("Username is available!")
//	}
//
//	// Check email availability
//	available, err = client.Users.CheckEmail(ctx, "new@example.com")
//
//	// Manage aggregators
//	aggregators, err := client.Users.Aggregators.List(ctx)
type UsersResource struct {
	http        *httpClient
	Aggregators *AggregatorsResource
}

// newUsersResource creates a new UsersResource.
func newUsersResource(http *httpClient) *UsersResource {
	return &UsersResource{
		http:        http,
		Aggregators: newAggregatorsResource(http),
	}
}

// Update updates the current user's profile. Only provided fields will be updated.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If update data is invalid
func (u *UsersResource) Update(ctx context.Context, req *UpdateUserRequest) (*User, error) {
	payload := make(map[string]interface{})

	if req.FullName != nil {
		payload["full_name"] = *req.FullName
	}
	if req.AvatarURL != nil {
		payload["avatar_url"] = *req.AvatarURL
	}

	var user User
	err := u.http.Put(ctx, "/api/v1/users/me", payload, &user)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// CheckUsername checks if a username is available.
func (u *UsersResource) CheckUsername(ctx context.Context, username string) (bool, error) {
	var response struct {
		Available bool `json:"available"`
	}
	err := u.http.Get(ctx, "/api/v1/users/check-username/"+url.PathEscape(username), &response, WithoutAuth())
	if err != nil {
		return false, err
	}
	return response.Available, nil
}

// CheckEmail checks if an email is available.
func (u *UsersResource) CheckEmail(ctx context.Context, email string) (bool, error) {
	var response struct {
		Available bool `json:"available"`
	}
	err := u.http.Get(ctx, "/api/v1/users/check-email/"+url.PathEscape(email), &response, WithoutAuth())
	if err != nil {
		return false, err
	}
	return response.Available, nil
}

// GetAccountingCredentials returns the current user's accounting service credentials.
//
// Returns credentials stored in SyftHub for connecting to an external
// accounting service. The email is always the same as the user's SyftHub email.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (u *UsersResource) GetAccountingCredentials(ctx context.Context) (*AccountingCredentials, error) {
	var creds AccountingCredentials
	err := u.http.Get(ctx, "/api/v1/users/me/accounting", &creds)
	if err != nil {
		return nil, err
	}
	return &creds, nil
}

// GetNatsCredentials returns NATS credentials for connecting to the NATS server.
//
// Fetches the shared NATS auth token from the hub. Spaces call this
// after login to obtain credentials for NATS WebSocket connections.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - APIError: If NATS is not configured on the hub (503)
func (u *UsersResource) GetNatsCredentials(ctx context.Context) (*NatsCredentials, error) {
	var creds NatsCredentials
	err := u.http.Get(ctx, "/api/v1/nats/credentials", &creds)
	if err != nil {
		return nil, err
	}
	return &creds, nil
}

// SendHeartbeat sends a heartbeat to indicate this SyftAI Space is alive.
//
// The heartbeat mechanism allows SyftAI Spaces to signal their availability
// to SyftHub. This should be called periodically (before the TTL expires)
// to maintain the "active" status.
//
// Parameters:
//   - spaceURL: Full URL of this space (e.g., "https://myspace.example.com")
//   - ttlSeconds: Time-to-live in seconds (1-3600). Server caps at 600.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If URL or TTL is invalid
func (u *UsersResource) SendHeartbeat(ctx context.Context, spaceURL string, ttlSeconds int) (*HeartbeatResponse, error) {
	payload := map[string]interface{}{
		"url":         spaceURL,
		"ttl_seconds": ttlSeconds,
	}

	var response HeartbeatResponse
	err := u.http.Post(ctx, "/api/v1/users/me/heartbeat", payload, &response)
	if err != nil {
		return nil, err
	}
	return &response, nil
}
