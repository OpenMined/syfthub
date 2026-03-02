/**
 * useMention Hook
 *
 * Manages state and logic for @owner/slug mentions in text input.
 * Uses available data sources as the source of truth for owners and endpoints.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { MentionState, OwnerInfo } from '@/lib/mention-utils';
import type { ChatSource } from '@/lib/types';

import { getPublicEndpointOwners, getPublicEndpointsByOwner } from '@/lib/endpoint-utils';
import {
  filterEndpoints,
  filterOwners,
  getEndpointsByOwner,
  getUniqueOwners,
  parseMentionAtCursor,
  replaceMention
} from '@/lib/mention-utils';

// =============================================================================
// Types
// =============================================================================

export interface UseMentionOptions {
  /** Available data sources for mention autocomplete */
  sources: ChatSource[];
  /** Maximum results to show in popover (default: 8) */
  maxResults?: number;
}

export interface UseMentionReturn {
  // State
  /** Current mention state parsed from input */
  mentionState: MentionState;
  /** Highlighted index in the popover list */
  highlightedIndex: number;

  // Filtered lists for popovers
  /** Filtered owners for owner popover */
  filteredOwners: OwnerInfo[];
  /** Filtered endpoints for endpoint popover */
  filteredEndpoints: ChatSource[];

  // Popover visibility
  /** Whether to show owner selection popover */
  showOwnerPopover: boolean;
  /** Whether to show endpoint selection popover */
  showEndpointPopover: boolean;

  // Loading states for API fetches
  /** Whether owners are being fetched from the API */
  isLoadingOwners: boolean;
  /** Whether endpoints are being fetched from the API for the current owner */
  isLoadingEndpoints: boolean;

