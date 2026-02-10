/**
 * Accounting Hooks
 *
 * Custom hooks for consuming accounting context and API operations.
 * Provides convenient access to:
 * - Accounting credentials (stored in backend)
 * - API operations (balance, transactions, delegation)
 *
 * @example
 * ```tsx
 * import {
 *   useAccounting,
 *   useAccountingCredentials,
 *   useAccountingReady,
 *   useAccountingUser,
 *   useAccountingBalance,
 *   useTransactions,
 * } from '@/hooks/use-accounting';
 * ```
 */

import type { AccountingCredentials } from '@/lib/types';

import { useAccountingContext } from '@/context/accounting-context';

// Re-export API hooks for convenience
// Note: Some hooks are deprecated but re-exported for backward compatibility
/* eslint-disable @typescript-eslint/no-deprecated -- Intentional re-export for backward compatibility */
export {
  useAccountingClient,
  useAccountingUser,
  useAccountingBalance,
  useTransactions,
  useTransaction,
  useCreateTransaction,
  useTransactionToken,
  useDelegatedTransaction
} from './use-accounting-api';
/* eslint-enable @typescript-eslint/no-deprecated */

// =============================================================================
// Main Hook
// =============================================================================

/**
 * Main hook for accessing all accounting functionality
 *
 * @example
 * ```tsx
 * function PaymentSettings() {
 *   const { credentials, isConfigured, updateCredentials, isLoading } = useAccounting();
 *
 *   if (!isConfigured) {
 *     return <SetupForm onSubmit={updateCredentials} />;
 *   }
 *
 *   return <CredentialsView credentials={credentials} />;
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
 * Hook for accessing accounting credentials
 *
 * @example
 * ```tsx
 * const credentials = useAccountingCredentials();
 * if (credentials?.url && credentials?.has_api_token) {
 *   // Credentials are configured - use credentials.url, credentials.email, credentials.account_id
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
 *   return <ErrorMessage message={error} onDismiss={clearError} />;
 * }
 * ```
 */
export function useAccountingError(): {
  error: string | null;
  clearError: () => void;
} {
  const { error, clearError } = useAccountingContext();
  return { error, clearError };
}

// =============================================================================
// Utility Hooks
// =============================================================================

/**
 * Hook that returns true if accounting is configured and ready to use
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
  const { isConfigured, credentials } = useAccountingContext();
  return isConfigured && credentials !== null;
}
