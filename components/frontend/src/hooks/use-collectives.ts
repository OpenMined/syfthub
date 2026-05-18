/**
 * React Query hooks for the Collectives feature.
 *
 * Queries are cached by `collectiveKeys`; every mutation invalidates the
 * affected collective so lists, detail pages and member tables stay in sync.
 */
import type {
  Collective,
  CollectiveCreateInput,
  CollectiveUpdateInput,
  InvitationDecision,
  MembershipStatus,
  ReviewDecision
} from '@/lib/collectives-api';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createCollective,
  deleteCollective,
  getCollectiveBySlug,
  inviteEndpoint,
  listCollectives,
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

/** Create a collective. Invalidates collective lists on success. */
export function useCreateCollective() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CollectiveCreateInput) => createCollective(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Update a collective's settings. */
export function useUpdateCollective() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: CollectiveUpdateInput }) =>
      updateCollective(id, input),
    onSuccess: (collective: Collective) => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
      queryClient.setQueryData(collectiveKeys.detail(collective.slug), collective);
    }
  });
}

/** Delete a collective. */
export function useDeleteCollective() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCollective(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Request that one of the current user's endpoints join a collective. */
export function useRequestJoin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      requestJoin(collectiveId, endpointId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Approve or reject a pending join request (collective owner). */
export function useReviewRequest() {
  const queryClient = useQueryClient();
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Remove an endpoint from a collective. */
export function useRemoveMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      removeMember(collectiveId, endpointId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Invite an endpoint into a collective (collective owner). */
export function useInviteEndpoint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectiveId, endpointId }: { collectiveId: number; endpointId: number }) =>
      inviteEndpoint(collectiveId, endpointId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}

/** Accept or decline a collective invitation (endpoint owner). */
export function useRespondToInvitation() {
  const queryClient = useQueryClient();
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: collectiveKeys.all });
    }
  });
}
