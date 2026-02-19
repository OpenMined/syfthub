package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

// HubResource handles browsing and discovery of public endpoints.
//
// Example usage:
//
//	// Browse all public endpoints
//	iter := client.Hub.Browse(ctx)
//	for iter.Next(ctx) {
//	    ep := iter.Value()
//	    fmt.Printf("%s: %s\n", ep.Path(), ep.Name)
//	}
//
//	// Get trending endpoints
//	iter = client.Hub.Trending(ctx, WithMinStars(10))
//	for iter.Next(ctx) {
//	    ep := iter.Value()
//	    fmt.Printf("%s - %d stars\n", ep.Name, ep.StarsCount)
//	}
//
//	// Semantic search for endpoints
//	results, _ := client.Hub.Search(ctx, "machine learning for images")
//	for _, result := range results {
//	    fmt.Printf("%s: %.2f\n", result.Path(), result.RelevanceScore)
//	}
//
//	// Get a specific endpoint by path
//	endpoint, _ := client.Hub.Get(ctx, "alice/cool-api")
//	fmt.Println(endpoint.Readme)
//
//	// Star an endpoint (requires auth)
//	client.Hub.Star(ctx, "alice/cool-api")
//
//	// Check if you've starred an endpoint
//	starred, _ := client.Hub.IsStarred(ctx, "alice/cool-api")
//	if starred {
//	    fmt.Println("You've starred this!")
//	}
//
//	// Unstar an endpoint
//	client.Hub.Unstar(ctx, "alice/cool-api")
type HubResource struct {
	http *httpClient
}

// newHubResource creates a new HubResource.
func newHubResource(http *httpClient) *HubResource {
	return &HubResource{http: http}
}

// BrowseOption configures the Browse operation.
type BrowseOption func(*browseOptions)

type browseOptions struct {
	pageSize int
}

// WithPageSize sets the page size for browsing.
func WithPageSize(size int) BrowseOption {
	return func(o *browseOptions) {
		o.pageSize = size
	}
}

// Browse returns all public endpoints.
func (h *HubResource) Browse(ctx context.Context, opts ...BrowseOption) *PageIterator[EndpointPublic] {
	options := &browseOptions{pageSize: DefaultPageSize}
	for _, opt := range opts {
		opt(options)
	}

	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		query := url.Values{}
		query.Set("skip", strconv.Itoa(skip))
		query.Set("limit", strconv.Itoa(limit))

		body, err := h.http.GetRaw(ctx, "/api/v1/endpoints/public", WithoutAuth(), WithQuery(query))
		if err != nil {
			return nil, err
		}

		var items []json.RawMessage
		if err := json.Unmarshal(body, &items); err != nil {
			return nil, err
		}
		return items, nil
	}

	return NewPageIterator[EndpointPublic](fetchFn, options.pageSize)
}

// OwnersOption configures the Owners operation.
type OwnersOption func(*ownersOptions)

type ownersOptions struct {
	limit int
}

// WithOwnersLimit sets the maximum number of owners to return.
func WithOwnersLimit(limit int) OwnersOption {
	return func(o *ownersOptions) {
		o.limit = limit
	}
}

// Owners returns a list of all owners (users/orgs) that have public endpoints.
//
// This is an efficient endpoint that returns only owner usernames and
// aggregated endpoint counts, without fetching full endpoint data.
// Useful for directory listing (e.g., `syft ls`).
//
// Example:
//
//	owners, _ := client.Hub.Owners(ctx, WithOwnersLimit(50))
//	for _, owner := range owners {
//	    fmt.Printf("%s/ (%d endpoints)\n", owner.Username, owner.EndpointCount)
//	}
func (h *HubResource) Owners(ctx context.Context, opts ...OwnersOption) ([]OwnerSummary, error) {
	options := &ownersOptions{limit: 100}
	for _, opt := range opts {
		opt(options)
	}

	query := url.Values{}
	query.Set("skip", "0")
	query.Set("limit", strconv.Itoa(options.limit))

	var response OwnersListResponse
	err := h.http.Get(ctx, "/api/v1/endpoints/public/owners", &response, WithoutAuth(), WithQuery(query))
	if err != nil {
		return nil, err
	}

	return response.Owners, nil
}

// ByOwnerOption configures the ByOwner operation.
type ByOwnerOption func(*byOwnerOptions)

