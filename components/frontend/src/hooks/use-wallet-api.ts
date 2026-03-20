/**
 * Wallet API Hooks
 *
 * React hooks for interacting with the wallet service via backend API.
 * All requests go through the SyftHub backend.
 *
 * @example
 * ```tsx
 * function BalanceDisplay() {
 *   const { balance, isLoading, error } = useWalletBalance();
 *
 *   if (isLoading) return <Spinner />;
 *   if (error) return <Error message={error} />;
 *   if (!balance) return <SetupPrompt />;
 *
 *   return <div>Balance: {balance.balance}</div>;
 * }
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { WalletBalance, WalletInfo, WalletTransaction } from '@/lib/types';

import { useWalletContext } from '@/context/wallet-context';
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
 * Call this from anywhere in the app to immediately refresh wallet data.
 *
 * @example
 * ```tsx
 * // After a successful payment
 * import { triggerBalanceRefresh } from '@/hooks/use-wallet-api';
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
// Wallet API Client
// =============================================================================

/**
 * Makes authenticated requests to the SyftHub backend wallet endpoints.
 */
export class WalletAPIClient {
  private readonly baseUrl = '/api/v1/wallet';
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
    const url = new URL(this.baseUrl + path, globalThis.location.origin);

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

  async getWallet(): Promise<WalletInfo> {
    return this.request<WalletInfo>('GET', '/');
  }

  async getBalance(): Promise<WalletBalance> {
    return this.request<WalletBalance>('GET', '/balance');
  }

  async getTransactions(): Promise<WalletTransaction[]> {
    return this.request<WalletTransaction[]>('GET', '/transactions');
  }

  async createWallet(): Promise<{ address: string }> {
    return this.request<{ address: string }>('POST', '/create');
  }

  async importWallet(privateKey: string): Promise<{ address: string }> {
    return this.request<{ address: string }>('POST', '/import', {
      body: { private_key: privateKey }
    });
  }
}

// Singleton client instance
let walletClient: WalletAPIClient | null = null;

function getWalletClient(): WalletAPIClient {
  walletClient ??= new WalletAPIClient();
  return walletClient;
}

// =============================================================================
// useWalletClient - Get the wallet API client
// =============================================================================

/**
 * Hook to get the wallet API client if configured.
 * Returns null if wallet is not configured.
 */
export function useWalletClient(): WalletAPIClient | null {
  const { isConfigured } = useWalletContext();

  if (!isConfigured) {
    return null;
  }

  return getWalletClient();
}

// =============================================================================
// useWalletBalance - Get wallet balance with polling
// =============================================================================

interface UseWalletBalanceResult {
  balance: WalletBalance | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and manage the wallet balance.
 *
 * Features:
 * - Auto-polls every 30 seconds when tab is visible
 * - Pauses polling when tab is hidden
 * - Supports force refresh via triggerBalanceRefresh()
 */
export function useWalletBalance(): UseWalletBalanceResult {
  const { isConfigured } = useWalletContext();
  const [balance, setBalance] = useState<WalletBalance | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);
  const isFetching = useRef(false);

  const fetchBalance = useCallback(
    async (isPolling = false) => {
      if (!isConfigured) {
        setBalance(null);
        return;
      }

      if (isFetching.current) return;
      isFetching.current = true;

      if (!isPolling) {
        setIsLoading(true);
        setError(null);
      }

      try {
        const client = getWalletClient();
        const fetchedBalance = await client.getBalance();
        if (isMounted.current) {
          setBalance(fetchedBalance);
          setError(null);
        }
      } catch (error_) {
        if (isMounted.current && !isPolling) {
          setError(error_ instanceof Error ? error_.message : 'Failed to fetch balance');
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

  const refetch = useCallback(async () => {
    await fetchBalance(false);
  }, [fetchBalance]);

  // Visibility-aware polling effect
  useEffect(() => {
    if (!isConfigured) return;

    isMounted.current = true;

    const polling = createVisibilityAwarePolling(fetchBalance, POLLING_INTERVAL_MS);

    if (!document.hidden) {
      polling.start();
    }

    const unsubscribe = subscribeToRefresh(() => void fetchBalance(false));

    return () => {
      isMounted.current = false;
      polling.cleanup();
      unsubscribe();
    };
  }, [isConfigured, fetchBalance]);

  return { balance, isLoading, error, refetch };
}

// =============================================================================
// useWalletTransactions - List transactions with polling
// =============================================================================

interface UseWalletTransactionsOptions {
  autoFetch?: boolean;
}

interface UseWalletTransactionsResult {
  transactions: WalletTransaction[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and manage wallet transactions.
 *
 * Features:
 * - Auto-polls every 30 seconds when tab is visible
 * - Pauses polling when tab is hidden
 * - Supports force refresh via triggerBalanceRefresh()
 */
export function useWalletTransactions(
  options: UseWalletTransactionsOptions = {}
): UseWalletTransactionsResult {
  const { autoFetch = true } = options;
  const { isConfigured } = useWalletContext();
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);
  const isFetching = useRef(false);

  const fetchTransactions = useCallback(
    async (isPolling = false) => {
      if (!isConfigured) {
        setTransactions([]);
        return;
      }

      if (isFetching.current) return;
      isFetching.current = true;

      if (!isPolling) {
        setIsLoading(true);
        setError(null);
      }

      try {
        const client = getWalletClient();
        const fetchedTransactions = await client.getTransactions();

        if (isMounted.current) {
          setTransactions(fetchedTransactions);
          setError(null);
        }
      } catch (error_) {
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
    [isConfigured]
  );

  const refetch = useCallback(async () => {
    await fetchTransactions(false);
  }, [fetchTransactions]);

  // Visibility-aware polling effect
  useEffect(() => {
    if (!isConfigured || !autoFetch) return;

    isMounted.current = true;

    const polling = createVisibilityAwarePolling(fetchTransactions, POLLING_INTERVAL_MS);

    if (!document.hidden) {
      polling.start();
    }

    const unsubscribe = subscribeToRefresh(() => void fetchTransactions(false));

    return () => {
      isMounted.current = false;
      polling.cleanup();
      unsubscribe();
    };
  }, [isConfigured, autoFetch, fetchTransactions]);

  return { transactions, isLoading, error, refetch };
}
