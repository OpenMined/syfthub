package syfthub

import (
	"context"
	"fmt"
)

// AggregatorsResource handles user aggregator configurations.
//
// Aggregators are custom RAG orchestration service endpoints that users can
// configure to use for chat operations. Each user can have multiple aggregator
// configurations, with one set as the default.
//
// The first aggregator created is automatically set as the default. Only one
// aggregator can be the default at a time; setting a new default automatically
// unsets the previous one.
//
// Example usage:
//
//	// List all aggregators
//	aggregators, err := client.Users.Aggregators.List(ctx)
//	for _, agg := range aggregators {
//	    fmt.Printf("%s: %s\n", agg.Name, agg.URL)
//	}
//
//	// Create a new aggregator
//	agg, err := client.Users.Aggregators.Create(ctx, "My Aggregator", "https://my-aggregator.example.com")
//
//	// Update an aggregator
//	agg, err = client.Users.Aggregators.Update(ctx, 1, &UpdateAggregatorRequest{
//	    Name: ptr("Updated Name"),
//	})
//
//	// Set as default
//	agg, err = client.Users.Aggregators.SetDefault(ctx, 1)
//
//	// Delete an aggregator
//	err = client.Users.Aggregators.Delete(ctx, 1)
type AggregatorsResource struct {
	http *httpClient
}

// newAggregatorsResource creates a new AggregatorsResource.
func newAggregatorsResource(http *httpClient) *AggregatorsResource {
	return &AggregatorsResource{http: http}
}

// aggregatorListResponse is the envelope returned by GET /users/me/aggregators.
type aggregatorListResponse struct {
	Aggregators         []UserAggregator `json:"aggregators"`
	DefaultAggregatorID *int             `json:"default_aggregator_id"`
}

// List returns all aggregator configurations for the current user.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (a *AggregatorsResource) List(ctx context.Context) ([]UserAggregator, error) {
	var resp aggregatorListResponse
	err := a.http.Get(ctx, "/api/v1/users/me/aggregators", &resp)
	if err != nil {
		return nil, err
	}
	if resp.Aggregators == nil {
		resp.Aggregators = []UserAggregator{}
	}
	return resp.Aggregators, nil
}

// Get returns a specific aggregator configuration by ID.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If aggregator not found
func (a *AggregatorsResource) Get(ctx context.Context, aggregatorID int) (*UserAggregator, error) {
	var aggregator UserAggregator
	err := a.http.Get(ctx, fmt.Sprintf("/api/v1/users/me/aggregators/%d", aggregatorID), &aggregator)
	if err != nil {
		return nil, err
	}
	return &aggregator, nil
}

// Create creates a new aggregator configuration.
//
// The first aggregator created is automatically set as the default.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If input is invalid
func (a *AggregatorsResource) Create(ctx context.Context, name, url string) (*UserAggregator, error) {
	payload := map[string]interface{}{
		"name": name,
		"url":  url,
	}

	var aggregator UserAggregator
	err := a.http.Post(ctx, "/api/v1/users/me/aggregators", payload, &aggregator)
	if err != nil {
		return nil, err
	}
	return &aggregator, nil
}

// UpdateAggregatorRequest contains optional fields for updating an aggregator.
type UpdateAggregatorRequest struct {
	Name *string
	URL  *string
}

// Update updates an aggregator configuration.
//
// Only provided fields will be updated.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If aggregator not found
//   - ValidationError: If input is invalid
func (a *AggregatorsResource) Update(ctx context.Context, aggregatorID int, req *UpdateAggregatorRequest) (*UserAggregator, error) {
	payload := make(map[string]interface{})

	if req.Name != nil {
		payload["name"] = *req.Name
	}
	if req.URL != nil {
		payload["url"] = *req.URL
	}

	var aggregator UserAggregator
	err := a.http.Put(ctx, fmt.Sprintf("/api/v1/users/me/aggregators/%d", aggregatorID), payload, &aggregator)
	if err != nil {
		return nil, err
	}
	return &aggregator, nil
}

// Delete deletes an aggregator configuration.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If aggregator not found
func (a *AggregatorsResource) Delete(ctx context.Context, aggregatorID int) error {
	return a.http.Delete(ctx, fmt.Sprintf("/api/v1/users/me/aggregators/%d", aggregatorID))
}

// SetDefault sets an aggregator as the default.
//
// Only one aggregator can be the default at a time. Setting a new default
// automatically unsets the previous one.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If aggregator not found
func (a *AggregatorsResource) SetDefault(ctx context.Context, aggregatorID int) (*UserAggregator, error) {
	var aggregator UserAggregator
	err := a.http.Patch(ctx, fmt.Sprintf("/api/v1/users/me/aggregators/%d/default", aggregatorID), nil, &aggregator)
	if err != nil {
		return nil, err
	}
	return &aggregator, nil
}
