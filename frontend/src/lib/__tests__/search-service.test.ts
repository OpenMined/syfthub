import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createMockSearchableChatSource } from '@/test/mocks/fixtures';

import {
  categorizeResults,
  createDebouncedSearch,
  filterByRelevance,
  hasHighRelevanceResults,
  searchEndpoints
} from '../search-service';

// ============================================================================
// filterByRelevance
// ============================================================================

describe('filterByRelevance', () => {
  const results = [
    createMockSearchableChatSource({ slug: 'high', relevance_score: 0.8 }),
    createMockSearchableChatSource({ slug: 'mid', relevance_score: 0.5 }),
    createMockSearchableChatSource({ slug: 'low', relevance_score: 0.2 })
  ];

  it('filters results below threshold', () => {
    const filtered = filterByRelevance(results, 0.5);
    expect(filtered).toHaveLength(2);
    expect(filtered.map((r) => r.slug)).toEqual(['high', 'mid']);
  });

  it('returns empty for very high threshold', () => {
    const filtered = filterByRelevance(results, 0.9);
    expect(filtered).toHaveLength(0);
  });

  it('returns all for zero threshold', () => {
    const filtered = filterByRelevance(results, 0);
    expect(filtered).toHaveLength(3);
  });

  it('handles empty input', () => {
    expect(filterByRelevance([], 0.5)).toEqual([]);
  });
});

// ============================================================================
// categorizeResults
// ============================================================================

describe('categorizeResults', () => {
  it('separates results at 0.5 threshold', () => {
    const results = [
      createMockSearchableChatSource({ relevance_score: 0.7 }),
      createMockSearchableChatSource({ relevance_score: 0.3 }),
      createMockSearchableChatSource({ relevance_score: 0.5 })
    ];
    const { highRelevance } = categorizeResults(results);
    expect(highRelevance).toHaveLength(2);
  });

  it('returns empty for no results', () => {
    const { highRelevance } = categorizeResults([]);
    expect(highRelevance).toEqual([]);
  });
});

// ============================================================================
// hasHighRelevanceResults
// ============================================================================

describe('hasHighRelevanceResults', () => {
  it('returns true if any result >= 0.5', () => {
    const results = [createMockSearchableChatSource({ relevance_score: 0.6 })];
    expect(hasHighRelevanceResults(results)).toBe(true);
  });

  it('returns false if all results < 0.5', () => {
    const results = [createMockSearchableChatSource({ relevance_score: 0.3 })];
    expect(hasHighRelevanceResults(results)).toBe(false);
  });

  it('returns false for empty results', () => {
    expect(hasHighRelevanceResults([])).toBe(false);
  });
});

// ============================================================================
// createDebouncedSearch
// ============================================================================

describe('createDebouncedSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Mock fetch for debounced search (searchEndpoints uses fetch)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [], total: 0, query: 'test' })
      })
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('cancels pending search and returns empty', async () => {
    const { search, cancel } = createDebouncedSearch(300);
    const promise = search('test query');
    cancel();
    const results = await promise;
    expect(results).toEqual([]);
  });

  it('returns cancel function', () => {
    const { cancel } = createDebouncedSearch(300);
    expect(typeof cancel).toBe('function');
  });
});

// ============================================================================
// searchEndpoints
// ============================================================================

describe('searchEndpoints', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns empty for short query', async () => {
    const results = await searchEndpoints('ab');
    expect(results).toEqual([]);
  });

  it('returns empty for empty query', async () => {
    const results = await searchEndpoints('');
    expect(results).toEqual([]);
  });

  it('calls fetch and returns mapped results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [
            {
              name: 'Test',
              slug: 'test',
              description: 'A test endpoint',
              type: 'data_source',
              owner_username: 'alice',
              contributors_count: 1,
              version: '1.0',
              readme: 'readme',
              tags: ['ai'],
              stars_count: 5,
              policies: [],
              connect: [],
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              relevance_score: 0.8
            }
          ],
          total: 1,
          query: 'test query'
        })
      })
    );

    const results = await searchEndpoints('test query');
    expect(results).toHaveLength(1);
    expect(results[0]?.slug).toBe('test');
    expect(results[0]?.relevance_score).toBe(0.8);
    expect(results[0]?.full_path).toBe('alice/test');
  });

  it('returns empty for 422 response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        text: async () => 'Validation error'
      })
    );

    const results = await searchEndpoints('test query');
    expect(results).toEqual([]);
  });

  it('returns empty on network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network failure')));

    const results = await searchEndpoints('test query');
    expect(results).toEqual([]);
  });

  it('filters by min_score option', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [
            {
              name: 'High',
              slug: 'high',
              description: '',
              type: 'data_source',
              owner_username: 'a',
              contributors_count: 0,
              version: '1.0',
              readme: '',
              tags: [],
              stars_count: 0,
              policies: [],
              connect: [],
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              relevance_score: 0.9
            },
            {
              name: 'Low',
              slug: 'low',
              description: '',
              type: 'data_source',
              owner_username: 'b',
              contributors_count: 0,
              version: '1.0',
              readme: '',
              tags: [],
              stars_count: 0,
              policies: [],
              connect: [],
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              relevance_score: 0.2
            }
          ],
          total: 2,
          query: 'test'
        })
      })
    );

    const results = await searchEndpoints('test query', { min_score: 0.5 });
    expect(results).toHaveLength(1);
    expect(results[0]?.slug).toBe('high');
  });
});
