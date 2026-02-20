package syfthub

import (
	"context"
	"encoding/json"
)

// FetchFunc is a function that fetches a page of items.
// It takes context, skip, and limit parameters and returns raw JSON items.
type FetchFunc func(ctx context.Context, skip, limit int) ([]json.RawMessage, error)

// PageIterator provides lazy pagination that fetches pages on demand.
//
// Example usage:
//
//	// Iterate through all items
//	iter := client.Hub.Browse(ctx)
//	for iter.Next(ctx) {
//	    endpoint := iter.Value()
//	    fmt.Println(endpoint.Name)
//	}
//	if err := iter.Err(); err != nil {
//	    log.Fatal(err)
//	}
//
//	// Get just the first page
//	items, err := client.Hub.Browse(ctx).FirstPage(ctx)
//
//	// Get all items as a slice
//	items, err := client.Hub.Browse(ctx).All(ctx)
//
//	// Get first 50 items
//	items, err := client.Hub.Browse(ctx).Take(ctx, 50)
type PageIterator[T any] struct {
	fetchFn  FetchFunc
	pageSize int

	// Current state
	buffer      []T
	currentPage int
	exhausted   bool
	err         error
	current     T
}

// NewPageIterator creates a new page iterator.
func NewPageIterator[T any](fetchFn FetchFunc, pageSize int) *PageIterator[T] {
	if pageSize <= 0 {
		pageSize = 20
	}
	return &PageIterator[T]{
		fetchFn:  fetchFn,
		pageSize: pageSize,
	}
}

// Reset resets the iterator state for fresh iteration.
func (p *PageIterator[T]) Reset() {
	p.buffer = nil
	p.currentPage = 0
	p.exhausted = false
	p.err = nil
	var zero T
	p.current = zero
}

// fetchPage fetches a single page and converts to typed items.
func (p *PageIterator[T]) fetchPage(ctx context.Context, page int) ([]T, error) {
	skip := page * p.pageSize
	rawItems, err := p.fetchFn(ctx, skip, p.pageSize)
	if err != nil {
		return nil, err
	}

	// Convert raw JSON to typed items
	items := make([]T, 0, len(rawItems))
	for _, raw := range rawItems {
		var item T
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, err
		}
		items = append(items, item)
	}

	// Check if this is the last page
	if len(items) < p.pageSize {
		p.exhausted = true
	}

	return items, nil
}

// Next advances the iterator to the next item.
// Returns true if there is a next item, false otherwise.
// Call Value() to get the current item after Next() returns true.
func (p *PageIterator[T]) Next(ctx context.Context) bool {
	// If we have items in buffer, use the next one
	if len(p.buffer) > 0 {
		p.current = p.buffer[0]
		p.buffer = p.buffer[1:]
		return true
	}

	// If exhausted, stop iteration
	if p.exhausted {
		return false
	}

	// Fetch next page
	pageItems, err := p.fetchPage(ctx, p.currentPage)
	if err != nil {
		p.err = err
		return false
	}
	p.currentPage++

	if len(pageItems) == 0 {
		p.exhausted = true
		return false
	}

	// Set current to first item, buffer the rest
	p.current = pageItems[0]
	if len(pageItems) > 1 {
		p.buffer = pageItems[1:]
	}

	return true
}

// Value returns the current item.
// Should only be called after Next() returns true.
func (p *PageIterator[T]) Value() T {
	return p.current
}

// Err returns any error that occurred during iteration.
func (p *PageIterator[T]) Err() error {
	return p.err
}

// FirstPage returns just the first page of results.
func (p *PageIterator[T]) FirstPage(ctx context.Context) ([]T, error) {
	return p.fetchPage(ctx, 0)
}

// All fetches all pages and returns as a single slice.
// Warning: This loads all items into memory.
func (p *PageIterator[T]) All(ctx context.Context) ([]T, error) {
	p.Reset()
	var result []T
	for p.Next(ctx) {
		result = append(result, p.Value())
	}
	if err := p.Err(); err != nil {
		return nil, err
	}
	return result, nil
}

// Take returns the first n items (may span multiple pages).
func (p *PageIterator[T]) Take(ctx context.Context, n int) ([]T, error) {
	p.Reset()
	result := make([]T, 0, n)
	for p.Next(ctx) {
		result = append(result, p.Value())
		if len(result) >= n {
			break
		}
	}
	if err := p.Err(); err != nil {
		return nil, err
	}
	return result, nil
}

// Collect is an alias for All that fetches all pages.
func (p *PageIterator[T]) Collect(ctx context.Context) ([]T, error) {
	return p.All(ctx)
}

// ForEach iterates through all items and calls the callback for each.
func (p *PageIterator[T]) ForEach(ctx context.Context, fn func(T) error) error {
	p.Reset()
	for p.Next(ctx) {
		if err := fn(p.Value()); err != nil {
			return err
		}
	}
	return p.Err()
}

// Filter returns a new slice containing only items that match the predicate.
func (p *PageIterator[T]) Filter(ctx context.Context, predicate func(T) bool) ([]T, error) {
	p.Reset()
	var result []T
	for p.Next(ctx) {
		if predicate(p.Value()) {
			result = append(result, p.Value())
		}
	}
	if err := p.Err(); err != nil {
		return nil, err
	}
	return result, nil
}
