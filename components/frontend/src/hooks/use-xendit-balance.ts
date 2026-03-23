import { useCallback, useEffect, useState } from 'react';

import { syftClient } from '@/lib/sdk-client';

interface BalanceResponse {
  remaining_units: number;
  total_purchased: number;
  unit_type: string;
}

interface UseXenditBalanceReturn {
  /** Remaining credits */
  remaining: number | null;
  /** Total purchased credits */
  total: number | null;
  /** Unit type (e.g. "requests") */
  unitType: string | null;
  /** Whether balance is being fetched */
  isLoading: boolean;
  /** Error message */
  error: string | null;
  /** Re-fetch the balance */
  refetch: () => Promise<void>;
}

/**
 * Hook for fetching Xendit bundle balance from Syft Space.
 *
 * Flow:
 * 1. Get satellite token for the Syft Space tenant
 * 2. GET {spaceBaseUrl}{balancePath}?unit_type=requests
 * 3. Return remaining/total credits
 *
 * Fetches once on mount, then on-demand via refetch().
 */
export function useXenditBalance(
  spaceBaseUrl: string | undefined,
  ownerUsername: string | undefined,
  balancePath: string | undefined
): UseXenditBalanceReturn {
  const [remaining, setRemaining] = useState<number | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [unitType, setUnitType] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBalance = useCallback(async () => {
    if (!spaceBaseUrl || !ownerUsername || !balancePath) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
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
          setRemaining(0);
          setTotal(0);
          setUnitType('requests');
          return;
        }
        throw new Error(`Failed to fetch balance (${String(response.status)})`);
      }

      const data = (await response.json()) as BalanceResponse;
      setRemaining(data.remaining_units);
      setTotal(data.total_purchased);
      setUnitType(data.unit_type);
    } catch (error_) {
      const message = error_ instanceof Error ? error_.message : 'Failed to fetch balance.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [spaceBaseUrl, ownerUsername, balancePath]);

  // Fetch on mount
  useEffect(() => {
    void fetchBalance();
  }, [fetchBalance]);

  return { remaining, total, unitType, isLoading, error, refetch: fetchBalance };
}
