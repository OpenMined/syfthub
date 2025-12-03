import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Options for the useAPI hook
 */
interface UseAPIOptions<T> {
  /** Initial data value */
  initialData?: T | null;
  /** Whether to execute the fetcher immediately on mount */
  immediate?: boolean;
  /** Callback on successful fetch */
  onSuccess?: (data: T) => void;
  /** Callback on error */
  onError?: (error: Error) => void;
}

/**
 * Return type for the useAPI hook
 */
interface UseAPIReturn<T, Arguments extends unknown[]> {
  /** The fetched data */
  data: T | null;
  /** Error from the last fetch attempt */
  error: Error | null;
  /** Whether a fetch is in progress */
  isLoading: boolean;
  /** Manually trigger the fetch */
  execute: (...arguments_: Arguments) => Promise<T | null>;
  /** Reset state to initial values */
  reset: () => void;
  /** Manually set data (for optimistic updates) */
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

/**
 * useAPI - Custom hook for data fetching with loading and error states.
 *
 * Provides a simple, reusable pattern for API calls with:
 * - Loading state management
 * - Error handling
 * - Optional immediate execution
 * - Manual execution trigger
 * - Cleanup on unmount
 *
 * @example
 * ```tsx
 * // Immediate fetch on mount
 * const { data, isLoading, error } = useAPI(
 *   () => getPublicEndpoints({ limit: 50 }),
 *   { immediate: true }
 * );
 *
 * // Manual fetch with arguments
 * const { data, execute, isLoading } = useAPI(
 *   (id: string) => getEndpoint(id)
 * );
 * // Later: execute('endpoint-123');
 *
 * // With callbacks
 * const { execute } = useAPI(deleteEndpoint, {
 *   onSuccess: () => toast.success('Deleted!'),
 *   onError: (err) => toast.error(err.message),
 * });
 * ```
 */
export function useAPI<T, Arguments extends unknown[] = []>(
  fetcher: (...arguments_: Arguments) => Promise<T>,
  options: UseAPIOptions<T> = {}
): UseAPIReturn<T, Arguments> {
  const { initialData = null, immediate = false, onSuccess, onError } = options;

  const [data, setData] = useState<T | null>(initialData);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(immediate);

  // Track if component is mounted to prevent state updates after unmount
  const isMounted = useRef(true);

  // Store the latest fetcher to avoid stale closures
  const fetcherReference = useRef(fetcher);
  fetcherReference.current = fetcher;

  // Store the latest callbacks to avoid stale closures
  const onSuccessReference = useRef(onSuccess);
  onSuccessReference.current = onSuccess;

  const onErrorReference = useRef(onError);
  onErrorReference.current = onError;

  // Cleanup on unmount
  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  /**
   * Execute the fetch
   */
  const execute = useCallback(async (...arguments_: Arguments): Promise<T | null> => {
    try {
      setIsLoading(true);
      setError(null);

      const result = await fetcherReference.current(...arguments_);

      if (isMounted.current) {
        setData(result);
        onSuccessReference.current?.(result);
      }

      return result;
    } catch (error_) {
      const error = error_ instanceof Error ? error_ : new Error(String(error_));

      if (isMounted.current) {
        setError(error);
        onErrorReference.current?.(error);
      }

      return null;
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, []);

  /**
   * Reset state to initial values
   */
  const reset = useCallback(() => {
    setData(initialData);
    setError(null);
    setIsLoading(false);
  }, [initialData]);

  // Execute immediately on mount if requested
  useEffect(() => {
    if (immediate) {
      // For immediate execution without args, we cast to Args
      // This is safe because immediate is typically used without args
      void execute(...([] as unknown as Arguments));
    }
  }, [immediate, execute]);

  return {
    data,
    error,
    isLoading,
    execute,
    reset,
    setData
  };
}

/**
 * useAPILazy - Variant of useAPI that never executes immediately.
 * Useful when you only want to fetch on user action.
 *
 * @example
 * ```tsx
 * const { execute, isLoading } = useAPILazy(deleteEndpoint);
 *
 * const handleDelete = async (id: string) => {
 *   const result = await execute(id);
 *   if (result) {
 *     // Success
 *   }
 * };
 * ```
 */
export function useAPILazy<T, Arguments extends unknown[] = []>(
  fetcher: (...arguments_: Arguments) => Promise<T>,
  options: Omit<UseAPIOptions<T>, 'immediate'> = {}
): UseAPIReturn<T, Arguments> {
  return useAPI(fetcher, { ...options, immediate: false });
}
