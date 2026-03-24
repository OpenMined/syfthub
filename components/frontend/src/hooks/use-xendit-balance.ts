import { useQuery } from '@tanstack/react-query';

import { xenditKeys } from '@/lib/query-keys';
import { syftClient } from '@/lib/sdk-client';

interface BalanceResponse {
  remaining_units: number;
  total_purchased: number;
  unit_type: string;
}

const DEFAULT_BALANCE: BalanceResponse = {
  remaining_units: 0,
  total_purchased: 0,
  unit_type: 'requests'
};

async function fetchXenditBalance(
  spaceBaseUrl: string,
  ownerUsername: string,
  balancePath: string
): Promise<BalanceResponse> {
  // Get satellite token for the Syft Space tenant
  const tokenResponse = await syftClient.auth.getSatelliteToken(ownerUsername);
  const token = tokenResponse.targetToken;

  // Fetch balance from Syft Space
  const url = `${spaceBaseUrl}${balancePath}?unit_type=requests`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    if (response.status === 404) {
      // No balance yet — user hasn't purchased any bundles
      return DEFAULT_BALANCE;
    }
    throw new Error(`Failed to fetch balance (${String(response.status)})`);
  }

  return (await response.json()) as BalanceResponse;
}

/**
 * Hook for fetching Xendit bundle balance from Syft Space.
 *
 * Flow:
 * 1. Get satellite token for the Syft Space tenant
 * 2. GET {spaceBaseUrl}{balancePath}?unit_type=requests
 * 3. Return remaining/total credits
 *
 * Uses React Query for caching and automatic state management.
 */
export function useXenditBalance(
  spaceBaseUrl: string | undefined,
  ownerUsername: string | undefined,
  balancePath: string | undefined
) {
  const enabled = !!spaceBaseUrl && !!ownerUsername && !!balancePath;
  const query = useQuery({
    queryKey: xenditKeys.balance(spaceBaseUrl ?? '', ownerUsername ?? '', balancePath ?? ''),
    queryFn: () => fetchXenditBalance(spaceBaseUrl ?? '', ownerUsername ?? '', balancePath ?? ''),
    enabled
  });

  return {
    /** Remaining credits */
    remaining: query.data?.remaining_units ?? null,
    /** Total purchased credits */
    total: query.data?.total_purchased ?? null,
    /** Unit type (e.g. "requests") */
    unitType: query.data?.unit_type ?? null,
    /** Whether balance is being fetched */
    isLoading: query.isLoading,
    /** Error message */
    error:
      query.error instanceof Error
        ? query.error.message
        : query.error
          ? 'Failed to fetch balance.'
          : null,
    /** Re-fetch the balance */
    refetch: query.refetch
  };
}
