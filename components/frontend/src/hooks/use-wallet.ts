/**
 * Wallet Hooks
 *
 * Custom hooks for consuming wallet context and API operations.
 * Provides convenient access to:
 * - Wallet info (stored in backend)
 * - API operations (balance, transactions)
 *
 * @example
 * ```tsx
 * import {
 *   useWallet,
 *   useWalletBalance,
 *   useWalletTransactions,
 * } from '@/hooks/use-wallet';
 * ```
 */

import type { WalletInfo } from '@/lib/types';

import { useWalletContext } from '@/context/wallet-context';

// Re-export API hooks for convenience
export { useWalletClient, useWalletBalance, useWalletTransactions } from './use-wallet-api';

// =============================================================================
// Main Hook
// =============================================================================

/**
 * Main hook for accessing all wallet functionality
 *
 * @example
 * ```tsx
 * function WalletSettings() {
 *   const { wallet, isConfigured, isLoading } = useWallet();
 *
 *   if (!isConfigured) {
 *     return <SetupForm />;
 *   }
 *
 *   return <WalletView wallet={wallet} />;
 * }
 * ```
 */
export function useWallet() {
  return useWalletContext();
}

// =============================================================================
// Selector Hooks
// =============================================================================

/**
 * Hook for accessing wallet info
 */
export function useWalletInfo(): WalletInfo | null {
  const { wallet } = useWalletContext();
  return wallet;
}

/**
 * Hook for accessing current error state
 */
export function useWalletError(): {
  error: string | null;
  clearError: () => void;
} {
  const { error, clearError } = useWalletContext();
  return { error, clearError };
}

// =============================================================================
// Utility Hooks
// =============================================================================

/**
 * Hook that returns true if wallet is configured and ready to use
 */
export function useWalletReady(): boolean {
  const { isConfigured, wallet } = useWalletContext();
  return isConfigured && wallet !== null;
}
