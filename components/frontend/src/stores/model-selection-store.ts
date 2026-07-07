import type { ChatSource } from '@/lib/types';

import { create } from 'zustand';

interface ModelSelectionState {
  selectedModel: ChatSource | null;
  setSelectedModel: (model: ChatSource | null) => void;
}

export const useModelSelectionStore = create<ModelSelectionState>((set) => ({
  selectedModel: null,
  setSelectedModel: (model) => {
    set({ selectedModel: model });
  }
}));
