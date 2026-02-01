/**
 * Accounting API Hooks
 *
 * React hooks for interacting with the accounting service via backend proxy.
 * All requests go through the SyftHub backend to avoid CORS issues.
 *
 * @example
 * ```tsx
 * function BalanceDisplay() {
 *   const { user, isLoading, error, refetch } = useAccountingUser();
 *
 *   if (isLoading) return <Spinner />;
 *   if (error) return <Error message={error} />;
 *   if (!user) return <SetupPrompt />;
 *
 *   return <div>Balance: {user.balance}</div>;
 * }
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { AccountingTransaction, AccountingUser, CreateTransactionInput } from '@/lib/types';

import { useAccountingContext } from '@/context/accounting-context';
import { syftClient } from '@/lib/sdk-client';

// =============================================================================
// Polling Configuration
// =============================================================================

/** Polling interval for balance and transactions (30 seconds) */
export const POLLING_INTERVAL_MS = 30_000;

// =============================================================================
// Force Refresh Event System
// =============================================================================

type RefreshListener = () => void;
const refreshListeners = new Set<RefreshListener>();

/**
 * Subscribe to force refresh events.
 * Returns an unsubscribe function.
 */
function subscribeToRefresh(listener: RefreshListener): () => void {
  refreshListeners.add(listener);
  return () => refreshListeners.delete(listener);
}

/**
 * Trigger a force refresh of all balance/transaction data.
 * Call this from anywhere in the app to immediately refresh accounting data.
 *
 * @example
 * ```tsx
 * // After a successful payment
 * import { triggerBalanceRefresh } from '@/hooks/use-accounting-api';
 * await processPayment();
 * triggerBalanceRefresh();
 * ```
 */
export function triggerBalanceRefresh(): void {
  for (const listener of refreshListeners) {
    listener();
  }
}

/**
 * Hook to get a function that forces refresh of balance data.
 * Use this when you need to trigger a refresh from a component.
 *
 * @example
 * ```tsx
 * function PaymentButton() {
 *   const forceRefresh = useBalanceRefresh();
 *
 *   const handlePayment = async () => {
 *     await processPayment();
 *     forceRefresh(); // Immediately update balance display
 *   };
 * }
 * ```
 */
export function useBalanceRefresh(): () => void {
  return triggerBalanceRefresh;
}

// =============================================================================
// Visibility-Aware Polling Utilities
// =============================================================================

interface PollingController {
  start: () => void;
  stop: () => void;
  cleanup: () => void;
}

/**
 * Creates a visibility-aware polling controller.
 * Pauses polling when tab is hidden, resumes when visible.
 */
function createVisibilityAwarePolling(
  fetchFunction: (isPolling: boolean) => Promise<void>,
  intervalMs: number
): PollingController {
  let intervalId: ReturnType<typeof setInterval> | null = null;

  const start = () => {
    if (intervalId) return; // Already polling
    void fetchFunction(false); // Initial fetch with loading state
    intervalId = setInterval(() => void fetchFunction(true), intervalMs);
  };

  const stop = () => {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  };

  const handleVisibilityChange = () => {
    if (document.hidden) {
      stop();
    } else {
      // Resume polling with immediate fetch when tab becomes visible
      start();
    }
  };

  const cleanup = () => {
    stop();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  };

  // Set up visibility listener
  document.addEventListener('visibilitychange', handleVisibilityChange);

  return { start, stop, cleanup };
}

// =============================================================================
// Proxy Client - Makes requests to SyftHub backend (which proxies to accounting)
// =============================================================================

/**
 * Makes authenticated requests to the SyftHub backend accounting proxy endpoints.
 * This avoids CORS issues by going through the backend.
 */
export class AccountingProxyClient {
  // Use same-origin for API calls (through Vite proxy or nginx)
  private readonly baseUrl = '/api/v1/accounting';
  private readonly timeout: number;

  constructor(timeout = 30_000) {
    this.timeout = timeout;
  }

