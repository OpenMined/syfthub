/**
 * React Query hook for a shared endpoint's billing summary — aggregate
 * per-currency price plus per-member settlement metadata.
 *
 * Pass `sharedSlug` to scope to a curated subset; omit it (or pass `'all'`)
 * for the default `collective/<slug>` shared endpoint covering all approved
 * members. See `lib/collectives-api.ts` for the wire contract.
 */
import { useQuery } from '@tanstack/react-query';

import { getCollectiveBillingSummary } from '@/lib/collectives-api';
import { billingSummaryKeys } from '@/lib/query-keys';

export function useCollectiveBilling(
  collectiveSlug: string | undefined,
  sharedSlug?: string,
  options: { enabled?: boolean } = {}
) {
  const enabled = (options.enabled ?? true) && Boolean(collectiveSlug);
  return useQuery({
    queryKey: billingSummaryKeys.bySharedEndpoint(collectiveSlug ?? '', sharedSlug),
    queryFn: () =>
      collectiveSlug ? getCollectiveBillingSummary(collectiveSlug, sharedSlug) : null,
    enabled,
    staleTime: 60_000
  });
}
