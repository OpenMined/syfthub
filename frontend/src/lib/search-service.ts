/**
 * Search Service - RAG-powered semantic search for endpoints
 *
 * This module provides functions for searching endpoints using the
 * backend's RAG (Retrieval-Augmented Generation) semantic search API.
 */

import type { ChatSource, EndpointType } from './types';

// ============================================================================
// Types
// ============================================================================

/**
 * Search result from the backend API with relevance score.
 */
export interface EndpointSearchResult {
  name: string;
  slug: string;
  description: string;
  type: EndpointType;
  owner_username: string;
  contributors_count: number;
  version: string;
  readme: string;
  tags: string[];
  stars_count: number;
  policies: unknown[];
  connect: unknown[];
  created_at: string;
  updated_at: string;
  relevance_score: number;
}

/**
 * Response from the search API.
 */
export interface EndpointSearchResponse {
  results: EndpointSearchResult[];
  total: number;
  query: string;
}

/**
 * Extended ChatSource with relevance score for search results.
 */
export interface SearchableChatSource extends ChatSource {
  /** Relevance score from semantic search (0.0-1.0) */
  relevance_score: number;
}

/**
 * Search options for filtering and limiting results.
 */
export interface SearchOptions {
  /** Maximum number of results to return (default: 10) */
  top_k?: number;
  /** Filter by endpoint type */
  type?: EndpointType;
  /** Minimum relevance score threshold (default: 0.0) */
  min_score?: number;
}

// ============================================================================
// Constants
// ============================================================================

/** Minimum relevance score for results to be shown (0.5 threshold) */
export const HIGH_RELEVANCE_THRESHOLD = 0.5;

/** Minimum query length to trigger search */
export const MIN_QUERY_LENGTH = 3;

/** Default number of results to fetch */
export const DEFAULT_TOP_K = 10;

// ============================================================================
// Search Functions
// ============================================================================

/**
 * Search endpoints using semantic search.
 *
 * @param query - Natural language search query
 * @param options - Search options (top_k, type filter, min_score)
 * @returns Promise resolving to search results with relevance scores
 */
export async function searchEndpoints(
  query: string,
  options: SearchOptions = {}
): Promise<SearchableChatSource[]> {
  const { top_k = DEFAULT_TOP_K, type, min_score = 0 } = options;

  // Skip search for very short queries
  if (!query || query.trim().length < MIN_QUERY_LENGTH) {
    return [];
  }

  try {
    const requestBody: { query: string; top_k: number; type?: EndpointType } = {
      query: query.trim(),
      top_k
    };

    if (type) {
      requestBody.type = type;
    }

    const response = await fetch('/api/v1/endpoints/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      // Handle specific error cases
      if (response.status === 422) {
        console.warn('Search validation error:', await response.text());
        return [];
      }
      throw new Error(`Search failed: ${String(response.status)} ${response.statusText}`);
    }

    const data = (await response.json()) as EndpointSearchResponse;

    // Convert results to ChatSource format with relevance scores
    const results: SearchableChatSource[] = data.results
      .filter((result) => result.relevance_score >= min_score)
      .map((result) => ({
        // Map endpoint fields to ChatSource
        id: result.slug,
        name: result.name,
        slug: result.slug,
        description: result.description,
        type: result.type,
        tags: result.tags,
        status: 'active' as const, // Search results are assumed active
        updated: formatRelativeTime(new Date(result.updated_at)),
        stars_count: result.stars_count,
        version: result.version,
        readme: result.readme,
        contributors_count: result.contributors_count,
        owner_username: result.owner_username,
        full_path: `${result.owner_username}/${result.slug}`,
        // Include raw connection/policy data
        connections: result.connect as ChatSource['connections'],
        policies: result.policies as ChatSource['policies'],
        // Search-specific field
        relevance_score: result.relevance_score
      }));

    return results;
  } catch (error) {
    console.error('Search request failed:', error);
    return [];
  }
}