  private getAuthHeader(): string {
    const tokens = syftClient.getTokens();
    if (!tokens?.accessToken) {
      throw new Error('Not authenticated');
    }
    return `Bearer ${tokens.accessToken}`;
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      body?: Record<string, unknown>;
      params?: Record<string, string | number>;
    }
  ): Promise<T> {
    const url = new URL(path, globalThis.location.origin + this.baseUrl);

    if (options?.params) {
      for (const [key, value] of Object.entries(options.params)) {
        url.searchParams.set(key, String(value));
      }
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, this.timeout);

    try {
      const response = await fetch(this.baseUrl + path + url.search, {
        method,
        headers: {
          Authorization: this.getAuthHeader(),
          'Content-Type': 'application/json',
          Accept: 'application/json'
        },
        body: options?.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal
      });

      if (!response.ok) {
        let detail: string;
        try {
          const body = (await response.json()) as { detail?: string; message?: string };
          detail = body.detail ?? body.message ?? `HTTP ${String(response.status)}`;
        } catch {
          detail = `HTTP ${String(response.status)}`;
        }
        throw new Error(detail);
      }

      if (response.status === 204) {
        return {} as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timeout');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async getUser(): Promise<AccountingUser> {
    return this.request<AccountingUser>('GET', '/user');
  }

  async getTransactions(skip = 0, limit = 20): Promise<TransactionResponse[]> {
    return this.request<TransactionResponse[]>('GET', '/transactions', {
      params: { skip, limit }
    });
  }

  async createTransaction(input: CreateTransactionInput): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', '/transactions', {
      body: {
        recipient_email: input.recipientEmail,
        amount: input.amount,
        ...(input.appName && { app_name: input.appName }),
        ...(input.appEpPath && { app_ep_path: input.appEpPath })
      }
    });
  }

  async confirmTransaction(id: string): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', `/transactions/${id}/confirm`);
  }

  async cancelTransaction(id: string): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', `/transactions/${id}/cancel`);
  }
}

// Raw response type from API (snake_case from backend)
interface TransactionResponse {
  id: string;
  sender_email: string;
  recipient_email: string;
  amount: number;
  status: 'pending' | 'completed' | 'cancelled' | 'PENDING' | 'COMPLETED' | 'CANCELLED';
  created_by: 'system' | 'sender' | 'recipient' | 'SYSTEM' | 'SENDER' | 'RECIPIENT';
  resolved_by: 'system' | 'sender' | 'recipient' | 'SYSTEM' | 'SENDER' | 'RECIPIENT' | null;
  created_at: string;
  resolved_at: string | null;
  app_name: string | null;
  app_ep_path: string | null;
}

// Parse transaction response to proper type (snake_case -> camelCase)
export function parseTransaction(response: TransactionResponse): AccountingTransaction {
  return {
    id: response.id,
    senderEmail: response.sender_email,
    recipientEmail: response.recipient_email,
    amount: response.amount,
    status: response.status.toLowerCase() as AccountingTransaction['status'],
    createdBy: response.created_by.toLowerCase() as AccountingTransaction['createdBy'],
    resolvedBy: response.resolved_by
      ? (response.resolved_by.toLowerCase() as AccountingTransaction['resolvedBy'])
      : null,
    createdAt: new Date(response.created_at),
    resolvedAt: response.resolved_at ? new Date(response.resolved_at) : null,
    appName: response.app_name,
    appEpPath: response.app_ep_path
  };
}

// Singleton proxy client instance
let proxyClient: AccountingProxyClient | null = null;

function getProxyClient(): AccountingProxyClient {
  proxyClient ??= new AccountingProxyClient();
  return proxyClient;
}

// =============================================================================
// useAccountingClient - For backward compatibility
// =============================================================================

/**
 * Hook to check if accounting is configured.
 * Returns a proxy client if configured, null otherwise.
 * @deprecated Use the proxy client directly via hooks
 */
export function useAccountingClient(): AccountingProxyClient | null {
  const { isConfigured } = useAccountingContext();

  if (!isConfigured) {
    return null;
  }

  return getProxyClient();
}

// =============================================================================
// useAccountingUser - Get current user with balance
// =============================================================================

