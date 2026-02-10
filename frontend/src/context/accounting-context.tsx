/**
 * Accounting Context
 *
 * React context for managing accounting credentials stored in the backend.
 * Credentials are fetched from the SyftHub API and updated via user profile.
 *
 * The Unified Global Ledger uses:
 * - URL: stored in user profile
 * - Email: same as SyftHub user email
 * - API Token: stored in user profile (at_* format)
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import type { AccountingCredentials } from '@/lib/types';

import { syftClient } from '@/lib/sdk-client';

import { useAuth } from './auth-context';

// =============================================================================
// Types
// =============================================================================

interface AccountingContextType {
  /** Accounting credentials (null if not loaded or user not authenticated) */
  credentials: AccountingCredentials | null;
  /** Whether credentials are being fetched or updated */
  isLoading: boolean;
  /** Error message (null if no error) */
  error: string | null;
  /** Whether accounting is configured (has URL and API token) */
  isConfigured: boolean;
  /** Fetch credentials from the backend */
  fetchCredentials: () => Promise<void>;
  /** Update accounting credentials */
  updateCredentials: (url: string, apiToken: string) => Promise<boolean>;
  /** Clear current error */
  clearError: () => void;
}

// =============================================================================
// Context
// =============================================================================

const AccountingContext = createContext<AccountingContextType | undefined>(undefined);

// =============================================================================
// Provider
// =============================================================================

interface AccountingProviderProps {
  children: React.ReactNode;
}

export function AccountingProvider({ children }: Readonly<AccountingProviderProps>) {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const { user } = useAuth();
  const [credentials, setCredentials] = useState<AccountingCredentials | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derive authentication state from user presence
  const isAuthenticated = user !== null;

  // Track if component is mounted to prevent state updates after unmount
  const isMounted = useRef(true);

  // ---------------------------------------------------------------------------
  // Derived State
  // ---------------------------------------------------------------------------

  const isConfigured =
    credentials !== null && Boolean(credentials.url && credentials.has_api_token);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const fetchCredentials = useCallback(async () => {
    if (!isAuthenticated) {
      setCredentials(null);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      // Get token from SDK client (uses syft_access_token in localStorage)
      const tokens = syftClient.getTokens();
      const accessToken = tokens?.accessToken ?? '';

      const response = await fetch('/api/v1/users/me/accounting', {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        if (response.status === 401) {
          setCredentials(null);
          return;
        }
        throw new Error('Failed to fetch accounting credentials');
      }

      const data = (await response.json()) as AccountingCredentials;

      if (isMounted.current) {
        setCredentials(data);
      }
    } catch (error_) {
      if (isMounted.current) {
        setError(error_ instanceof Error ? error_.message : 'An unknown error occurred');
      }
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [isAuthenticated]);

  const updateCredentials = useCallback(
    async (url: string, apiToken: string): Promise<boolean> => {
      if (!isAuthenticated) {
        setError('You must be logged in to update accounting credentials');
        return false;
      }

      try {
        setIsLoading(true);
        setError(null);

        // Get token from SDK client (uses syft_access_token in localStorage)
        const tokens = syftClient.getTokens();
        const accessToken = tokens?.accessToken ?? '';

        const response = await fetch('/api/v1/users/me', {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${accessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            accounting_service_url: url,
            accounting_api_token: apiToken
          })
        });

        if (!response.ok) {
          const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errorData.detail ?? 'Failed to update accounting credentials');
        }

        // Refresh credentials after successful update
        await fetchCredentials();

        return true;
      } catch (error_) {
        if (isMounted.current) {
          setError(error_ instanceof Error ? error_.message : 'An unknown error occurred');
        }
        return false;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [isAuthenticated, fetchCredentials]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Track mounted state
  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  // Fetch credentials when user logs in or changes
  useEffect(() => {
    if (user) {
      void fetchCredentials();
    } else {
      setCredentials(null);
    }
  }, [user, fetchCredentials]);

  // ---------------------------------------------------------------------------
  // Context Value
  // ---------------------------------------------------------------------------

  const value: AccountingContextType = {
    credentials,
    isLoading,
    error,
    isConfigured,
    fetchCredentials,
    updateCredentials,
    clearError
  };

  return <AccountingContext.Provider value={value}>{children}</AccountingContext.Provider>;
}

// =============================================================================
// Hook
// =============================================================================

/**
 * Hook to access accounting context
 * @throws Error if used outside AccountingProvider
 */
export function useAccountingContext(): AccountingContextType {
  const context = useContext(AccountingContext);
  if (context === undefined) {
    throw new Error('useAccountingContext must be used within an AccountingProvider');
  }
  return context;
}

// =============================================================================
// Exports
// =============================================================================

export { AccountingContext };
export type { AccountingContextType };
