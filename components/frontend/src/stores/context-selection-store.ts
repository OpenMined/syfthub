import type { ChatSource } from '@/lib/types';

import { create } from 'zustand';

interface ContextSelectionState {
  /** Map of selected source ID → ChatSource details */
  selectedSources: Map<string, ChatSource>;
  /** Add a source to the context */
  addSource: (source: ChatSource) => void;
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

  addSource: (source) => {
    set((state) => {
      const next = new Map(state.selectedSources);
      next.set(source.id, source);
      return { selectedSources: next };
    });
  },

  removeSource: (id) => {
    set((state) => {
      const next = new Map(state.selectedSources);
      next.delete(id);
      return { selectedSources: next };
    });
  },

  toggleSource: (source) => {
    set((state) => {
      const next = new Map(state.selectedSources);
      if (next.has(source.id)) {
        next.delete(source.id);
      } else {
        next.set(source.id, source);
      }
      return { selectedSources: next };
    });
  },

  isSelected: (id) => get().selectedSources.has(id),

  count: () => get().selectedSources.size,

  getSourcesArray: () => [...get().selectedSources.values()],

  clearSources: () => {
    set({ selectedSources: new Map() });
  }
}));
