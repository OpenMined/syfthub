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

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createSharedEndpoint,
  deleteSharedEndpoint,
  getSharedEndpoint,
  listSharedEndpoints,
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
 * Bulk-load shared endpoints for an array of collectives.
 *
 * Fans out one cached query per collective so each result is cached + revalidated
 * independently (`useSharedEndpoints` consumers also benefit from the cache).
 * Combines the per-collective results into a flat list of
 * `{ collective, shared }` pairs convenient for rendering in the chat
 * add-sources modal.
 */
export function useSharedEndpointsForCollectives(collectives: Collective[]) {
  return useQueries({
    queries: collectives.map((collective) => ({
      queryKey: sharedEndpointKeys.byCollective(collective.id),
      queryFn: () => listSharedEndpoints(collective.id),
      staleTime: 60_000
    })),
    combine: (results) => ({
      data: results.flatMap((result, index) => {
        const collective = collectives[index];
        if (!collective) return [];
        return (result.data ?? []).map((shared) => ({ collective, shared }));
      }),
      isLoading: results.some((result) => result.isLoading)
    })
  });
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
 * Invalidator shared across mutations: every CUD operation invalidates the
 * collective's list view AND the collective's detail (so the sidebar count
 * stays consistent with the admin tab) AND the by-slug list (the public
 * detail page reads via slug, not id).
 */
function useInvalidateForCollective() {
  const queryClient = useQueryClient();
  return useCallback(
    (collectiveId: number, collectiveSlug?: string) => {
      void queryClient.invalidateQueries({
        queryKey: sharedEndpointKeys.byCollective(collectiveId)
      });
      if (collectiveSlug) {
        void queryClient.invalidateQueries({
          queryKey: sharedEndpointKeys.byCollectiveSlug(collectiveSlug)
        });
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
