/**
 * useMention Hook
 *
 * Manages state and logic for @owner/slug mentions in text input.
 * Uses available data sources as the source of truth for owners and endpoints.
 */
import { useCallback, useMemo, useState } from 'react';

import type { MentionState, OwnerInfo } from '@/lib/mention-utils';
import type { ChatSource } from '@/lib/types';

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

  // Get unique owners from available sources
  const allOwners = useMemo(() => getUniqueOwners(sources), [sources]);

  // Filter owners based on typed text
  const filteredOwners = useMemo(() => {
    if (mentionState.phase !== 'owner') return [];
    return filterOwners(allOwners, mentionState.ownerText, maxResults);
  }, [allOwners, mentionState.phase, mentionState.ownerText, maxResults]);

  // Get endpoints for selected owner
  const ownerEndpoints = useMemo(() => {
    if (mentionState.phase !== 'slug' || !mentionState.ownerText) return [];
    return getEndpointsByOwner(sources, mentionState.ownerText);
  }, [sources, mentionState.phase, mentionState.ownerText]);

  // Filter endpoints based on typed text
  const filteredEndpoints = useMemo(() => {
    if (mentionState.phase !== 'slug') return [];
    return filterEndpoints(ownerEndpoints, mentionState.slugText, maxResults);
  }, [ownerEndpoints, mentionState.phase, mentionState.slugText, maxResults]);

  // Popover visibility
  const showOwnerPopover = mentionState.phase === 'owner' && filteredOwners.length > 0;
  const showEndpointPopover = mentionState.phase === 'slug' && filteredEndpoints.length > 0;

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
    updateMentionState,
    handleKeyDown,
    selectOwner,
    selectEndpoint,
    reset
  };
}
