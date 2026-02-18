import type { ChatSource } from '@/lib/types';

import { create } from 'zustand';

interface ContextSelectionState {
  /** Map of selected source ID → ChatSource details */
  selectedSources: Map<string, ChatSource>;
  /** Set of source IDs that were added via @mentions (vs + button) */
  mentionAddedIds: Set<string>;
  /** Add a source to the context (via + button or other means) */
  addSource: (source: ChatSource) => void;
  /** Add a source via @mention - tracks it for sync */
  addMentionSource: (source: ChatSource) => void;
  /** Sync mention sources - removes mention-added sources not in the given set */
  syncMentionSources: (presentIds: Set<string>) => void;
  /** Remove a source from the context by ID */
  removeSource: (id: string) => void;
  /** Toggle a source in/out of the context */
  toggleSource: (source: ChatSource) => void;
  /** Check if a source is selected */
  isSelected: (id: string) => boolean;
  /** Get the count of selected sources */
  count: () => number;
  /** Get selected sources as an array */
  getSourcesArray: () => ChatSource[];
  /** Clear all selected sources */
  clearSources: () => void;
}

export const useContextSelectionStore = create<ContextSelectionState>((set, get) => ({
  selectedSources: new Map(),
  mentionAddedIds: new Set(),

  addSource: (source) => {
    set((state) => {
      const next = new Map(state.selectedSources);
      next.set(source.id, source);
      return { selectedSources: next };
    });
  },

  addMentionSource: (source) => {
    set((state) => {
      const nextSources = new Map(state.selectedSources);
      const nextMentionIds = new Set(state.mentionAddedIds);
      nextSources.set(source.id, source);
      nextMentionIds.add(source.id);
      return { selectedSources: nextSources, mentionAddedIds: nextMentionIds };
    });
  },

  syncMentionSources: (presentIds) => {
    set((state) => {
      // Find mention-added sources that are no longer in the text
      const toRemove: string[] = [];
      for (const id of state.mentionAddedIds) {
        if (!presentIds.has(id)) {
          toRemove.push(id);
        }
      }

      // If nothing to remove, no state change needed
      if (toRemove.length === 0) {
        return state;
      }

      // Remove stale mention sources
      const nextSources = new Map(state.selectedSources);
      const nextMentionIds = new Set(state.mentionAddedIds);
      for (const id of toRemove) {
        nextSources.delete(id);
        nextMentionIds.delete(id);
      }

      return { selectedSources: nextSources, mentionAddedIds: nextMentionIds };
    });
  },

  removeSource: (id) => {
    set((state) => {
      const nextSources = new Map(state.selectedSources);
      const nextMentionIds = new Set(state.mentionAddedIds);
      nextSources.delete(id);
      nextMentionIds.delete(id); // Also remove from mention tracking if present
      return { selectedSources: nextSources, mentionAddedIds: nextMentionIds };
    });
  },

  toggleSource: (source) => {
    set((state) => {
      const nextSources = new Map(state.selectedSources);
      const nextMentionIds = new Set(state.mentionAddedIds);
      if (nextSources.has(source.id)) {
        nextSources.delete(source.id);
        nextMentionIds.delete(source.id);
      } else {
        nextSources.set(source.id, source);
      }
      return { selectedSources: nextSources, mentionAddedIds: nextMentionIds };
    });
  },

  isSelected: (id) => get().selectedSources.has(id),

  count: () => get().selectedSources.size,

  getSourcesArray: () => [...get().selectedSources.values()],

  clearSources: () => {
    set({ selectedSources: new Map(), mentionAddedIds: new Set() });
  }
}));
