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
  getInvitation,
  inviteEndpoint,
  inviteEndpointByPath,
  listCollectives,
  listCollectivesForEndpoint,
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

/**
 * Fetch a single invitation (membership row) by collective + endpoint id.
 * Readable by the endpoint owner, the collective owner, or an admin — backs
 * the invitation-response landing page reached from the invitation email.
 */
export function useInvitation(collectiveId: number | undefined, endpointId: number | undefined) {
  return useQuery({
    queryKey: collectiveKeys.invitation(collectiveId ?? 0, endpointId ?? 0),
    queryFn: () => (collectiveId && endpointId ? getInvitation(collectiveId, endpointId) : null),
    enabled: Boolean(collectiveId && endpointId)
  });
}

/**
 * List approved collectives an `owner/slug` endpoint participates in. Backs the
 * Collectives card on the endpoint detail page; gated until both parts of the
 * path are known.
 */
export function useCollectivesForEndpoint(
  owner: string | undefined | null,
  slug: string | undefined | null
) {
  return useQuery({
    queryKey: collectiveKeys.byEndpoint(owner ?? '', slug ?? ''),
    queryFn: () => (owner && slug ? listCollectivesForEndpoint(owner, slug) : []),
    enabled: Boolean(owner && slug)
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
      void queryClient.invalidateQueries({
        queryKey: collectiveKeys.membersByCollective(collectiveId)
      }),
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

/**
 * Run `fn` against every item in parallel and partition the outcomes. The
 * backend exposes only single-item routes, so batch operations fan out here and
 * report a partial result. Shared by {@link useRequestJoinMany} and
 * {@link useInviteEndpointsByPath}.
 */
async function settleAll<T>(
  items: T[],
  fn: (item: T) => Promise<unknown>
): Promise<{ succeeded: T[]; failed: { item: T; error: Error }[] }> {
  const settled = await Promise.allSettled(items.map((item) => fn(item)));
  const succeeded: T[] = [];
  const failed: { item: T; error: Error }[] = [];
  for (const [index, outcome] of settled.entries()) {
    const item = items[index];
    if (item === undefined) continue;
    if (outcome.status === 'fulfilled') {
      succeeded.push(item);
    } else {
      failed.push({
        item,
        error: outcome.reason instanceof Error ? outcome.reason : new Error(String(outcome.reason))
      });
    }
  }
  return { succeeded, failed };
}

/** Outcome of a {@link useRequestJoinMany} call. */
export interface RequestJoinManyResult {
  /** Endpoints whose join request succeeded. */
  succeeded: number[];
  /** Per-endpoint failures, surfaced so the UI can report a partial result. */
  failed: { endpointId: number; error: Error }[];
}

/**
 * Submit join requests for multiple endpoints in parallel.
 *
 * The backend exposes only the single-endpoint route, so we fan out and gather
 * results with `Promise.allSettled` — every endpoint succeeds or fails on its
 * own and the caller renders a partial-success summary if any fail.
 */
export function useRequestJoinMany() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation<RequestJoinManyResult, Error, { collectiveId: number; endpointIds: number[] }>(
    {
      mutationFn: async ({ collectiveId, endpointIds }) => {
        const { succeeded, failed } = await settleAll(endpointIds, (endpointId) =>
          requestJoin(collectiveId, endpointId)
        );
        return {
          succeeded,
          failed: failed.map(({ item, error }) => ({ endpointId: item, error }))
        };
      },
      onSuccess: (_data, { collectiveId }) => {
        invalidateMembers(collectiveId);
      }
    }
  );
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

/**
 * Invite an endpoint into a collective by its `owner/slug` path. Backs the
 * admin invite-endpoint modal.
 */
export function useInviteEndpointByPath() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation({
    mutationFn: ({
      collectiveId,
      ownerUsername,
      slug
    }: {
      collectiveId: number;
      ownerUsername: string;
      slug: string;
    }) => inviteEndpointByPath(collectiveId, ownerUsername, slug),
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Outcome of a {@link useInviteEndpointsByPath} batch invite. */
export interface InviteEndpointsByPathResult {
  /** Endpoints that were successfully invited. */
  succeeded: { owner: string; slug: string }[];
  /** Per-endpoint failures (e.g. already a member), surfaced for a partial summary. */
  failed: { owner: string; slug: string; error: Error }[];
}

/**
 * Invite many endpoints into a collective by `owner/slug` path in parallel.
 *
 * The backend exposes only the single-endpoint invite route, so we fan out and
 * gather with `Promise.allSettled` — each endpoint succeeds or fails on its own
 * and the caller renders a partial-success summary. Backs the multi-select
 * invite modal, including the "invite every endpoint of an owner" (`owner/*`)
 * action.
 */
export function useInviteEndpointsByPath() {
  const invalidateMembers = useInvalidateMembers();
  return useMutation<
    InviteEndpointsByPathResult,
    Error,
    { collectiveId: number; targets: { owner: string; slug: string }[] }
  >({
    mutationFn: async ({ collectiveId, targets }) => {
      const { succeeded, failed } = await settleAll(targets, (target) =>
        inviteEndpointByPath(collectiveId, target.owner, target.slug)
      );
      return {
        succeeded,
        failed: failed.map(({ item, error }) => ({ ...item, error }))
      };
    },
    onSuccess: (_data, { collectiveId }) => {
      invalidateMembers(collectiveId);
    }
  });
}

/** Accept or decline a collective invitation (endpoint owner). */
export function useRespondToInvitation() {
  const queryClient = useQueryClient();
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
    onSuccess: (_data, { collectiveId, endpointId }) => {
      invalidateMembers(collectiveId);
      void queryClient.invalidateQueries({
        queryKey: collectiveKeys.invitation(collectiveId, endpointId)
      });
    }
  });
}