type byOwnerOptions struct {
	skip  int
	limit int
}

// WithByOwnerSkip sets the number of endpoints to skip.
func WithByOwnerSkip(skip int) ByOwnerOption {
	return func(o *byOwnerOptions) {
		o.skip = skip
	}
}

// WithByOwnerLimit sets the maximum number of endpoints to return.
func WithByOwnerLimit(limit int) ByOwnerOption {
	return func(o *byOwnerOptions) {
		o.limit = limit
	}
}

// ByOwner returns all public endpoints for a specific owner (user or organization).
//
// This uses the API route GET /api/v1/endpoints/public/by-owner/{owner_slug}
// which is more efficient than browsing all endpoints and filtering by owner.
//
// Example:
//
//	endpoints, _ := client.Hub.ByOwner(ctx, "alice", WithByOwnerLimit(50))
//	for _, ep := range endpoints {
//	    fmt.Printf("%s: %s\n", ep.Slug, ep.Description)
//	}
func (h *HubResource) ByOwner(ctx context.Context, owner string, opts ...ByOwnerOption) ([]EndpointPublic, error) {
	options := &byOwnerOptions{skip: 0, limit: 100}
	for _, opt := range opts {
		opt(options)
	}

	query := url.Values{}
	query.Set("skip", strconv.Itoa(options.skip))
	query.Set("limit", strconv.Itoa(options.limit))

	// Use the API route: GET /api/v1/endpoints/public/by-owner/{owner_slug}
	path := "/api/v1/endpoints/public/by-owner/" + url.PathEscape(owner)

	body, err := h.http.GetRaw(ctx, path, WithoutAuth(), WithQuery(query))
	if err != nil {
		return nil, err
	}

	var endpoints []EndpointPublic
	if err := json.Unmarshal(body, &endpoints); err != nil {
		return nil, err
	}

	return endpoints, nil
}

// TrendingOption configures the Trending operation.
type TrendingOption func(*trendingOptions)

type trendingOptions struct {
	minStars *int
	pageSize int
}

// WithMinStars filters endpoints by minimum star count.
func WithMinStars(minStars int) TrendingOption {
	return func(o *trendingOptions) {
		o.minStars = &minStars
	}
}

// WithTrendingPageSize sets the page size for trending.
func WithTrendingPageSize(size int) TrendingOption {
	return func(o *trendingOptions) {
		o.pageSize = size
	}
}

// Trending returns trending endpoints sorted by stars.
func (h *HubResource) Trending(ctx context.Context, opts ...TrendingOption) *PageIterator[EndpointPublic] {
	options := &trendingOptions{pageSize: DefaultPageSize}
	for _, opt := range opts {
		opt(options)
	}

	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		query := url.Values{}
		query.Set("skip", strconv.Itoa(skip))
		query.Set("limit", strconv.Itoa(limit))
		if options.minStars != nil {
			query.Set("min_stars", strconv.Itoa(*options.minStars))
		}

		body, err := h.http.GetRaw(ctx, "/api/v1/endpoints/trending", WithoutAuth(), WithQuery(query))
		if err != nil {
			return nil, err
		}

		var items []json.RawMessage
		if err := json.Unmarshal(body, &items); err != nil {
			return nil, err
		}
		return items, nil
	}

	return NewPageIterator[EndpointPublic](fetchFn, options.pageSize)
}

// SearchOption configures the Search operation.
type SearchOption func(*searchOptions)

type searchOptions struct {
	topK         int
	endpointType *EndpointType
	minScore     float64
}

// WithTopK sets the maximum number of search results.
func WithTopK(k int) SearchOption {
	return func(o *searchOptions) {
		o.topK = k
	}
}

// WithEndpointType filters search results by endpoint type.
func WithEndpointType(t EndpointType) SearchOption {
	return func(o *searchOptions) {
		o.endpointType = &t
	}
}

// WithMinScore sets the minimum relevance score threshold.
func WithMinScore(score float64) SearchOption {
	return func(o *searchOptions) {
		o.minScore = score
	}
}

