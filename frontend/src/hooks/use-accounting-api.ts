/**
 * Accounting API Hooks
 *
 * React hooks for interacting with the external accounting service.
 * These hooks use the credentials stored in the encrypted vault.
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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type {
  AccountingCredentials,
  AccountingTransaction,
  AccountingUser,
  CreateTransactionInput
} from '@/lib/types';

import { useAccountingContext } from '@/context/accounting-context';

// =============================================================================
// Accounting Client (inline implementation to avoid SDK dependency issues)
// =============================================================================

/**
 * Simple accounting client that makes direct API calls.
 * This mirrors the SDK's AccountingResource but is self-contained.
 */
class AccountingClient {
  private readonly baseUrl: string;
  private readonly authHeader: string;
  private readonly timeout: number;

  constructor(credentials: AccountingCredentials, timeout = 30_000) {
    this.baseUrl = credentials.url.replace(/\/$/, '');
    this.timeout = timeout;

    // Create Basic auth header
    const encoded = btoa(`${credentials.email}:${credentials.password}`);
    this.authHeader = `Basic ${encoded}`;
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      body?: Record<string, unknown>;
      params?: Record<string, string | number>;
    }
  ): Promise<T> {
    const url = new URL(path, this.baseUrl);

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
      const response = await fetch(url.toString(), {
        method,
        headers: {
          Authorization: this.authHeader,
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

  async getTransaction(id: string): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('GET', `/transactions/${id}`);
  }

  async createTransaction(input: CreateTransactionInput): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', '/transactions', {
      body: {
        recipientEmail: input.recipientEmail,
        amount: input.amount,
        ...(input.appName && { appName: input.appName }),
        ...(input.appEpPath && { appEpPath: input.appEpPath })
      }
    });
  }

  async confirmTransaction(id: string): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', `/transactions/${id}/confirm`);
  }

  async cancelTransaction(id: string): Promise<TransactionResponse> {
    return this.request<TransactionResponse>('POST', `/transactions/${id}/cancel`);
  }

  async createTransactionToken(recipientEmail: string): Promise<string> {
    const response = await this.request<{ token: string }>('POST', '/tokens', {
      body: { recipientEmail }
    });
    return response.token;
  }

  async createDelegatedTransaction(
    senderEmail: string,
    amount: number,
    token: string
  ): Promise<TransactionResponse> {
    const url = new URL('/transactions', this.baseUrl);

    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({ senderEmail, amount })
    });

    if (!response.ok) {
      let detail: string;
      try {
        const body = (await response.json()) as { detail?: string };
        detail = body.detail ?? `HTTP ${String(response.status)}`;
      } catch {
        detail = `HTTP ${String(response.status)}`;
      }
      throw new Error(detail);
    }

    return (await response.json()) as TransactionResponse;
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

// =============================================================================
// useAccountingClient - Get or create accounting client from vault credentials
// =============================================================================

/**
 * Hook to get an AccountingClient instance from vault credentials.
 * Returns null if vault is not unlocked.
 */
export function useAccountingClient(): AccountingClient | null {
  const { credentials, status } = useAccountingContext();

  return useMemo(() => {
    if (!status.isUnlocked || !credentials) {
      return null;
    }
    return new AccountingClient(credentials);
  }, [credentials, status.isUnlocked]);
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
  const client = useAccountingClient();
  const [user, setUser] = useState<AccountingUser | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const refetch = useCallback(async () => {
    if (!client) {
      setUser(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
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
  }, [client]);

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
  const client = useAccountingClient();
  const [transactions, setTransactions] = useState<AccountingTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const isMounted = useRef(true);

  const fetchMore = useCallback(async () => {
    if (!client || isLoading || !hasMore) return;

    setIsLoading(true);
    setError(null);

    try {
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
  }, [client, isLoading, hasMore, transactions.length, pageSize]);

  const refetch = useCallback(async () => {
    if (!client) {
      setTransactions([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    setHasMore(true);

    try {
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
  }, [client, pageSize]);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (autoFetch) {
      void refetch();
    }
  }, [autoFetch, refetch]);

  return { transactions, isLoading, error, hasMore, fetchMore, refetch };
}

// =============================================================================
// useTransaction - Get single transaction with actions
// =============================================================================

interface UseTransactionResult {
  transaction: AccountingTransaction | null;
  isLoading: boolean;
  error: string | null;
  confirm: () => Promise<AccountingTransaction | null>;
  cancel: () => Promise<AccountingTransaction | null>;
  refetch: () => Promise<void>;
}

/**
 * Hook to manage a single transaction.
 */
export function useTransaction(transactionId: string | null): UseTransactionResult {
  const client = useAccountingClient();
  const [transaction, setTransaction] = useState<AccountingTransaction | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const refetch = useCallback(async () => {
    if (!client || !transactionId) {
      setTransaction(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await client.getTransaction(transactionId);
      if (isMounted.current) {
        setTransaction(parseTransaction(response));
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'Failed to fetch transaction');
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [client, transactionId]);

  const confirm = useCallback(async (): Promise<AccountingTransaction | null> => {
    if (!client || !transactionId) return null;

    setIsLoading(true);
    setError(null);

    try {
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
  }, [client, transactionId]);

  const cancel = useCallback(async (): Promise<AccountingTransaction | null> => {
    if (!client || !transactionId) return null;

    setIsLoading(true);
    setError(null);

    try {
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
  }, [client, transactionId]);

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
  const client = useAccountingClient();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const create = useCallback(
    async (input: CreateTransactionInput): Promise<AccountingTransaction | null> => {
      if (!client) {
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
    [client]
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
// useTransactionToken - Create delegation tokens
// =============================================================================

interface UseTransactionTokenResult {
  createToken: (recipientEmail: string) => Promise<string | null>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

/**
 * Hook to create transaction tokens for delegated transfers.
 */
export function useTransactionToken(): UseTransactionTokenResult {
  const client = useAccountingClient();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const createToken = useCallback(
    async (recipientEmail: string): Promise<string | null> => {
      if (!client) {
        setError('Accounting not configured');
        return null;
      }

      setIsLoading(true);
      setError(null);

      try {
        return await client.createTransactionToken(recipientEmail);
      } catch (error_) {
        if (isMounted.current) {
          setError(error_ instanceof Error ? error_.message : 'Failed to create token');
        }
        return null;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [client]
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

  return { createToken, isLoading, error, clearError };
}

// =============================================================================
// useDelegatedTransaction - Create delegated transactions
// =============================================================================

interface UseDelegatedTransactionResult {
  create: (
    senderEmail: string,
    amount: number,
    token: string
  ) => Promise<AccountingTransaction | null>;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
}

/**
 * Hook to create delegated transactions using pre-authorized tokens.
 */
export function useDelegatedTransaction(): UseDelegatedTransactionResult {
  const client = useAccountingClient();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMounted = useRef(true);

  const create = useCallback(
    async (
      senderEmail: string,
      amount: number,
      token: string
    ): Promise<AccountingTransaction | null> => {
      if (!client) {
        setError('Accounting not configured');
        return null;
      }

      if (amount <= 0) {
        setError('Amount must be greater than 0');
        return null;
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await client.createDelegatedTransaction(senderEmail, amount, token);
        return parseTransaction(response);
      } catch (error_) {
        if (isMounted.current) {
          setError(
            error_ instanceof Error ? error_.message : 'Failed to create delegated transaction'
          );
        }
        return null;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [client]
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
