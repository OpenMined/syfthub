/**
 * useModels Hook
 *
 * Centralized hook for model fetching.
 * Selection state is managed separately by useModelSelectionStore.
 */
import { useCallback, useEffect, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { getChatModels, getGuestAccessibleModels } from '@/lib/endpoint-utils';
import { useModelSelectionStore } from '@/stores/model-selection-store';

/** Username to prioritize for default model selection */
const PREFERRED_MODEL_OWNER = 'openmined-models';

/**
 * Get a unique identifier for a model that distinguishes models with the same name
 * but different owners. Uses full_path (owner/slug) when available, otherwise
 * constructs it from owner_username and slug.
 */
function getModelUniqueId(model: ChatSource): string {
  return model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;
}

/**
 * Find the preferred model for auto-selection.
 * Prioritizes models from the preferred owner, falls back to first model.
 */
function findPreferredModel(models: ChatSource[]): ChatSource | undefined {
  const preferredModel = models.find((model) => model.owner_username === PREFERRED_MODEL_OWNER);
  return preferredModel ?? models[0];
}

export interface UseModelsOptions {
  /** Initial model to pre-select (e.g., from navigation state) */
  initialModel?: ChatSource | null;
  /** Whether to auto-select the first model if none selected (default: true) */
  autoSelectFirst?: boolean;
  /** Maximum number of models to fetch (default: 20) */
  limit?: number;
}

export interface UseModelsReturn {
  /** Available models from the backend */
  models: ChatSource[];
  /** Currently selected model (from Zustand store) */
  selectedModel: ChatSource | null;
  /** Update the selected model (writes to Zustand store) */
  setSelectedModel: (model: ChatSource | null) => void;
  /** Whether models are currently loading */
  isLoading: boolean;
  /** Reload models from the backend */
  refresh: () => Promise<void>;
}

/**
 * Hook for managing model fetching and selection.
 *
 * Selection state is persisted in the useModelSelectionStore Zustand store,
 * making it accessible across all components without prop drilling.
 *
 * @example
 * ```tsx
 * const { models, selectedModel, setSelectedModel, isLoading } = useModels();
 * ```
 */
export function useModels(options: UseModelsOptions = {}): UseModelsReturn {
  const { initialModel = null, autoSelectFirst = true, limit = 20 } = options;

  const { user } = useAuth();
  const isAuthenticated = !!user;

  const [models, setModels] = useState<ChatSource[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const { selectedModel, setSelectedModel } = useModelSelectionStore();

  const loadModels = useCallback(async () => {
    setIsLoading(true);

    try {
      // Use guest-accessible models for unauthenticated users
      const fetchedModels = isAuthenticated
        ? await getChatModels(limit)
        : await getGuestAccessibleModels(limit);

      // If initialModel was provided but not in fetched list, prepend it
      // Use full_path (owner/slug) for comparison to correctly handle models with same slug but different owners
      let updatedModels = fetchedModels;
      if (
        initialModel &&
        !fetchedModels.some((m) => getModelUniqueId(m) === getModelUniqueId(initialModel))
      ) {
        updatedModels = [initialModel, ...fetchedModels];
      }

      setModels(updatedModels);

      // Auto-select preferred model if enabled and no current selection
      // Prioritizes models from 'openmined-models' owner, falls back to first model
      const currentSelection = useModelSelectionStore.getState().selectedModel;
      if (currentSelection === null && autoSelectFirst && updatedModels.length > 0) {
        const preferredModel = findPreferredModel(updatedModels);
        if (preferredModel) {
          setSelectedModel(preferredModel);
        }
      }
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      setIsLoading(false);
    }
  }, [initialModel, autoSelectFirst, limit, isAuthenticated, setSelectedModel]);

  // Load models on mount
  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      await loadModels();
      if (!isMounted) return;
    };

    void load();

    return () => {
      isMounted = false;
    };
  }, [loadModels]);

  const refresh = useCallback(async () => {
    await loadModels();
  }, [loadModels]);

  return {
    models,
    selectedModel,
    setSelectedModel,
    isLoading,
    refresh
  };
}