// Search performs semantic search for endpoints.
//
// Uses RAG-powered semantic search to find endpoints that match the
// natural language query. Returns results sorted by relevance score.
//
// Note: If RAG is not configured on the server (no OpenAI API key),
// this method returns an empty list.
func (h *HubResource) Search(ctx context.Context, query string, opts ...SearchOption) ([]EndpointSearchResult, error) {
	options := &searchOptions{
		topK:     10,
		minScore: 0.0,
	}
	for _, opt := range opts {
		opt(options)
	}

	// Skip search for very short queries
	query = strings.TrimSpace(query)
	if len(query) < 3 {
		return []EndpointSearchResult{}, nil
	}

	payload := map[string]interface{}{
		"query": query,
		"top_k": options.topK,
	}
	if options.endpointType != nil {
		payload["type"] = string(*options.endpointType)
	}

	var response EndpointSearchResponse
	err := h.http.Post(ctx, "/api/v1/endpoints/search", payload, &response, WithoutAuth())
	if err != nil {
		// Return empty list on any error (e.g., RAG not configured)
		return []EndpointSearchResult{}, nil
	}

	// Filter by min_score
	results := make([]EndpointSearchResult, 0, len(response.Results))
	for _, result := range response.Results {
		if result.RelevanceScore >= options.minScore {
			results = append(results, result)
		}
	}

	return results, nil
}

// Get returns an endpoint by its path (owner/slug format).
//
// This method searches the public endpoints API to find the endpoint,
// which works reliably across all deployment configurations.
func (h *HubResource) Get(ctx context.Context, path string) (*EndpointPublic, error) {
	owner, slug, err := h.parsePath(path)
	if err != nil {
		return nil, err
	}

	// Search public endpoints to find the matching one
	iter := h.Browse(ctx, WithPageSize(100))
	for iter.Next(ctx) {
		endpoint := iter.Value()
		if endpoint.OwnerUsername == owner && endpoint.Slug == slug {
			return &endpoint, nil
		}
	}
	if err := iter.Err(); err != nil {
		return nil, err
	}

	return nil, newNotFoundError(fmt.Sprintf("Endpoint not found: '%s'", path))
}

// Star stars an endpoint.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
func (h *HubResource) Star(ctx context.Context, path string) error {
	endpointID, err := h.resolveEndpointID(ctx, path)
	if err != nil {
		return err
	}
	return h.http.Post(ctx, fmt.Sprintf("/api/v1/endpoints/%d/star", endpointID), nil, nil)
}

// Unstar unstars an endpoint.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
func (h *HubResource) Unstar(ctx context.Context, path string) error {
	endpointID, err := h.resolveEndpointID(ctx, path)
	if err != nil {
		return err
	}
	return h.http.Delete(ctx, fmt.Sprintf("/api/v1/endpoints/%d/star", endpointID))
}

// IsStarred checks if you have starred an endpoint.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If endpoint not found
func (h *HubResource) IsStarred(ctx context.Context, path string) (bool, error) {
	endpointID, err := h.resolveEndpointID(ctx, path)
	if err != nil {
		return false, err
	}

	var response struct {
		Starred bool `json:"starred"`
	}
	err = h.http.Get(ctx, fmt.Sprintf("/api/v1/endpoints/%d/starred", endpointID), &response)
	if err != nil {
		return false, err
	}
	return response.Starred, nil
}

// parsePath parses an endpoint path into owner and slug.
func (h *HubResource) parsePath(path string) (owner, slug string, err error) {
	path = strings.Trim(path, "/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 {
		return "", "", fmt.Errorf("invalid endpoint path: '%s'. Expected format: 'owner/slug'", path)
	}
	return parts[0], parts[1], nil
}

// resolveEndpointID resolves an endpoint path to its ID.
func (h *HubResource) resolveEndpointID(ctx context.Context, path string) (int, error) {
	_, slug, err := h.parsePath(path)
	if err != nil {
		return 0, err
	}

	// Search the user's endpoints to find the ID
	query := url.Values{}
	query.Set("limit", "100")

	body, err := h.http.GetRaw(ctx, "/api/v1/endpoints", WithQuery(query))
	if err != nil {
		return 0, err
	}

	var endpoints []struct {
		ID   int    `json:"id"`
		Slug string `json:"slug"`
	}
	if err := json.Unmarshal(body, &endpoints); err != nil {
		return 0, err
	}

	for _, ep := range endpoints {
		if ep.Slug == slug {
			return ep.ID, nil
		}
	}

	return 0, newNotFoundError(fmt.Sprintf("Could not resolve endpoint ID for '%s'", path))
}
