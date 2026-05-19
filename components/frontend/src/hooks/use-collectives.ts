/**
 * React Query hooks for the Collectives feature.
 *
 * Queries are cached by `collectiveKeys`; every mutation invalidates the
 * affected collective so lists, detail pages and member tables stay in sync.
 */
import { useCallback } from 'react';

import type {
  Collective,
  CollectiveCreateInput,
  CollectiveUpdateInput,
  InvitationDecision,
  MembershipStatus,
  ReviewDecision
} from '@/lib/collectives-api';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createCollective,
  deleteCollective,
  getCollectiveBySlug,
  inviteEndpoint,
  listCollectives,
  listCollectivesPaginated,
  listMembers,
  removeMember,
  requestJoin,
  respondToInvitation,
  reviewRequest,
  updateCollective
} from '@/lib/collectives-api';
import { collectiveKeys } from '@/lib/query-keys';

// =============================================================================
// Queries
// =============================================================================

/** List collectives, optionally filtered to those owned by `ownerId`. */
export function useCollectives(ownerId?: number) {
  return useQuery({
    queryKey: collectiveKeys.list(ownerId),
    queryFn: () => listCollectives({ ownerId, limit: 100 })
  });
}

/**
 * Paginated collectives with server-side search — backs the Collectives tab on
 * the Browse page. Mirrors `usePaginatedPublicEndpoints`.
 */
export function usePaginatedCollectives(page: number, pageSize = 12, search?: string) {
  return useQuery({
    queryKey: collectiveKeys.paginated(page, pageSize, search),
    queryFn: () => listCollectivesPaginated({ page, limit: pageSize, search }),
    placeholderData: keepPreviousData
  });
}

/** Fetch a single collective by slug. Resolves to `null` when not found. */
export function useCollectiveBySlug(slug: string | undefined) {
  return useQuery({
    queryKey: collectiveKeys.detail(slug ?? ''),
    queryFn: () => (slug ? getCollectiveBySlug(slug) : null),
    enabled: Boolean(slug)
  });
}

/** List a collective's memberships, optionally filtered by workflow status. */
export function useCollectiveMembers(collectiveId: number | undefined, status?: MembershipStatus) {
  return useQuery({
    queryKey: collectiveKeys.members(collectiveId ?? 0, status),
    queryFn: () => (collectiveId ? listMembers(collectiveId, status) : []),
    enabled: Boolean(collectiveId)
  });
}

// =============================================================================
// Mutations
// =============================================================================

function useInvalidateAllCollectives() {
  const queryClient = useQueryClient();
  return useCallback(
    () => void queryClient.invalidateQueries({ queryKey: collectiveKeys.all }),
    [queryClient]
  );
}

function useInvalidateMembers() {
  const queryClient = useQueryClient();
  return useCallback(
    (collectiveId: number) =>
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.members(collectiveId) }),
    [queryClient]
  );
}

/** Create a collective. Invalidates collective lists on success. */
export function useCreateCollective() {
  const invalidate = useInvalidateAllCollectives();
  return useMutation({
    mutationFn: (input: CollectiveCreateInput) => createCollective(input),
    onSuccess: invalidate
  });
}

/** Update a collective's settings. */
export function useUpdateCollective() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateAllCollectives();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: CollectiveUpdateInput }) =>
      updateCollective(id, input),
    onSuccess: (collective: Collective) => {
      invalidate();
      queryClient.setQueryData(collectiveKeys.detail(collective.slug), collective);
    }
  });
}

/** Delete a collective. */
export function useDeleteCollective() {
  const invalidate = useInvalidateAllCollectives();
  return useMutation({
    mutationFn: (id: number) => deleteCollective(id),
    onSuccess: invalidate
  });
}

/** Request that one of the current user's endpoints join a collective. */
export function useRequestJoin() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      requestJoin(collectiveId, endpointId),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Approve or reject a pending join request (collective owner). */
export function useReviewRequest() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({
      collectiveId,
      endpointId,
      decision
    }: {
      collectiveId: number;
      endpointId: number;
      decision: ReviewDecision;
    }) => reviewRequest(collectiveId, endpointId, decision),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Remove an endpoint from a collective. */
export function useRemoveMember() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      removeMember(collectiveId, endpointId),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Invite an endpoint into a collective (collective owner). */
export function useInviteEndpoint() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      inviteEndpoint(collectiveId, endpointId),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Accept or decline a collective invitation (endpoint owner). */
export function useRespondToInvitation() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({
      collectiveId,
      endpointId,
      decision
    }: {
      collectiveId: number;
      endpointId: number;
      decision: InvitationDecision;
    }) => respondToInvitation(collectiveId, endpointId, decision),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}