interface UseAccountingUserResult {
  user: AccountingUser | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and manage the current accounting user.
 *
 * Features:
 * - Auto-polls every 30 seconds when tab is visible
 * - Pauses polling when tab is hidden (saves bandwidth)
 * - Resumes with immediate fetch when tab becomes visible
 * - Supports force refresh via triggerBalanceRefresh()
 * - Silent error handling during polling (doesn't disrupt UI)
 */
export function useAccountingUser(): UseAccountingUserResult {
  const { isConfigured } = useAccountingContext();
  const [user, setUser] = useState<AccountingUser | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);
  const isFetching = useRef(false);

  // Fetch user data, with optional silent mode for polling
  const fetchUser = useCallback(
    async (isPolling = false) => {
      if (!isConfigured) {
        setUser(null);
        return;
      }

      // Prevent concurrent fetches
      if (isFetching.current) return;
      isFetching.current = true;

      // Only show loading state on initial/manual fetch, not polling
      if (!isPolling) {
        setIsLoading(true);
        setError(null);
      }

      try {
        const client = getProxyClient();
        const fetchedUser = await client.getUser();
        if (isMounted.current) {
          setUser(fetchedUser);
          // Clear any previous error on successful fetch (self-healing)
          setError(null);
        }
      } catch (error_) {
        // Only show error to user on initial/manual fetch, not during polling
        // This prevents transient network issues from disrupting the UI
        if (isMounted.current && !isPolling) {
          setError(error_ instanceof Error ? error_.message : 'Failed to fetch user');
        }
      } finally {
        isFetching.current = false;
        if (isMounted.current && !isPolling) {
          setIsLoading(false);
        }
      }
    },
    [isConfigured]
  );

  // Manual refetch (shows loading state)
  const refetch = useCallback(async () => {
    await fetchUser(false);
  }, [fetchUser]);

  // Visibility-aware polling effect
  useEffect(() => {
    if (!isConfigured) return;

    isMounted.current = true;

    // Create polling controller
    const polling = createVisibilityAwarePolling(fetchUser, POLLING_INTERVAL_MS);

    // Start polling if tab is currently visible
    if (!document.hidden) {
      polling.start();
    }

    // Subscribe to force refresh events
    const unsubscribe = subscribeToRefresh(() => void fetchUser(false));

    return () => {
      isMounted.current = false;
      polling.cleanup();
      unsubscribe();
    };
  }, [isConfigured, fetchUser]);

  return { user, isLoading, error, refetch };
}

// =============================================================================
// useAccountingBalance - Convenience hook for just the balance
// =============================================================================

interface UseAccountingBalanceResult {
  balance: number | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Convenience hook to get just the balance.
 */
export function useAccountingBalance(): UseAccountingBalanceResult {
  const { user, isLoading, error, refetch } = useAccountingUser();
  return {
    balance: user?.balance ?? null,
    isLoading,
    error,
    refetch
  };
}

// =============================================================================
// useTransactions - List transactions with pagination
// =============================================================================

interface UseTransactionsOptions {
  pageSize?: number;
  autoFetch?: boolean;
}

interface UseTransactionsResult {
  transactions: AccountingTransaction[];
  isLoading: boolean;
  error: string | null;
  hasMore: boolean;
  fetchMore: () => Promise<void>;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and manage transactions list.
 *
 * Features:
 * - Auto-polls every 30 seconds when tab is visible (if autoFetch is true)
 * - Pauses polling when tab is hidden (saves bandwidth)
 * - Resumes with immediate fetch when tab becomes visible
 * - Supports force refresh via triggerBalanceRefresh()
 * - Silent error handling during polling (doesn't disrupt UI)
 * - Pagination support via fetchMore()
 */
export function useTransactions(options: UseTransactionsOptions = {}): UseTransactionsResult {
  const { pageSize = 20, autoFetch = true } = options;
  const { isConfigured } = useAccountingContext();
  const [transactions, setTransactions] = useState<AccountingTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const isMounted = useRef(true);
  const isFetching = useRef(false);

  // Fetch more transactions (pagination) - not used during polling
  const fetchMore = useCallback(async () => {
    if (!isConfigured || isFetching.current || !hasMore) return;

    isFetching.current = true;
    setIsLoading(true);
    setError(null);

    try {
      const client = getProxyClient();
      const skip = transactions.length;
      const response = await client.getTransactions(skip, pageSize);
      const newTransactions = response.map((tx) => parseTransaction(tx));

      if (isMounted.current) {
        setTransactions((previous: AccountingTransaction[]) => [...previous, ...newTransactions]);
        setHasMore(newTransactions.length === pageSize);
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to fetch transactions');
      }
    } finally {
      isFetching.current = false;
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured, hasMore, transactions.length, pageSize]);

  // Fetch transactions (first page), with optional silent mode for polling
  const fetchTransactions = useCallback(
    async (isPolling = false) => {
      if (!isConfigured) {
        setTransactions([]);
        return;
      }

      // Prevent concurrent fetches
      if (isFetching.current) return;
      isFetching.current = true;

      // Only show loading state on initial/manual fetch, not polling
      if (!isPolling) {
        setIsLoading(true);
        setError(null);
        setHasMore(true);
      }

      try {
        const client = getProxyClient();
        const response = await client.getTransactions(0, pageSize);
        const newTransactions = response.map((tx) => parseTransaction(tx));

        if (isMounted.current) {
          setTransactions(newTransactions);
          setHasMore(newTransactions.length === pageSize);
          // Clear any previous error on successful fetch (self-healing)
          setError(null);
        }
      } catch (error_) {
        // Only show error to user on initial/manual fetch, not during polling
        if (isMounted.current && !isPolling) {
          setError(error_ instanceof Error ? error_.message : 'Failed to fetch transactions');
        }
      } finally {
        isFetching.current = false;
        if (isMounted.current && !isPolling) {
          setIsLoading(false);
        }
      }
    },
    [isConfigured, pageSize]
  );

  // Manual refetch (shows loading state)
  const refetch = useCallback(async () => {
    await fetchTransactions(false);
  }, [fetchTransactions]);

  // Visibility-aware polling effect
  useEffect(() => {
    if (!isConfigured || !autoFetch) return;

    isMounted.current = true;

    // Create polling controller
    const polling = createVisibilityAwarePolling(fetchTransactions, POLLING_INTERVAL_MS);

    // Start polling if tab is currently visible
    if (!document.hidden) {
      polling.start();
    }

    // Subscribe to force refresh events
    const unsubscribe = subscribeToRefresh(() => void fetchTransactions(false));

    return () => {
      isMounted.current = false;
      polling.cleanup();
      unsubscribe();
    };
  }, [isConfigured, autoFetch, fetchTransactions]);

  return { transactions, isLoading, error, hasMore, fetchMore, refetch };
}

// =============================================================================
// useCreateTransaction - Create new transaction
// =============================================================================

interface UseCreateTransactionResult {
  create: (input: CreateTransactionInput) => Promise<AccountingTransaction | null>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

/**
 * Hook to create new transactions.
 */
export function useCreateTransaction(): UseCreateTransactionResult {
  const { isConfigured } = useAccountingContext();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const create = useCallback(
    async (input: CreateTransactionInput): Promise<AccountingTransaction | null> => {
      if (!isConfigured) {
        setError('Accounting not configured');
        return null;
      }

      if (input.amount <= 0) {
        setError('Amount must be greater than 0');
        return null;
      }

      setIsLoading(true);
      setError(null);

      try {
        const client = getProxyClient();
        const response = await client.createTransaction(input);
        return parseTransaction(response);
      } catch (error_) {
        if (isMounted.current) {
          setError(error_ instanceof Error ? error_.message : 'Failed to create transaction');
        }
        return null;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [isConfigured]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  return { create, isLoading, error, clearError };
}

// =============================================================================
// useConfirmTransaction - Confirm a transaction
// =============================================================================

interface UseConfirmTransactionResult {
  confirm: (transactionId: string) => Promise<AccountingTransaction | null>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

/**
 * Hook to confirm transactions.
 */
export function useConfirmTransaction(): UseConfirmTransactionResult {
  const { isConfigured } = useAccountingContext();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const confirm = useCallback(
    async (transactionId: string): Promise<AccountingTransaction | null> => {
      if (!isConfigured) {
        setError('Accounting not configured');
        return null;
      }

      setIsLoading(true);
      setError(null);

      try {
        const client = getProxyClient();
        const response = await client.confirmTransaction(transactionId);
        return parseTransaction(response);
      } catch (error_) {
        if (isMounted.current) {
          setError(error_ instanceof Error ? error_.message : 'Failed to confirm transaction');
        }
        return null;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [isConfigured]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  return { confirm, isLoading, error, clearError };
}

// =============================================================================
// useCancelTransaction - Cancel a transaction
// =============================================================================

interface UseCancelTransactionResult {
  cancel: (transactionId: string) => Promise<AccountingTransaction | null>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

/**
 * Hook to cancel transactions.
 */
export function useCancelTransaction(): UseCancelTransactionResult {
  const { isConfigured } = useAccountingContext();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const cancel = useCallback(
    async (transactionId: string): Promise<AccountingTransaction | null> => {
      if (!isConfigured) {
        setError('Accounting not configured');
        return null;
      }

      setIsLoading(true);
      setError(null);

      try {
        const client = getProxyClient();
        const response = await client.cancelTransaction(transactionId);
        return parseTransaction(response);
      } catch (error_) {
        if (isMounted.current) {
          setError(error_ instanceof Error ? error_.message : 'Failed to cancel transaction');
        }
        return null;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [isConfigured]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  return { cancel, isLoading, error, clearError };
}

// =============================================================================
// Deprecated hooks - kept for backward compatibility
// =============================================================================

/**
 * @deprecated Use useConfirmTransaction and useCancelTransaction instead
 */
export function useTransaction(transactionId: string | null) {
  const { isConfigured } = useAccountingContext();
  const [transaction, setTransaction] = useState<AccountingTransaction | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const refetch = useCallback(async () => {
    if (!isConfigured || !transactionId) {
      setTransaction(null);
      return;
    }
    // Note: Single transaction fetch not implemented in proxy yet
    setTransaction(null);
  }, [isConfigured, transactionId]);

  const confirm = useCallback(async (): Promise<AccountingTransaction | null> => {
    if (!isConfigured || !transactionId) return null;

    setIsLoading(true);
    setError(null);

    try {
      const client = getProxyClient();
      const response = await client.confirmTransaction(transactionId);
      const updated = parseTransaction(response);
      if (isMounted.current) {
        setTransaction(updated);
      }
      return updated;
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to confirm transaction');
      }
      return null;
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured, transactionId]);

  const cancel = useCallback(async (): Promise<AccountingTransaction | null> => {
    if (!isConfigured || !transactionId) return null;

    setIsLoading(true);
    setError(null);

    try {
      const client = getProxyClient();
      const response = await client.cancelTransaction(transactionId);
      const updated = parseTransaction(response);
      if (isMounted.current) {
        setTransaction(updated);
      }
      return updated;
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to cancel transaction');
      }
      return null;
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured, transactionId]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { transaction, isLoading, error, confirm, cancel, refetch };
}

/**
 * @deprecated Token-based delegation not supported via proxy
 */
export function useTransactionToken() {
  return {
    createToken: async () => null as string | null,
    isLoading: false,
    error: 'Token creation not supported via proxy' as string | null,
    // No-op: deprecated stub with no error state to clear
    // eslint-disable-next-line @typescript-eslint/no-empty-function -- Intentional no-op for deprecated stub
    clearError: () => {}
  };
}

/**
 * @deprecated Delegated transactions not supported via proxy
 */
export function useDelegatedTransaction() {
  return {
    create: async () => null as AccountingTransaction | null,
    isLoading: false,
    error: 'Delegated transactions not supported via proxy' as string | null,
    // No-op: deprecated stub with no error state to clear
    // eslint-disable-next-line @typescript-eslint/no-empty-function -- Intentional no-op for deprecated stub
    clearError: () => {}
  };
}
