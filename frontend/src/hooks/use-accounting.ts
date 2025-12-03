/**
 * Accounting Hooks
 *
 * Custom hooks for consuming accounting context.
 * Provides convenient access to vault state and actions.
 */

import type { AccountingCredentials, AccountingError, AccountingVaultStatus } from '@/lib/types';

import { useAccountingContext } from '@/context/accounting-context';

// =============================================================================
// Main Hook
// =============================================================================

/**
 * Main hook for accessing all accounting functionality
 *
 * @example
 * ```tsx
 * function PaymentSettings() {
 *   const { status, credentials, createVault, unlock, lock } = useAccounting();
 *
 *   if (status.isEmpty) {
 *     return <SetupForm onSubmit={createVault} />;
 *   }
 *
 *   if (status.isLocked) {
 *     return <UnlockForm onSubmit={unlock} />;
 *   }
 *
 *   return <CredentialsView credentials={credentials} onLock={lock} />;
 * }
 * ```
 */
export function useAccounting() {
  return useAccountingContext();
}

// =============================================================================
// Selector Hooks
// =============================================================================

/**
 * Hook for accessing just the vault status
 *
 * @example
 * ```tsx
 * const { isConfigured, isUnlocked } = useAccountingStatus();
 * ```
 */
export function useAccountingStatus(): AccountingVaultStatus {
  const { status } = useAccountingContext();
  return status;
}

/**
 * Hook for accessing decrypted credentials (null if locked)
 *
 * @example
 * ```tsx
 * const credentials = useAccountingCredentials();
 * if (credentials) {
 *   // Use credentials.url, credentials.email, credentials.password
 * }
 * ```
 */
export function useAccountingCredentials(): AccountingCredentials | null {
  const { credentials } = useAccountingContext();
  return credentials;
}

/**
 * Hook for accessing current error state
 *
 * @example
 * ```tsx
 * const { error, clearError } = useAccountingError();
 * if (error) {
 *   return <ErrorMessage error={error} onDismiss={clearError} />;
 * }
 * ```
 */
export function useAccountingError(): {
  error: AccountingError | null;
  clearError: () => void;
} {
  const { error, clearError } = useAccountingContext();
  return { error, clearError };
}

/**
 * Hook for accessing loading and rate limit state
 *
 * @example
 * ```tsx
 * const { isLoading, waitTime } = useAccountingLoadingState();
 * ```
 */
export function useAccountingLoadingState(): {
  isLoading: boolean;
  waitTime: number;
} {
  const { isLoading, waitTime } = useAccountingContext();
  return { isLoading, waitTime };
}

/**
 * Hook for vault management actions
 *
 * @example
 * ```tsx
 * const { createVault, deleteVault } = useAccountingVaultActions();
 * ```
 */
export function useAccountingVaultActions() {
  const { createVault, unlock, lock, deleteVault, updateVault } = useAccountingContext();
  return { createVault, unlock, lock, deleteVault, updateVault };
}

// =============================================================================
// Utility Hooks
// =============================================================================

/**
 * Hook that returns true if vault is ready to use (unlocked with credentials)
 *
 * @example
 * ```tsx
 * const isReady = useAccountingReady();
 * if (!isReady) {
 *   return <PaymentSetupPrompt />;
 * }
 * ```
 */
export function useAccountingReady(): boolean {
  const { status, credentials } = useAccountingContext();
  return status.isUnlocked && credentials !== null;
}

/**
 * Hook that returns true if crypto is supported in the browser
 *
 * @example
 * ```tsx
 * const isSupported = useAccountingSupported();
 * if (!isSupported) {
 *   return <BrowserNotSupportedMessage />;
 * }
 * ```
 */
export function useAccountingSupported(): boolean {
  // Check if Web Crypto API is available
  try {
    if (typeof crypto === 'undefined' || !crypto.subtle) {
      return false;
    }
    return typeof crypto.getRandomValues === 'function';
  } catch {
    return false;
  }
}
