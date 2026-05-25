/**
 * React Query hooks for collective shared endpoints — curated subsets of a
 * collective's approved members. See `lib/collectives-api.ts` for the wire
 * contracts and `components/backend/.../collective_service.py` for resolution
 * semantics (intersection with currently approved members).
 */
import { useCallback } from 'react';

import type {
  Collective,
  CollectiveSharedEndpoint,
  CollectiveSharedEndpointCreateInput,
  CollectiveSharedEndpointUpdateInput
} from '@/lib/collectives-api';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createSharedEndpoint,
  deleteSharedEndpoint,
  getSharedEndpoint,
  listSharedEndpoints,
  listSharedEndpointsBulk,
  listSharedEndpointsByCollectiveSlug,
  updateSharedEndpoint
} from '@/lib/collectives-api';
import { collectiveKeys, sharedEndpointKeys } from '@/lib/query-keys';

// =============================================================================
// Queries
// =============================================================================

/** List a collective's shared endpoints by parent id. */
export function useSharedEndpoints(collectiveId: number | undefined) {
  return useQuery({
    queryKey: sharedEndpointKeys.byCollective(collectiveId ?? 0),
    queryFn: () => (collectiveId ? listSharedEndpoints(collectiveId) : []),
    enabled: Boolean(collectiveId)
  });
}

/**
 * List a collective's shared endpoints by parent slug — useful on the public
 * detail page where the numeric id isn't always in scope before the
 * collective resolves.
 */
export function useSharedEndpointsByCollectiveSlug(collectiveSlug: string | undefined) {
  return useQuery({
    queryKey: sharedEndpointKeys.byCollectiveSlug(collectiveSlug ?? ''),
    queryFn: () => (collectiveSlug ? listSharedEndpointsByCollectiveSlug(collectiveSlug) : []),
    enabled: Boolean(collectiveSlug)
  });
}

/**
 * Bulk-load shared endpoints for an array of collectives in a single request.
 *
 * Uses the `/shared-endpoints/bulk` endpoint so the chat-view modal can pay
 * one round trip regardless of how many collectives the user can see (the
 * older per-collective fan-out scaled linearly with collective count). The
 * cache key is derived from the sorted collective ids — the list shape, not
 * the array reference identity — so re-renders that pass a new array but the
 * same ids don't refetch.
 */
export function useSharedEndpointsForCollectives(collectives: Collective[]) {
  const collectivesBySlug = new Map(collectives.map((c) => [c.slug, c]));
  const collectivesById = new Map(collectives.map((c) => [c.id, c]));
  const collectiveIds = collectives.map((c) => c.id).toSorted((a, b) => a - b);
  const query = useQuery({
    queryKey: [...sharedEndpointKeys.all, 'bulk', collectiveIds],
    queryFn: () => listSharedEndpointsBulk(collectiveIds),
    enabled: collectiveIds.length > 0,
    staleTime: 60_000
  });
  const data = (query.data ?? []).flatMap((shared) => {
    const parent =
      collectivesById.get(shared.collective_id) ?? collectivesBySlug.get(shared.collective_slug);
    return parent ? [{ collective: parent, shared }] : [];
  });
  return { data, isLoading: query.isLoading };
}

/** Get a single shared endpoint by parent id + own slug. */
export function useSharedEndpoint(
  collectiveId: number | undefined,
  sharedSlug: string | undefined
) {
  return useQuery({
    queryKey: sharedEndpointKeys.detail(collectiveId ?? 0, sharedSlug ?? ''),
    queryFn: () =>
      collectiveId && sharedSlug ? getSharedEndpoint(collectiveId, sharedSlug) : null,
    enabled: Boolean(collectiveId && sharedSlug)
  });
}

// =============================================================================
// Mutations
// =============================================================================

/**
 * Invalidator shared across mutations: every CUD operation invalidates every
 * shared-endpoint cache (list-by-id, list-by-slug, AND single-detail) plus
 * the collective's detail (so the sidebar count stays consistent with the
 * admin tab). Invalidating ``sharedEndpointKeys.all`` covers the detail key
 * too — its prefix doesn't share ``byCollective`` / ``byCollectiveSlug`` so
 * a narrower invalidation would leave ``useSharedEndpoint`` stale.
 */
function useInvalidateForCollective() {
  const queryClient = useQueryClient();
  return useCallback(
    (_collectiveId: number, collectiveSlug?: string) => {
      void queryClient.invalidateQueries({ queryKey: sharedEndpointKeys.all });
      if (collectiveSlug) {
        void queryClient.invalidateQueries({
          queryKey: collectiveKeys.detail(collectiveSlug)
        });
      }
    },
    [queryClient]
  );
}

/** Create a shared endpoint. */
export function useCreateSharedEndpoint() {
  const invalidate = useInvalidateForCollective();
  return useMutation({
    mutationFn: ({
      collectiveId,
      input
    }: {
      collectiveId: number;
      input: CollectiveSharedEndpointCreateInput;
    }) => createSharedEndpoint(collectiveId, input),
    onSuccess: (data: CollectiveSharedEndpoint) => {
      invalidate(data.collective_id, data.collective_slug);
    }
  });
}

/** Update a shared endpoint. */
export function useUpdateSharedEndpoint() {
  const invalidate = useInvalidateForCollective();
  return useMutation({
    mutationFn: ({
      collectiveId,
      sharedSlug,
      input
    }: {
      collectiveId: number;
      sharedSlug: string;
      input: CollectiveSharedEndpointUpdateInput;
    }) => updateSharedEndpoint(collectiveId, sharedSlug, input),
    onSuccess: (data: CollectiveSharedEndpoint) => {
      invalidate(data.collective_id, data.collective_slug);
    }
  });
}

/** Delete a shared endpoint. */
export function useDeleteSharedEndpoint() {
  const invalidate = useInvalidateForCollective();
  return useMutation({
    mutationFn: ({
      collectiveId,
      sharedSlug
    }: {
      collectiveId: number;
      sharedSlug: string;
      /** Pass when known so the by-slug + detail caches also invalidate. */
      collectiveSlug?: string;
    }) => deleteSharedEndpoint(collectiveId, sharedSlug),
    onSuccess: (_data, { collectiveId, collectiveSlug }) => {
      invalidate(collectiveId, collectiveSlug);
    }
  });
}
