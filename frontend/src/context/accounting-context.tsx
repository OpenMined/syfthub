/**
 * Accounting Context
 *
 * React context for managing encrypted accounting credentials.
 * Provides state and actions for vault operations.
 *
 * Features:
 * - Vault status tracking (configured, unlocked, locked)
 * - Encrypted credential storage
 * - Rate limiting on unlock attempts
 * - Auto-lock after inactivity
 * - Integration with logout flow
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import type { AccountingCredentials, AccountingError, AccountingVaultStatus } from '@/lib/types';

import { AccountingStorage, DEFAULT_AUTO_LOCK_TIMEOUT } from '@/lib/accounting-storage';

// =============================================================================
// Types
// =============================================================================

interface AccountingContextType {
  // State
  /** Current vault status */
  status: AccountingVaultStatus;
  /** Decrypted credentials (null if locked) */
  credentials: AccountingCredentials | null;
  /** Current error (null if no error) */
  error: AccountingError | null;
  /** Whether an async operation is in progress */
  isLoading: boolean;
  /** Seconds until next unlock attempt is allowed (rate limiting) */
  waitTime: number;

  // Actions
  /** Create a new vault with encrypted credentials */
  createVault: (credentials: AccountingCredentials, pin: string) => Promise<boolean>;
  /** Unlock existing vault with PIN */
  unlock: (pin: string) => Promise<boolean>;
  /** Lock vault (clear session credentials) */
  lock: () => void;
  /** Delete vault entirely */
  deleteVault: () => void;
  /** Update credentials (requires current PIN) */
  updateVault: (
    credentials: AccountingCredentials,
    currentPin: string,
    newPin?: string
  ) => Promise<boolean>;
  /** Clear current error */
  clearError: () => void;
  /** Refresh status from storage */
  refreshStatus: () => void;
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
  /** Auto-lock timeout in minutes (default: 15) */
  autoLockTimeout?: number;
}

export function AccountingProvider({
  children,
  autoLockTimeout = DEFAULT_AUTO_LOCK_TIMEOUT
}: Readonly<AccountingProviderProps>) {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const [status, setStatus] = useState<AccountingVaultStatus>(() => AccountingStorage.getStatus());
  const [credentials, setCredentials] = useState<AccountingCredentials | null>(() =>
    AccountingStorage.getCredentials()
  );
  const [error, setError] = useState<AccountingError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [waitTime, setWaitTime] = useState(0);

  // Track if component is mounted to prevent state updates after unmount
  const isMounted = useRef(true);

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const refreshStatus = useCallback(() => {
    if (!isMounted.current) return;
    setStatus(AccountingStorage.getStatus());
    setCredentials(AccountingStorage.getCredentials());
  }, []);

  const handleError = useCallback((err: unknown) => {
    if (!isMounted.current) return;

    if (err && typeof err === 'object' && 'type' in err) {
      const accountingError = err as AccountingError;
      setError(accountingError);

      // Update wait time for rate limiting
      if (accountingError.type === 'RATE_LIMITED' && accountingError.waitTime) {
        setWaitTime(accountingError.waitTime);
      }
    } else {
      setError({
        type: 'STORAGE_UNAVAILABLE',
        message: err instanceof Error ? err.message : 'An unknown error occurred'
      });
    }
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

  // Auto-lock check interval
  useEffect(() => {
    const checkAutoLock = () => {
      if (!isMounted.current) return;

      const wasLocked = AccountingStorage.checkAutoLock(autoLockTimeout);
      if (wasLocked) {
        refreshStatus();
      }
    };

    // Check immediately
    checkAutoLock();

    // Check every minute
    const interval = setInterval(checkAutoLock, 60_000);

    return () => {
      clearInterval(interval);
    };
  }, [autoLockTimeout, refreshStatus]);

  // Activity tracking
  useEffect(() => {
    const updateActivity = () => {
      if (AccountingStorage.isUnlocked()) {
        AccountingStorage.updateActivity();
      }
    };

    // Update on user interaction
    globalThis.addEventListener('click', updateActivity);
    globalThis.addEventListener('keydown', updateActivity);

    return () => {
      globalThis.removeEventListener('click', updateActivity);
      globalThis.removeEventListener('keydown', updateActivity);
    };
  }, []);

  // Logout event listener
  useEffect(() => {
    const handleLogout = () => {
      if (!isMounted.current) return;

      AccountingStorage.lock();
      refreshStatus();
    };

    globalThis.addEventListener('syft:logout', handleLogout);

    return () => {
      globalThis.removeEventListener('syft:logout', handleLogout);
    };
  }, [refreshStatus]);

  // Rate limit countdown
  useEffect(() => {
    if (waitTime <= 0) return;

    const interval = setInterval(() => {
      if (!isMounted.current) return;

      setWaitTime((previous) => {
        if (previous <= 1) {
          return 0;
        }
        return previous - 1;
      });
    }, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [waitTime]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const createVault = useCallback(
    async (creds: AccountingCredentials, pin: string): Promise<boolean> => {
      if (!isMounted.current) return false;

      try {
        setIsLoading(true);
        setError(null);

        await AccountingStorage.createVault(creds, pin);

        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          refreshStatus();
        }

        return true;
      } catch (error_) {
        handleError(error_);
        return false;
      } finally {
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [refreshStatus, handleError]
  );

  const unlock = useCallback(
    async (pin: string): Promise<boolean> => {
      if (!isMounted.current) return false;

      // Check rate limiting first
      const rateLimit = AccountingStorage.checkRateLimit();
      if (!rateLimit.allowed) {
        setWaitTime(rateLimit.waitTime);
        setError({
          type: 'RATE_LIMITED',
          message: `Too many attempts. Please wait ${String(rateLimit.waitTime)} seconds.`,
          waitTime: rateLimit.waitTime
        });
        return false;
      }

      try {
        setIsLoading(true);
        setError(null);

        await AccountingStorage.unlock(pin);

        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          refreshStatus();
          setWaitTime(0);
        }

        return true;
      } catch (error_) {
        handleError(error_);
        return false;
      } finally {
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [refreshStatus, handleError]
  );

  const lock = useCallback(() => {
    AccountingStorage.lock();
    refreshStatus();
  }, [refreshStatus]);

  const deleteVault = useCallback(() => {
    AccountingStorage.deleteVault();
    setError(null);
    setWaitTime(0);
    refreshStatus();
  }, [refreshStatus]);

  const updateVault = useCallback(
    async (creds: AccountingCredentials, currentPin: string, newPin?: string): Promise<boolean> => {
      if (!isMounted.current) return false;

      try {
        setIsLoading(true);
        setError(null);

        await AccountingStorage.updateVault(creds, currentPin, newPin);

        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          refreshStatus();
        }

        return true;
      } catch (error_) {
        handleError(error_);
        return false;
      } finally {
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Runtime check needed
        if (isMounted.current) {
          setIsLoading(false);
        }
      }
    },
    [refreshStatus, handleError]
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // ---------------------------------------------------------------------------
  // Context Value
  // ---------------------------------------------------------------------------

  const value: AccountingContextType = {
    status,
    credentials,
    error,
    isLoading,
    waitTime,
    createVault,
    unlock,
    lock,
    deleteVault,
    updateVault,
    clearError,
    refreshStatus
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
