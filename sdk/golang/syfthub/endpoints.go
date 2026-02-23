package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

// MyEndpointsResource handles CRUD operations for the user's own endpoints.
//
// Example usage:
//
//	// List my endpoints (with pagination)
//	iter := client.MyEndpoints.List(ctx)
//	for iter.Next(ctx) {
//	    ep := iter.Value()
//	    fmt.Printf("%s (%s)\n", ep.Name, ep.Visibility)
//	}
//
//	// Create a new endpoint
//	endpoint, err := client.MyEndpoints.Create(ctx, &CreateEndpointRequest{
//	    Name:        "My API",
//	    Type:        EndpointTypeModel,
//	    Visibility:  VisibilityPublic,
//	    Description: "A cool API",
//	    Readme:      "# My API\n\nThis is my API.",
//	})
//
//	// Get a specific endpoint by path
//	endpoint, err := client.MyEndpoints.Get(ctx, "alice/my-api")
//
//	// Update an endpoint
//	endpoint, err := client.MyEndpoints.Update(ctx, "alice/my-api", &UpdateEndpointRequest{
//	    Description: ptr("Updated description"),
//	})
//
//	// Delete an endpoint
//	err = client.MyEndpoints.Delete(ctx, "alice/my-api")
type MyEndpointsResource struct {
	http *httpClient
}

// newMyEndpointsResource creates a new MyEndpointsResource.
func newMyEndpointsResource(http *httpClient) *MyEndpointsResource {
	return &MyEndpointsResource{http: http}
}

// ListOption configures the List operation.
type ListOption func(*listOptions)

type listOptions struct {
	visibility *Visibility
	pageSize   int
}

// WithVisibility filters endpoints by visibility.
func WithVisibility(v Visibility) ListOption {
	return func(o *listOptions) {
		o.visibility = &v
	}
}

// WithListPageSize sets the page size for listing.
func WithListPageSize(size int) ListOption {
	return func(o *listOptions) {
		o.pageSize = size
	}
}

// List returns the current user's endpoints.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (e *MyEndpointsResource) List(ctx context.Context, opts ...ListOption) *PageIterator[Endpoint] {
	options := &listOptions{pageSize: DefaultPageSize}
	for _, opt := range opts {
		opt(options)
	}

	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		query := url.Values{}
		query.Set("skip", strconv.Itoa(skip))
		query.Set("limit", strconv.Itoa(limit))
		if options.visibility != nil {
			query.Set("visibility", string(*options.visibility))
		}

		body, err := e.http.GetRaw(ctx, "/api/v1/endpoints", WithQuery(query))
		if err != nil {
			return nil, err
		}

		var items []json.RawMessage
		if err := json.Unmarshal(body, &items); err != nil {
			return nil, err
		}
		return items, nil
	}

	return NewPageIterator[Endpoint](fetchFn, options.pageSize)
}

// Create creates a new endpoint.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If data is invalid
func (e *MyEndpointsResource) Create(ctx context.Context, req *CreateEndpointRequest) (*Endpoint, error) {
	payload := map[string]interface{}{
		"name":        req.Name,
		"type":        string(req.Type),
		"visibility":  string(req.Visibility),
		"description": req.Description,
		"readme":      req.Readme,
	}

	if req.Slug != nil {
		payload["slug"] = *req.Slug
	}
	if req.Tags != nil {
		payload["tags"] = req.Tags
	}
	if req.Policies != nil {
		payload["policies"] = req.Policies
	}
	if req.Connect != nil {
		payload["connect"] = req.Connect
	}

	var endpoint Endpoint
	err := e.http.Post(ctx, "/api/v1/endpoints", payload, &endpoint)
	if err != nil {
		return nil, err
	}
	return &endpoint, nil
}

// Get returns a specific endpoint by path.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
//   - AuthorizationError: If not authorized to view
func (e *MyEndpointsResource) Get(ctx context.Context, path string) (*Endpoint, error) {
	_, slug, err := e.parsePath(path)
	if err != nil {
		return nil, err
	}

	// Search user's own endpoints by slug
	query := url.Values{}
	query.Set("limit", "100")

	body, err := e.http.GetRaw(ctx, "/api/v1/endpoints", WithQuery(query))
	if err != nil {
		return nil, err
	}

	var endpoints []Endpoint
	if err := json.Unmarshal(body, &endpoints); err != nil {
		return nil, err
	}

	for _, ep := range endpoints {
		if ep.Slug == slug {
			return &ep, nil
		}
	}

	return nil, newNotFoundError(fmt.Sprintf("Endpoint not found: '%s'", path))
}

// Update updates an endpoint. Only provided fields will be updated.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
//   - AuthorizationError: If not owner/admin
func (e *MyEndpointsResource) Update(ctx context.Context, path string, req *UpdateEndpointRequest) (*Endpoint, error) {
	_, slug, err := e.parsePath(path)
	if err != nil {
		return nil, err
	}

	payload := make(map[string]interface{})

	if req.Name != nil {
		payload["name"] = *req.Name
	}
	if req.Description != nil {
		payload["description"] = *req.Description
	}
	if req.Visibility != nil {
		payload["visibility"] = string(*req.Visibility)
	}
	if req.Readme != nil {
		payload["readme"] = *req.Readme
	}
	if req.Tags != nil {
		payload["tags"] = req.Tags
	}
	if req.Policies != nil {
		payload["policies"] = req.Policies
	}
	if req.Connect != nil {
		payload["connect"] = req.Connect
	}

	var endpoint Endpoint
	err = e.http.Patch(ctx, fmt.Sprintf("/api/v1/endpoints/slug/%s", slug), payload, &endpoint)
	if err != nil {
		return nil, err
	}
	return &endpoint, nil
}

// Delete deletes an endpoint.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
//   - AuthorizationError: If not owner/admin
func (e *MyEndpointsResource) Delete(ctx context.Context, path string) error {
	_, slug, err := e.parsePath(path)
	if err != nil {
		return err
	}
	return e.http.Delete(ctx, fmt.Sprintf("/api/v1/endpoints/slug/%s", slug))
}

// Sync synchronizes user's endpoints with the provided list.
//
// This is a DESTRUCTIVE operation that:
//  1. Deletes ALL existing endpoints owned by the current user
//  2. Creates ALL endpoints from the provided list
//  3. Is ATOMIC: either all endpoints sync successfully, or none do
//
// Important Notes:
//   - Organization endpoints are NOT affected
//   - Stars on existing endpoints will be lost (reset to 0)
//   - Endpoint IDs will change (new IDs assigned)
//   - Maximum 100 endpoints per sync request
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If any endpoint fails validation
func (e *MyEndpointsResource) Sync(ctx context.Context, endpoints []map[string]interface{}) (*SyncEndpointsResponse, error) {
	if endpoints == nil {
		endpoints = []map[string]interface{}{}
	}

	payload := map[string]interface{}{
		"endpoints": endpoints,
	}

	var response SyncEndpointsResponse
	err := e.http.Post(ctx, "/api/v1/endpoints/sync", payload, &response)
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// parsePath parses an endpoint path into owner and slug.
func (e *MyEndpointsResource) parsePath(path string) (owner, slug string, err error) {
	path = strings.Trim(path, "/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 {
		return "", "", fmt.Errorf("invalid endpoint path: '%s'. Expected format: 'owner/slug'", path)
	}
	return parts[0], parts[1], nil
}
