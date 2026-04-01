/**
 * Wallet TanStack Query Hooks
 *
 * TanStack Query wrappers for wallet API operations.
 * Provides caching, auto-refetching, and query invalidation.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { useWalletContext } from '@/context/wallet-context';
import { POLLING_INTERVAL_MS, WalletAPIClient } from '@/hooks/use-wallet-api';
import { walletKeys } from '@/lib/query-keys';

// Singleton wallet client
let walletClientInstance: WalletAPIClient | null = null;

function getWalletClient(): WalletAPIClient {
  walletClientInstance ??= new WalletAPIClient();
  return walletClientInstance;
}

export function useWalletInfoQuery() {
  const { isConfigured } = useWalletContext();

  return useQuery({
    queryKey: walletKeys.info(),
    queryFn: () => getWalletClient().getWallet(),
    enabled: isConfigured,
    refetchInterval: POLLING_INTERVAL_MS,
    refetchIntervalInBackground: false
  });
}

export function useWalletBalanceQuery() {
  const { isConfigured } = useWalletContext();

  return useQuery({
    queryKey: walletKeys.balance(),
    queryFn: () => getWalletClient().getBalance(),
    enabled: isConfigured,
    refetchInterval: POLLING_INTERVAL_MS,
    refetchIntervalInBackground: false
  });
}

export function useWalletTransactionsQuery() {
  const { isConfigured } = useWalletContext();

  return useQuery({
    queryKey: walletKeys.transactions(),
    queryFn: () => getWalletClient().getTransactions(),
    enabled: isConfigured,
    refetchInterval: POLLING_INTERVAL_MS,
    refetchIntervalInBackground: false
  });
}

/**
 * Hook to invalidate all wallet queries.
 * Useful after wallet operations (create, import, update).
 */
export function useInvalidateWalletQueries() {
  const queryClient = useQueryClient();

  return () => {
    void queryClient.invalidateQueries({ queryKey: walletKeys.all });
  };
}
