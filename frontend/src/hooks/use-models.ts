/**
 * useModels Hook
 *
 * Centralized hook for model fetching and selection state.
 * Used by both Hero and ChatView to eliminate duplicate model management.
 */
import { useCallback, useEffect, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { getChatModels, getGuestAccessibleModels } from '@/lib/endpoint-utils';

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
  /** Currently selected model */
  selectedModel: ChatSource | null;
  /** Update the selected model */
  setSelectedModel: (model: ChatSource | null) => void;
  /** Whether models are currently loading */
  isLoading: boolean;
  /** Reload models from the backend */
  refresh: () => Promise<void>;
}

/**
 * Hook for managing model fetching and selection.
 *
 * @example
 * ```tsx
 * // Basic usage
 * const { models, selectedModel, setSelectedModel, isLoading } = useModels();
 *
 * // With initial model from navigation
 * const { models, selectedModel, setSelectedModel } = useModels({
 *   initialModel: locationState?.model
 * });
 * ```
 */
export function useModels(options: UseModelsOptions = {}): UseModelsReturn {
  const { initialModel = null, autoSelectFirst = true, limit = 20 } = options;

  const { user } = useAuth();
  const isAuthenticated = !!user;

  const [models, setModels] = useState<ChatSource[]>([]);
  const [selectedModel, setSelectedModel] = useState<ChatSource | null>(initialModel);
  const [isLoading, setIsLoading] = useState(true);

  const loadModels = useCallback(async () => {
    setIsLoading(true);

    try {
      // Use guest-accessible models for unauthenticated users
      const fetchedModels = isAuthenticated
        ? await getChatModels(limit)
        : await getGuestAccessibleModels(limit);

      // If initialModel was provided but not in fetched list, prepend it
      let updatedModels = fetchedModels;
      if (initialModel && !fetchedModels.some((m) => m.slug === initialModel.slug)) {
        updatedModels = [initialModel, ...fetchedModels];
      }

      setModels(updatedModels);

      // Auto-select first model if enabled and no current selection
      setSelectedModel((current) => {
        // Keep current selection if exists
        if (current !== null) return current;
        // Auto-select first if enabled
        if (autoSelectFirst && updatedModels.length > 0 && updatedModels[0]) {
          return updatedModels[0];
        }
        return null;
      });
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      setIsLoading(false);
    }
  }, [initialModel, autoSelectFirst, limit, isAuthenticated]);

  // Load models on mount
  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      await loadModels();
      // Guard against state updates after unmount (loadModels handles its own state)
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