  // Actions
  /** Update mention state based on input value and cursor position */
  updateMentionState: (value: string, cursorPos: number) => void;
  /** Handle keyboard navigation in popover */
  handleKeyDown: (
    event: React.KeyboardEvent,
    value: string,
    cursorPos: number
  ) => {
    handled: boolean;
    newValue?: string;
    newCursorPos?: number;
    completedSource?: ChatSource;
  };
  /** Select an owner from the popover */
  selectOwner: (
    owner: string,
    value: string,
    cursorPos: number
  ) => { newValue: string; newCursorPos: number };
  /** Select an endpoint from the popover */
  selectEndpoint: (
    endpoint: ChatSource,
    value: string,
    cursorPos: number
  ) => { newValue: string; newCursorPos: number; completedSource: ChatSource };
  /** Reset mention state */
  reset: () => void;
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useMention({ sources, maxResults = 8 }: UseMentionOptions): UseMentionReturn {
  // Parse state from input (controlled by parent component)
  const [mentionState, setMentionState] = useState<MentionState>({
    phase: 'idle',
    startIndex: -1,
    ownerText: '',
    slugText: '',
    fullText: ''
  });

  const [highlightedIndex, setHighlightedIndex] = useState(0);

  // API-fetched data to supplement the local 100-item cache
  const [fetchedOwners, setFetchedOwners] = useState<OwnerInfo[]>([]);
  const [isLoadingOwners, setIsLoadingOwners] = useState(false);
  const [fetchedEndpoints, setFetchedEndpoints] = useState<ChatSource[]>([]);
  const [isLoadingEndpoints, setIsLoadingEndpoints] = useState(false);
  // Per-owner endpoint cache — useRef so cache updates don't trigger re-renders
  const endpointCacheReference = useRef<Map<string, ChatSource[]>>(new Map());

  // Fetch all owners from the API on mount so the owner dropdown shows every owner,
  // not just those present in the 100-item local cache.
  useEffect(() => {
    let cancelled = false;
    setIsLoadingOwners(true);

    void getPublicEndpointOwners().then((result) => {
      if (!cancelled) {
        setFetchedOwners(result);
        setIsLoadingOwners(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // Merge local owners with API-fetched owners, deduplicating by username.
  // API data takes precedence for endpoint counts (accurate totals).
  const allOwners = useMemo(() => {
    const merged = new Map<string, OwnerInfo>();
    for (const owner of getUniqueOwners(sources)) {
      merged.set(owner.username, owner);
    }
    for (const owner of fetchedOwners) {
      merged.set(owner.username, owner);
    }
    return [...merged.values()].toSorted((a, b) => b.endpointCount - a.endpointCount);
  }, [sources, fetchedOwners]);

  // When entering slug phase for an owner, fetch all that owner's endpoints from
  // the API so the dropdown is not limited to the 100-item local cache.
  useEffect(() => {
    if (mentionState.phase !== 'slug' || !mentionState.ownerText) {
      setFetchedEndpoints([]);
      return;
    }

    const owner = mentionState.ownerText;

    // Cache hit — use stored results immediately, no loading state needed
    const cached = endpointCacheReference.current.get(owner);
    if (cached) {
      setFetchedEndpoints(cached);
      return;
    }

    let cancelled = false;
    setIsLoadingEndpoints(true);

    void getPublicEndpointsByOwner(owner).then((result) => {
      if (!cancelled) {
        endpointCacheReference.current.set(owner, result);
        setFetchedEndpoints(result);
        setIsLoadingEndpoints(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [mentionState.phase, mentionState.ownerText]);

  // Filter owners based on typed text
  const filteredOwners = useMemo(() => {
    if (mentionState.phase !== 'owner') return [];
    return filterOwners(allOwners, mentionState.ownerText, maxResults);
  }, [allOwners, mentionState.phase, mentionState.ownerText, maxResults]);

  // Merge local and API-fetched endpoints for the selected owner, deduplicating by full_path.
  // API results come first (complete set); local results fill in any gaps.
  const ownerEndpoints = useMemo(() => {
    if (mentionState.phase !== 'slug' || !mentionState.ownerText) return [];
    const seen = new Set<string>();
    const merged: ChatSource[] = [];
    for (const ep of fetchedEndpoints) {
      if (ep.type !== 'data_source' && ep.type !== 'model_data_source') continue;
      const key = ep.full_path ?? (ep.owner_username ?? '') + '/' + ep.slug;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(ep);
      }
    }
    for (const ep of getEndpointsByOwner(sources, mentionState.ownerText)) {
      const key = ep.full_path ?? (ep.owner_username ?? '') + '/' + ep.slug;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(ep);
      }
    }
    return merged;
  }, [sources, mentionState.phase, mentionState.ownerText, fetchedEndpoints]);

  // Filter endpoints based on typed text
  const filteredEndpoints = useMemo(() => {
    if (mentionState.phase !== 'slug') return [];
    return filterEndpoints(ownerEndpoints, mentionState.slugText, maxResults);
  }, [ownerEndpoints, mentionState.phase, mentionState.slugText, maxResults]);

  // Popover visibility — keep endpoint popover open while loading so the spinner shows
  const showOwnerPopover =
    mentionState.phase === 'owner' && (filteredOwners.length > 0 || isLoadingOwners);
  const showEndpointPopover =
    mentionState.phase === 'slug' && (filteredEndpoints.length > 0 || isLoadingEndpoints);

  // Update mention state from input
  const updateMentionState = useCallback(
    (value: string, cursorPos: number) => {
      const newState = parseMentionAtCursor(value, cursorPos);
      setMentionState(newState);

      // Reset highlighted index when state changes
      if (newState.phase !== mentionState.phase) {
        setHighlightedIndex(0);
      }
    },
    [mentionState.phase]
  );

  // Select an owner - replaces @partial with @owner/
  const selectOwner = useCallback(
    (
      owner: string,
      value: string,
      cursorPos: number
    ): { newValue: string; newCursorPos: number } => {
      if (mentionState.startIndex === -1) {
        return { newValue: value, newCursorPos: cursorPos };
      }

      const replacement = `@${owner}/`;
      const result = replaceMention(value, mentionState.startIndex, cursorPos, replacement);

      // Update state to slug phase
      setMentionState({
        phase: 'slug',
        startIndex: mentionState.startIndex,
        ownerText: owner,
        slugText: '',
        fullText: replacement
      });
      setHighlightedIndex(0);

      return result;
    },
    [mentionState.startIndex]
  );

  // Select an endpoint - replaces @owner/partial with @owner/slug and completes
  const selectEndpoint = useCallback(
    (
      endpoint: ChatSource,
      value: string,
      cursorPos: number
    ): { newValue: string; newCursorPos: number; completedSource: ChatSource } => {
      if (mentionState.startIndex === -1) {
        return { newValue: value, newCursorPos: cursorPos, completedSource: endpoint };
      }

      const replacement = `@${mentionState.ownerText}/${endpoint.slug} `;
      const result = replaceMention(value, mentionState.startIndex, cursorPos, replacement);

      // Reset to idle after completion
      setMentionState({
        phase: 'idle',
        startIndex: -1,
        ownerText: '',
        slugText: '',
        fullText: ''
      });
      setHighlightedIndex(0);

      return { ...result, completedSource: endpoint };
    },
    [mentionState.startIndex, mentionState.ownerText]
  );

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (
      event: React.KeyboardEvent,
      value: string,
      cursorPos: number
    ): {
      handled: boolean;
      newValue?: string;
      newCursorPos?: number;
      completedSource?: ChatSource;
    } => {
      // Only handle keys when popover is visible
      if (!showOwnerPopover && !showEndpointPopover) {
        return { handled: false };
      }

      const currentList = showOwnerPopover ? filteredOwners : filteredEndpoints;
      const listLength = currentList.length;

      switch (event.key) {
        case 'ArrowDown': {
          event.preventDefault();
          setHighlightedIndex((previous) => (previous + 1) % listLength);
          return { handled: true };
        }

        case 'ArrowUp': {
          event.preventDefault();
          setHighlightedIndex((previous) => (previous - 1 + listLength) % listLength);
          return { handled: true };
        }

        case 'Tab':
        case 'Enter': {
          event.preventDefault();

          if (showOwnerPopover && filteredOwners[highlightedIndex]) {
            const result = selectOwner(filteredOwners[highlightedIndex].username, value, cursorPos);
            return { handled: true, ...result };
          }

          if (showEndpointPopover && filteredEndpoints[highlightedIndex]) {
            const result = selectEndpoint(filteredEndpoints[highlightedIndex], value, cursorPos);
            return { handled: true, ...result };
          }

          return { handled: true };
        }

        case 'Escape': {
          event.preventDefault();
          setMentionState({
            phase: 'idle',
            startIndex: -1,
            ownerText: '',
            slugText: '',
            fullText: ''
          });
          return { handled: true };
        }

        default: {
          return { handled: false };
        }
      }
    },
    [
      showOwnerPopover,
      showEndpointPopover,
      filteredOwners,
      filteredEndpoints,
      highlightedIndex,
      selectOwner,
      selectEndpoint
    ]
  );

  // Reset state
  const reset = useCallback(() => {
    setMentionState({
      phase: 'idle',
      startIndex: -1,
      ownerText: '',
      slugText: '',
      fullText: ''
    });
    setHighlightedIndex(0);
  }, []);

  return {
    mentionState,
    highlightedIndex,
    filteredOwners,
    filteredEndpoints,
    showOwnerPopover,
    showEndpointPopover,
    isLoadingOwners,
    isLoadingEndpoints,
    updateMentionState,
    handleKeyDown,
    selectOwner,
    selectEndpoint,
    reset
  };
}
