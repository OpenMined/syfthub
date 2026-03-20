/**
 * Wallet Context
 *
 * React context for managing wallet state.
 * Fetches wallet info from the SyftHub backend API on mount.
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import type { WalletInfo } from '@/lib/types';

import { syftClient } from '@/lib/sdk-client';

import { useAuth } from './auth-context';

// =============================================================================
// Types
// =============================================================================

interface WalletContextType {
  /** Wallet info (null if not loaded or user not authenticated) */
  wallet: WalletInfo | null;
  /** Whether wallet info is being fetched */
  isLoading: boolean;
  /** Error message (null if no error) */
  error: string | null;
  /** Whether a wallet is configured (exists with an address) */
  isConfigured: boolean;
  /** Fetch wallet info from the backend */
  fetchWallet: () => Promise<void>;
  /** Clear current error */
  clearError: () => void;
}

// =============================================================================
// Context
// =============================================================================

const WalletContext = createContext<WalletContextType | undefined>(undefined);

// =============================================================================
// Provider
// =============================================================================

interface WalletProviderProps {
  children: React.ReactNode;
}

export function WalletProvider({ children }: Readonly<WalletProviderProps>) {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const { user } = useAuth();
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derive authentication state from user presence
  const isAuthenticated = user !== null;

  // Track if component is mounted to prevent state updates after unmount
  const isMounted = useRef(true);

  // ---------------------------------------------------------------------------
  // Derived State
  // ---------------------------------------------------------------------------

  const isConfigured = wallet?.exists ?? false;

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const fetchWallet = useCallback(async () => {
    if (!isAuthenticated) {
      setWallet(null);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const tokens = syftClient.getTokens();
      const accessToken = tokens?.accessToken ?? '';

      const response = await fetch('/api/v1/wallet/', {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        if (response.status === 401) {
          setWallet(null);
          return;
        }
        throw new Error('Failed to fetch wallet info');
      }

      const data = (await response.json()) as WalletInfo;

      if (isMounted.current) {
        setWallet(data);
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

  // Fetch wallet info when user logs in or changes
  useEffect(() => {
    if (user) {
      void fetchWallet();
    } else {
      setWallet(null);
    }
  }, [user]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Context Value
  // ---------------------------------------------------------------------------

  const value: WalletContextType = {
    wallet,
    isLoading,
    error,
    isConfigured,
    fetchWallet,
    clearError
  };

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

// =============================================================================
// Hook
// =============================================================================

/**
 * Hook to access wallet context
 * @throws Error if used outside WalletProvider
 */
export function useWalletContext(): WalletContextType {
  const context = useContext(WalletContext);
  if (context === undefined) {
    throw new Error('useWalletContext must be used within a WalletProvider');
  }
  return context;
}

// =============================================================================
// Exports
// =============================================================================

export { WalletContext };
export type { WalletContextType };
