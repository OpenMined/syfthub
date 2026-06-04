/**
 * useCollectiveQueryReadiness
 *
 * Decides whether the current user can query a Collective API right now — i.e.
 * whether they are settled with every paid member. Mirrors the per-wallet
 * threshold logic of the chat precheck / accounts modal:
 *
 * - prepaid members: funded when the publisher wallet balance (per credits_url,
 *   deduped by owner) is >= the per-request price.
 * - MPP members: funded when the single Hub wallet is configured and holds at
 *   least the summed MPP per-request price.
 * - free members never block.
 *
 * Returns a coarse status the UI can colour: 'ready' (green), 'blocked' (red),
 * 'loading', or 'idle' (nothing to check / disabled).
 */
import { useMemo } from 'react';

import type { PrepaidWalletDescriptor } from '@/hooks/use-prepaid-wallet-balances';
import type { CollectiveBillingSummary } from '@/lib/collectives-api';

import { useQuery } from '@tanstack/react-query';

import { useWalletContext } from '@/context/wallet-context';
import {
  dedupeWalletsByKey,
  distinctWalletOwners,
  fetchWalletBalances
} from '@/hooks/use-prepaid-wallet-balances';
import { useWalletBalance } from '@/hooks/use-wallet-api';
import { billingSummaryKeys } from '@/lib/query-keys';
import { getSatelliteToken } from '@/lib/xendit-client';

export type QueryReadiness = 'idle' | 'loading' | 'ready' | 'blocked';

export function useCollectiveQueryReadiness(
  summary: CollectiveBillingSummary | null | undefined,
  enabled: boolean
): QueryReadiness {
  const wallets = useMemo<PrepaidWalletDescriptor[]>(() => {
    if (!summary) return [];
    const descriptors: PrepaidWalletDescriptor[] = [];
    for (const member of summary.members) {
      const b = member.billing;
      if (b.kind !== 'prepaid' || !b.credits_url || !member.endpoint_owner_username) continue;
      descriptors.push({
        walletKey: b.credits_url,
        creditsUrl: b.credits_url,
        owner: member.endpoint_owner_username,
        threshold: b.price_per_unit ?? 1
      });
    }
    return dedupeWalletsByKey(descriptors);
  }, [summary]);

  const hasMpp = (summary?.mpp_count ?? 0) > 0;
  const mppTotal = useMemo(() => {
    if (!summary) return 0;
    return summary.members
      .filter((m) => m.billing.kind === 'mpp')
      .reduce((sum, m) => sum + (m.billing.price_per_unit ?? 0), 0);
  }, [summary]);

  const { isConfigured } = useWalletContext();
  const { balance: walletBalance } = useWalletBalance();

  const creditsUrls = useMemo(
    () => wallets.map((w) => w.creditsUrl).toSorted((a, b) => a.localeCompare(b)),
    [wallets]
  );
  const balancesQuery = useQuery({
    queryKey: billingSummaryKeys.readiness(creditsUrls),
    enabled: enabled && wallets.length > 0,
    staleTime: 15_000,
    queryFn: async ({ signal }) => {
      const owners = distinctWalletOwners(wallets);
      const tokenByOwner = new Map<string, string>();
      await Promise.all(
        owners.map(async (owner) => {
          const token = await getSatelliteToken(owner);
          if (token) tokenByOwner.set(owner, token);
        })
      );
      // walletKey === creditsUrl here, so the tuples key the balance map by URL.
      // Keep the raw null (unreachable wallet) — it must BLOCK ready below.
      const updates = await fetchWalletBalances(wallets, tokenByOwner, signal);
      const out: Record<string, number | null> = {};
      for (const [creditsUrl, balance] of updates) out[creditsUrl] = balance;
      return out;
    }
  });

  if (!enabled || !summary) return 'idle';
  // Only free members → always queryable.
  if (wallets.length === 0 && !hasMpp) return 'ready';
  if (wallets.length > 0 && balancesQuery.isLoading) return 'loading';

  const balances = balancesQuery.data ?? {};
  const prepaidReady = wallets.every((w) => {
    const balance = balances[w.creditsUrl];
    return typeof balance === 'number' && balance >= w.threshold;
  });
  const mppReady = !hasMpp || (isConfigured && (walletBalance?.balance ?? 0) >= mppTotal);

  return prepaidReady && mppReady ? 'ready' : 'blocked';
}