/**
 * Search for data sources only.
 *
 * @param query - Natural language search query
 * @param options - Search options (top_k, min_score)
 * @returns Promise resolving to data source results with relevance scores
 */
export async function searchDataSources(
  query: string,
  options: Omit<SearchOptions, 'type'> = {}
): Promise<SearchableChatSource[]> {
  return searchEndpoints(query, { ...options, type: 'data_source' });
}

/**
 * Search for models only.
 *
 * @param query - Natural language search query
 * @param options - Search options (top_k, min_score)
 * @returns Promise resolving to model results with relevance scores
 */
export async function searchModels(
  query: string,
  options: Omit<SearchOptions, 'type'> = {}
): Promise<SearchableChatSource[]> {
  return searchEndpoints(query, { ...options, type: 'model' });
}

/**
 * Filter search results by relevance threshold.
 *
 * @param results - Search results with relevance scores
 * @param threshold - Minimum relevance score
 * @returns Filtered results
 */
export function filterByRelevance(
  results: SearchableChatSource[],
  threshold: number
): SearchableChatSource[] {
  return results.filter((result) => result.relevance_score >= threshold);
}

/**
 * Filter search results to only include high relevance matches (>= 0.5 threshold).
 *
 * Results below the threshold are filtered out completely - they are not shown
 * to the user. If no results meet the threshold, the UI should show a "no match"
 * message instead.
 *
 * @param results - Search results with relevance scores
 * @returns Object with high relevance result array (only results >= 0.5)
 */
export function categorizeResults(results: SearchableChatSource[]): {
  highRelevance: SearchableChatSource[];
} {
  const highRelevance = results.filter(
    (result) => result.relevance_score >= HIGH_RELEVANCE_THRESHOLD
  );

  return { highRelevance };
}

/**
 * Check if search results contain any high-relevance matches.
 *
 * @param results - Search results with relevance scores
 * @returns True if at least one result has high relevance
 */
export function hasHighRelevanceResults(results: SearchableChatSource[]): boolean {
  return results.some((result) => result.relevance_score >= HIGH_RELEVANCE_THRESHOLD);
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format a date as a relative time string.
 */
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));

  if (diffInHours < 1) return 'just now';
  if (diffInHours < 24) return `${String(diffInHours)} hour${diffInHours === 1 ? '' : 's'} ago`;

  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 7) return `${String(diffInDays)} day${diffInDays === 1 ? '' : 's'} ago`;

  const diffInWeeks = Math.floor(diffInDays / 7);
  if (diffInDays < 30) return `${String(diffInWeeks)} week${diffInWeeks === 1 ? '' : 's'} ago`;

  const diffInMonths = Math.floor(diffInDays / 30);
  return `${String(diffInMonths)} month${diffInMonths === 1 ? '' : 's'} ago`;
}

/**
 * Create a debounced version of the search function.
 *
 * @param delay - Debounce delay in milliseconds
 * @returns Debounced search function
 */
export function createDebouncedSearch(delay = 300): {
  search: (query: string, options?: SearchOptions) => Promise<SearchableChatSource[]>;
  cancel: () => void;
} {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let pendingResolve: ((results: SearchableChatSource[]) => void) | null = null;

  // Extract the async search execution to reduce nesting depth
  const executeSearchAndResolve = async (
    query: string,
    options: SearchOptions | undefined,
    resolveCallback: (results: SearchableChatSource[]) => void
  ) => {
    const results = await searchEndpoints(query, options);
    if (pendingResolve === resolveCallback) {
      resolveCallback(results);
    }
  };

  const search = (query: string, options?: SearchOptions): Promise<SearchableChatSource[]> => {
    // Cancel any pending search
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }

    return new Promise((resolve) => {
      pendingResolve = resolve;
      timeoutId = setTimeout(() => void executeSearchAndResolve(query, options, resolve), delay);
    });
  };

  const cancel = () => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
    if (pendingResolve !== null) {
      pendingResolve([]);
      pendingResolve = null;
    }
  };

  return { search, cancel };
}
