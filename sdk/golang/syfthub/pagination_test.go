package syfthub

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
)

func TestNewPageIterator(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		return nil, nil
	}

	t.Run("with valid page size", func(t *testing.T) {
		iter := NewPageIterator[string](fetchFn, 10)
		if iter == nil {
			t.Fatal("iterator should not be nil")
		}
		if iter.pageSize != 10 {
			t.Errorf("pageSize = %d, want 10", iter.pageSize)
		}
	})

	t.Run("with zero page size", func(t *testing.T) {
		iter := NewPageIterator[string](fetchFn, 0)
		if iter.pageSize != 20 {
			t.Errorf("pageSize = %d, want 20 (default)", iter.pageSize)
		}
	})

	t.Run("with negative page size", func(t *testing.T) {
		iter := NewPageIterator[string](fetchFn, -5)
		if iter.pageSize != 20 {
			t.Errorf("pageSize = %d, want 20 (default)", iter.pageSize)
		}
	})
}

func TestPageIteratorNext(t *testing.T) {
	t.Run("iterates through all items", func(t *testing.T) {
		// Mock data: 2 pages of 3 items each
		allItems := [][]string{
			{"item1", "item2", "item3"},
			{"item4", "item5"},
		}

		fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
			page := skip / limit
			if page >= len(allItems) {
				return nil, nil
			}

			items := allItems[page]
			result := make([]json.RawMessage, len(items))
			for i, item := range items {
				data, _ := json.Marshal(item)
				result[i] = data
			}
			return result, nil
		}

		iter := NewPageIterator[string](fetchFn, 3)

		var collected []string
		ctx := context.Background()
		for iter.Next(ctx) {
			collected = append(collected, iter.Value())
		}

		if err := iter.Err(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		expected := []string{"item1", "item2", "item3", "item4", "item5"}
		if len(collected) != len(expected) {
			t.Errorf("collected %d items, want %d", len(collected), len(expected))
		}
		for i, item := range collected {
			if item != expected[i] {
				t.Errorf("item[%d] = %q, want %q", i, item, expected[i])
			}
		}
	})

	t.Run("handles empty result", func(t *testing.T) {
		fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
			return nil, nil
		}

		iter := NewPageIterator[string](fetchFn, 10)

		if iter.Next(context.Background()) {
			t.Error("Next should return false for empty result")
		}
		if iter.Err() != nil {
			t.Errorf("Err should be nil: %v", iter.Err())
		}
	})

	t.Run("handles fetch error", func(t *testing.T) {
		expectedErr := errors.New("fetch failed")
		fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
			return nil, expectedErr
		}

		iter := NewPageIterator[string](fetchFn, 10)

		if iter.Next(context.Background()) {
			t.Error("Next should return false on error")
		}
		if iter.Err() != expectedErr {
			t.Errorf("Err = %v, want %v", iter.Err(), expectedErr)
		}
	})

	t.Run("handles JSON unmarshal error", func(t *testing.T) {
		fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
			// Return invalid JSON for string type
			return []json.RawMessage{[]byte(`{"not": "a string"}`)}, nil
		}

		iter := NewPageIterator[string](fetchFn, 10)

		if iter.Next(context.Background()) {
			t.Error("Next should return false on unmarshal error")
		}
		if iter.Err() == nil {
			t.Error("Err should not be nil on unmarshal error")
		}
	})
}

func TestPageIteratorReset(t *testing.T) {
	callCount := 0
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		callCount++
		if callCount <= 2 {
			data, _ := json.Marshal("item")
			return []json.RawMessage{data}, nil
		}
		return nil, nil
	}

	iter := NewPageIterator[string](fetchFn, 1)
	ctx := context.Background()

	// First iteration
	for iter.Next(ctx) {
	}

	// Reset and iterate again
	iter.Reset()
	callCount = 0

	var count int
	for iter.Next(ctx) {
		count++
	}

	if count != 2 {
		t.Errorf("after reset, collected %d items, want 2", count)
	}
}

