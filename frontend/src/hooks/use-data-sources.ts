/**
 * useDataSources Hook
 *
 * Centralized hook for data source fetching.
 * Used by ChatView and any component that needs available data sources.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { getChatDataSources, getGuestAccessibleDataSources } from '@/lib/endpoint-utils';

export interface UseDataSourcesOptions {
  /** Maximum number of sources to fetch (default: 100) */
  limit?: number;
  /** Whether to fetch immediately on mount (default: true) */
  immediate?: boolean;
}

export interface UseDataSourcesReturn {
  /** Available data sources from the backend */
  sources: ChatSource[];
  /** Map of sources by ID for O(1) lookups */
  sourcesById: Map<string, ChatSource>;
  /** Whether sources are currently loading */
  isLoading: boolean;
  /** Reload sources from the backend */
  refresh: () => Promise<void>;
}

/**
 * Hook for managing data source fetching.
 *
 * @example
 * ```tsx
 * const { sources, sourcesById, isLoading } = useDataSources();
 *
 * // Quick lookup by ID
 * const source = sourcesById.get(sourceId);
 * ```
 */
export function useDataSources(options: UseDataSourcesOptions = {}): UseDataSourcesReturn {
  const { limit = 100, immediate = true } = options;

  const { user } = useAuth();
  const isAuthenticated = !!user;

  const [sources, setSources] = useState<ChatSource[]>([]);
  const [isLoading, setIsLoading] = useState(immediate);

  const loadSources = useCallback(async () => {
    setIsLoading(true);

    try {
      // Use guest-accessible data sources for unauthenticated users
      const fetchedSources = isAuthenticated
        ? await getChatDataSources(limit)
        : await getGuestAccessibleDataSources(limit);
      setSources(fetchedSources);
    } catch (error) {
      console.error('Failed to load data sources:', error);
    } finally {
      setIsLoading(false);
    }
  }, [limit, isAuthenticated]);

  // Load sources on mount if immediate
  useEffect(() => {
    if (!immediate) return;

    let isMounted = true;

    const load = async () => {
      await loadSources();
      if (!isMounted) return;
    };

    void load();

    return () => {
      isMounted = false;
    };
  }, [immediate, loadSources]);

  // Memoized Map for O(1) lookups
  const sourcesById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources]
  );

  const refresh = useCallback(async () => {
    await loadSources();
  }, [loadSources]);

  return {
    sources,
    sourcesById,
    isLoading,
    refresh
  };
}
