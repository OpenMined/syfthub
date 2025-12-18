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
// Proxy Client - Makes requests to SyftHub backend (which proxies to accounting)
// =============================================================================

/**
 * Makes authenticated requests to the SyftHub backend accounting proxy endpoints.
 * This avoids CORS issues by going through the backend.
 */
class AccountingProxyClient {
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

// Raw response type from API
interface TransactionResponse {
  id: string;
  senderEmail: string;
  recipientEmail: string;
  amount: number;
  status: 'pending' | 'completed' | 'cancelled';
  createdBy: 'system' | 'sender' | 'recipient';
  resolvedBy: 'system' | 'sender' | 'recipient' | null;
  createdAt: string;
  resolvedAt: string | null;
  appName: string | null;
  appEpPath: string | null;
}

// Parse transaction response to proper type
function parseTransaction(response: TransactionResponse): AccountingTransaction {
  return {
    ...response,
    createdAt: new Date(response.createdAt),
    resolvedAt: response.resolvedAt ? new Date(response.resolvedAt) : null
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
 */
export function useAccountingUser(): UseAccountingUserResult {
  const { isConfigured } = useAccountingContext();
  const [user, setUser] = useState<AccountingUser | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const refetch = useCallback(async () => {
    if (!isConfigured) {
      setUser(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const client = getProxyClient();
      const fetchedUser = await client.getUser();
      if (isMounted.current) {
        setUser(fetchedUser);
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to fetch user');
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

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
 */
export function useTransactions(options: UseTransactionsOptions = {}): UseTransactionsResult {
  const { pageSize = 20, autoFetch = true } = options;
  const { isConfigured } = useAccountingContext();
  const [transactions, setTransactions] = useState<AccountingTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const isMounted = useRef(true);

  const fetchMore = useCallback(async () => {
    if (!isConfigured || isLoading || !hasMore) return;

    setIsLoading(true);
    setError(null);

    try {
      const client = getProxyClient();
      const skip = transactions.length;
      const response = await client.getTransactions(skip, pageSize);
      const newTransactions = response.map((tx) => parseTransaction(tx));

      if (isMounted.current) {
        setTransactions((previous) => [...previous, ...newTransactions]);
        setHasMore(newTransactions.length === pageSize);
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to fetch transactions');
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured, isLoading, hasMore, transactions.length, pageSize]);

  const refetch = useCallback(async () => {
    if (!isConfigured) {
      setTransactions([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    setHasMore(true);

    try {
      const client = getProxyClient();
      const response = await client.getTransactions(0, pageSize);
      const newTransactions = response.map((tx) => parseTransaction(tx));

      if (isMounted.current) {
        setTransactions(newTransactions);
        setHasMore(newTransactions.length === pageSize);
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to fetch transactions');
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isConfigured, pageSize]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (autoFetch && isConfigured) {
      void refetch();
    }
  }, [autoFetch, isConfigured, refetch]);

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