func TestPageIteratorFirstPage(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip != 0 {
			t.Errorf("FirstPage should fetch with skip=0, got %d", skip)
		}
		items := make([]json.RawMessage, 3)
		for i := 0; i < 3; i++ {
			data, _ := json.Marshal(i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 3)
	page, err := iter.FirstPage(context.Background())
	if err != nil {
		t.Fatalf("FirstPage error: %v", err)
	}

	expected := []int{1, 2, 3}
	if len(page) != len(expected) {
		t.Errorf("page length = %d, want %d", len(page), len(expected))
	}
	for i, v := range page {
		if v != expected[i] {
			t.Errorf("page[%d] = %d, want %d", i, v, expected[i])
		}
	}
}

func TestPageIteratorAll(t *testing.T) {
	fetchCount := 0
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		fetchCount++
		if fetchCount > 2 {
			return nil, nil
		}
		items := make([]json.RawMessage, 2)
		for i := 0; i < 2; i++ {
			data, _ := json.Marshal(skip + i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 2)
	all, err := iter.All(context.Background())
	if err != nil {
		t.Fatalf("All error: %v", err)
	}

	expected := []int{1, 2, 3, 4}
	if len(all) != len(expected) {
		t.Errorf("all length = %d, want %d", len(all), len(expected))
	}
	for i, v := range all {
		if v != expected[i] {
			t.Errorf("all[%d] = %d, want %d", i, v, expected[i])
		}
	}
}

func TestPageIteratorTake(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		items := make([]json.RawMessage, limit)
		for i := 0; i < limit; i++ {
			data, _ := json.Marshal(skip + i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 5)
	taken, err := iter.Take(context.Background(), 3)
	if err != nil {
		t.Fatalf("Take error: %v", err)
	}

	if len(taken) != 3 {
		t.Errorf("taken length = %d, want 3", len(taken))
	}
	expected := []int{1, 2, 3}
	for i, v := range taken {
		if v != expected[i] {
			t.Errorf("taken[%d] = %d, want %d", i, v, expected[i])
		}
	}
}

func TestPageIteratorCollect(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip > 0 {
			return nil, nil
		}
		data, _ := json.Marshal("item")
		return []json.RawMessage{data}, nil
	}

	iter := NewPageIterator[string](fetchFn, 10)
	collected, err := iter.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect error: %v", err)
	}

	if len(collected) != 1 {
		t.Errorf("collected length = %d, want 1", len(collected))
	}
}

func TestPageIteratorForEach(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip > 0 {
			return nil, nil
		}
		items := make([]json.RawMessage, 3)
		for i := 0; i < 3; i++ {
			data, _ := json.Marshal(i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 10)

	var sum int
	err := iter.ForEach(context.Background(), func(item int) error {
		sum += item
		return nil
	})

	if err != nil {
		t.Fatalf("ForEach error: %v", err)
	}

	expected := 1 + 2 + 3
	if sum != expected {
		t.Errorf("sum = %d, want %d", sum, expected)
	}
}

func TestPageIteratorForEachWithError(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		items := make([]json.RawMessage, 3)
		for i := 0; i < 3; i++ {
			data, _ := json.Marshal(i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 10)

	expectedErr := errors.New("stop iteration")
	err := iter.ForEach(context.Background(), func(item int) error {
		if item == 2 {
			return expectedErr
		}
		return nil
	})

	if err != expectedErr {
		t.Errorf("ForEach error = %v, want %v", err, expectedErr)
	}
}

func TestPageIteratorFilter(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip > 0 {
			return nil, nil
		}
		items := make([]json.RawMessage, 5)
		for i := 0; i < 5; i++ {
			data, _ := json.Marshal(i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 10)
	filtered, err := iter.Filter(context.Background(), func(item int) bool {
		return item%2 == 0 // Keep even numbers
	})

	if err != nil {
		t.Fatalf("Filter error: %v", err)
	}

	expected := []int{2, 4}
	if len(filtered) != len(expected) {
		t.Errorf("filtered length = %d, want %d", len(filtered), len(expected))
	}
	for i, v := range filtered {
		if v != expected[i] {
			t.Errorf("filtered[%d] = %d, want %d", i, v, expected[i])
		}
	}
}

func TestPageIteratorValue(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		data, _ := json.Marshal("test-value")
		return []json.RawMessage{data}, nil
	}

	iter := NewPageIterator[string](fetchFn, 10)

	// Value before Next should return zero value
	if iter.Value() != "" {
		t.Errorf("Value before Next = %q, want empty", iter.Value())
	}

	ctx := context.Background()
	if iter.Next(ctx) {
		if iter.Value() != "test-value" {
			t.Errorf("Value = %q, want test-value", iter.Value())
		}
	}
}

func TestPageIteratorExhausted(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		// Return less than page size to mark as exhausted
		data, _ := json.Marshal("single")
		return []json.RawMessage{data}, nil
	}

	iter := NewPageIterator[string](fetchFn, 10)
	ctx := context.Background()

	if !iter.Next(ctx) {
		t.Error("First Next should return true")
	}

	// Should be exhausted now (only 1 item returned, less than page size of 10)
	if iter.Next(ctx) {
		t.Error("Second Next should return false (exhausted)")
	}
}

type testItem struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

func TestPageIteratorWithStruct(t *testing.T) {
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip > 0 {
			return nil, nil
		}
		items := []testItem{
			{ID: 1, Name: "first"},
			{ID: 2, Name: "second"},
		}
		result := make([]json.RawMessage, len(items))
		for i, item := range items {
			data, _ := json.Marshal(item)
			result[i] = data
		}
		return result, nil
	}

	iter := NewPageIterator[testItem](fetchFn, 10)
	all, err := iter.All(context.Background())
	if err != nil {
		t.Fatalf("All error: %v", err)
	}

	if len(all) != 2 {
		t.Errorf("all length = %d, want 2", len(all))
	}
	if all[0].ID != 1 || all[0].Name != "first" {
		t.Errorf("all[0] = %+v", all[0])
	}
	if all[1].ID != 2 || all[1].Name != "second" {
		t.Errorf("all[1] = %+v", all[1])
	}
}

func TestPageIteratorBuffering(t *testing.T) {
	// Test that items are properly buffered between calls
	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		if skip >= limit {
			return nil, nil
		}
		items := make([]json.RawMessage, limit)
		for i := 0; i < limit; i++ {
			data, _ := json.Marshal(skip + i + 1)
			items[i] = data
		}
		return items, nil
	}

	iter := NewPageIterator[int](fetchFn, 5)
	ctx := context.Background()

	// Iterate through first 3 items
	var items []int
	for i := 0; i < 3; i++ {
		if !iter.Next(ctx) {
			t.Fatalf("Next returned false at iteration %d", i)
		}
		items = append(items, iter.Value())
	}

	expected := []int{1, 2, 3}
	for i, v := range items {
		if v != expected[i] {
			t.Errorf("items[%d] = %d, want %d", i, v, expected[i])
		}
	}

	// Items 4 and 5 should still be in buffer
	if !iter.Next(ctx) {
		t.Error("Next should return true for buffered item 4")
	}
	if iter.Value() != 4 {
		t.Errorf("Value = %d, want 4", iter.Value())
	}
}
