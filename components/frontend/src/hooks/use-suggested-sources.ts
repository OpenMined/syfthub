/**
 * useSuggestedSources Hook
 *
 * Custom hook that provides debounced semantic search suggestions for data sources
 * based on the user's current input text. Uses character-count-based triggering
 * (every N characters of change) combined with time-based debouncing to balance
 * responsiveness with API efficiency.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { SearchableChatSource } from '@/lib/search-service';

import { categorizeResults, MIN_QUERY_LENGTH, searchDataSources } from '@/lib/search-service';

// =============================================================================
// Types
// =============================================================================

export interface UseSuggestedSourcesOptions {
  /** Current query text from the input field */
  query: string;
  /** Set of source IDs already selected in context (excluded from suggestions) */
  selectedSourceIds: Set<string>;
  /** Number of characters of change before triggering a new search (default: 10) */
  charThreshold?: number;
  /** Debounce delay in milliseconds after threshold is met (default: 300) */
  debounceMs?: number;
  /** Maximum number of results to fetch (default: 5) */
  maxResults?: number;
  /** Whether the hook is enabled (set false during active workflow) */
  enabled?: boolean;
}

export interface UseSuggestedSourcesReturn {
  /** Filtered suggestions (excludes already-selected sources) */
  suggestions: SearchableChatSource[];
  /** Whether a search request is currently in flight */
  isSearching: boolean;
  /** Manually clear all suggestions and reset state */
  clearSuggestions: () => void;
}

// =============================================================================
// Hook
// =============================================================================

export function useSuggestedSources({
  query,
  selectedSourceIds,
  charThreshold = 10,
  debounceMs = 300,
  maxResults = 5,
  enabled = true
}: UseSuggestedSourcesOptions): UseSuggestedSourcesReturn {
  // Raw search results (before filtering out selected sources)
  const [rawResults, setRawResults] = useState<SearchableChatSource[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Mutable refs for tracking state across renders without causing re-renders
  const lastSearchedAtLengthReference = useRef<number>(0);
  const debounceTimerReference = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestCounterReference = useRef<number>(0);

  // Cancel any pending debounce timer
  const cancelTimer = useCallback(() => {
    if (debounceTimerReference.current !== null) {
      clearTimeout(debounceTimerReference.current);
      debounceTimerReference.current = null;
    }
  }, []);

  // Clear suggestions and reset tracking state
  const clearSuggestions = useCallback(() => {
    cancelTimer();
    setRawResults([]);
    setIsSearching(false);
    lastSearchedAtLengthReference.current = 0;
  }, [cancelTimer]);

  // Main effect: watch query changes and trigger search when threshold met
  useEffect(() => {
    // Disabled or query too short — clear everything
    if (!enabled || query.trim().length < MIN_QUERY_LENGTH) {
      cancelTimer();
      setRawResults([]);
      setIsSearching(false);
      lastSearchedAtLengthReference.current = 0;
      return;
    }

    // Check if enough characters have changed since last search
    const delta = Math.abs(query.length - lastSearchedAtLengthReference.current);
    if (delta < charThreshold) {
      return;
    }

    // Threshold met — start debounce timer
    cancelTimer();

    const currentRequest = ++requestCounterReference.current;
    const querySnapshot = query.trim();

    debounceTimerReference.current = setTimeout(() => {
      setIsSearching(true);

      void searchDataSources(querySnapshot, { top_k: maxResults }).then((results) => {
        // Only apply results if this is still the latest request
        if (requestCounterReference.current === currentRequest) {
          const { highRelevance } = categorizeResults(results);
          setRawResults(highRelevance);
          setIsSearching(false);
          lastSearchedAtLengthReference.current = query.length;
        }
      });
    }, debounceMs);

    // Cleanup: cancel timer on unmount or dependency change
    return cancelTimer;
  }, [query, enabled, charThreshold, debounceMs, maxResults, cancelTimer]);

  // Filter out already-selected sources reactively
  const suggestions = useMemo(
    () => rawResults.filter((result) => !selectedSourceIds.has(result.id)),
    [rawResults, selectedSourceIds]
  );

  return { suggestions, isSearching, clearSuggestions };
}
