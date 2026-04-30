/**
 * Xendit subscription hooks.
 *
 * Surfaces the publisher-side wallets a user has funded. Subscription rows
 * live on the SyftHub backend (just metadata + last-known balance), but the
 * authoritative balance is always fetched live from the publisher's
 * `credits_url` with a per-publisher satellite token.
 */

import { useCallback } from 'react';

import type { XenditSubscription } from '@/lib/types';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/context/auth-context';
import { WalletAPIClient } from '@/hooks/use-wallet-api';
import { walletKeys } from '@/lib/query-keys';
import { fetchBalance, getSatelliteToken } from '@/lib/xendit-client';

let walletClientInstance: WalletAPIClient | null = null;

function getWalletClient(): WalletAPIClient {
  walletClientInstance ??= new WalletAPIClient();
  return walletClientInstance;
}

export interface RegisterXenditSubscriptionInput {
  creditsUrl: string;
  paymentUrl: string;
  endpointOwner: string;
  endpointSlug?: string | null;
  currency: string;
  lastKnownBalance?: number | null;
}

export function useXenditSubscriptions(options: { enabled?: boolean } = {}) {
  const { user } = useAuth();
  const isAuthenticated = user !== null;
  const enabled = (options.enabled ?? true) && isAuthenticated;

  return useQuery({
    queryKey: walletKeys.subscriptions(),
    queryFn: async () => {
      const result = await getWalletClient().listXenditSubscriptions();
      return result.subscriptions;
    },
    enabled,
    staleTime: 30_000
  });
}

export function useRegisterXenditSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: RegisterXenditSubscriptionInput) => {
      return getWalletClient().upsertXenditSubscription({
        credits_url: input.creditsUrl,
        payment_url: input.paymentUrl,
        endpoint_owner: input.endpointOwner,
        endpoint_slug: input.endpointSlug ?? null,
        currency: input.currency,
        last_known_balance: input.lastKnownBalance ?? null
      });
    },
    onSuccess: (row) => {
      queryClient.setQueryData<XenditSubscription[] | undefined>(
        walletKeys.subscriptions(),
        (previous) => {
          if (!previous) return [row];
          const index = previous.findIndex((p) => p.credits_url === row.credits_url);
          if (index === -1) return [row, ...previous];
          const next = [...previous];
          next[index] = row;
          return next;
        }
      );
    }
  });
}

export function useDeleteXenditSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      await getWalletClient().deleteXenditSubscription(id);
      return id;
    },
    onSuccess: (id) => {
      queryClient.setQueryData<XenditSubscription[] | undefined>(
        walletKeys.subscriptions(),
        (previous) => previous?.filter((p) => p.id !== id) ?? []
      );
    }
  });
}

export interface SubscriptionBalanceResult {
  balance: number | null;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  refetch: () => Promise<unknown>;
}

/**
 * Live-fetch a subscription's balance from its publisher.
 *
 * Mints a satellite token for the endpoint owner and queries credits_url.
 * Polls every `pollIntervalMs` while `enabled` is true (typically while the
 * credits panel is open). Returns `null` balance when fetching fails.
 */
export function useSubscriptionBalance(
  subscription: Pick<XenditSubscription, 'credits_url' | 'endpoint_owner'>,
  options: { enabled?: boolean; pollIntervalMs?: number } = {}
): SubscriptionBalanceResult {
  const { enabled = true, pollIntervalMs } = options;

  const query = useQuery({
    queryKey: walletKeys.subscriptionBalance(subscription.credits_url),
    queryFn: async ({ signal }) => {
      const token = await getSatelliteToken(subscription.endpoint_owner);
      if (!token) throw new Error('Failed to mint satellite token');
      const balance = await fetchBalance(subscription.credits_url, token, signal);
      return balance;
    },
    enabled,
    refetchInterval: pollIntervalMs,
    refetchIntervalInBackground: false,
    staleTime: 5000
  });

  return {
    balance: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    refetch: query.refetch
  };
}

/**
 * Imperative helper for the auto-registration sites (xendit-policy-content,
 * subscription-gate-modal). Wraps the mutation in a stable callback that
 * silently swallows errors — registration is best-effort and shouldn't block
 * payment confirmation.
 */
export function useRegisterOnFundingDetected() {
  const { mutateAsync } = useRegisterXenditSubscription();

  return useCallback(
    async (input: RegisterXenditSubscriptionInput) => {
      try {
        await mutateAsync(input);
      } catch {
        // Best-effort: a failed registration here is not fatal. The next
        // balance check will retry.
      }
    },
    [mutateAsync]
  );
}
