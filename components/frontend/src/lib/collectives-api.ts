/**
 * Collectives API client.
 *
 * Thin `fetch` wrappers over the backend `/api/v1/collectives` routes. A
 * collective is a user-owned grouping of *endpoints* — its members are
 * endpoint routes, not people. See `components/backend/.../api/endpoints/collectives.py`.
 */

import { getAuthHeaders, persistTokens, syftClient } from '@/lib/sdk-client';

// =============================================================================
// Types — mirror the backend Pydantic schemas (schemas/collective.py)
// =============================================================================

/** Workflow status of an endpoint's membership in a collective. */
export type MembershipStatus = 'pending' | 'invited' | 'approved' | 'rejected';

/** A collective in API responses (`CollectiveResponse`). */
export interface Collective {
  id: number;
  owner_id: number;
  name: string;
  slug: string;
  /**
   * Unique shared-endpoint path, `collective/<slug>` — the single identifier
   * that addresses every member endpoint. Backend-derived, read-only.
   */
  shared_endpoint_path: string;
  /** Short summary, shown on cards and the detail header. */
  description: string;
  /** Long-form markdown "about" / README, shown on the detail page. */
  about: string;
  /** When true, join requests are approved immediately. */
  auto_approve: boolean;
  icon_url: string | null;
  tags: string[];
  /** Platform-granted trust signal. Not user-settable. */
  verified: boolean;
  /** Number of approved endpoint members. */
  member_count: number;
  /** Number of distinct users who own the approved member endpoints. */
  owner_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * A collective membership (`CollectiveMemberResponse`). The `endpoint_*` fields
 * are populated by the backend so a membership can be rendered without a
 * second round-trip; they are null only when the endpoint has been removed.
 */
export interface CollectiveMember {
  id: number;
  collective_id: number;
  endpoint_id: number;
  status: MembershipStatus;
  requested_at: string;
  responded_at: string | null;
  reviewed_by_user_id: number | null;
  endpoint_name: string | null;
  endpoint_description: string | null;
  endpoint_slug: string | null;
  endpoint_owner_username: string | null;
  endpoint_owner_full_name: string | null;
  endpoint_type: string | null;
}

/** Body for `POST /collectives` (`CollectiveCreate`). */
export interface CollectiveCreateInput {
  name: string;
  description?: string;
  about?: string;
  auto_approve?: boolean;
  icon_url?: string | null;
  tags?: string[];
  /** Optional — auto-generated from the name when omitted. */
  slug?: string;
}

/** Body for `PATCH /collectives/{id}` (`CollectiveUpdate`) — all fields optional. */
export interface CollectiveUpdateInput {
  name?: string;
  description?: string;
  about?: string;
  auto_approve?: boolean;
  icon_url?: string | null;
  tags?: string[];
}

/** A collective owner's decision on a pending join request. */
export type ReviewDecision = 'approve' | 'reject';

/** An endpoint owner's response to a collective invitation. */
export type InvitationDecision = 'accept' | 'decline';

/**
 * Endpoint types eligible for collective membership. A collective groups data
 * sources, so model-only and agent endpoints cannot join; `model_data_source`
 * qualifies because it also exposes a data source. Mirrors the backend guard
 * `CollectiveService._require_joinable_endpoint` — the backend is the source
 * of truth; this is only for filtering the UI.
 */
export const JOINABLE_ENDPOINT_TYPES = ['data_source', 'model_data_source'] as const;

/** Whether an endpoint of the given type may join a collective. */
export function isJoinableEndpointType(type: string | null | undefined): boolean {
  return type != null && (JOINABLE_ENDPOINT_TYPES as readonly string[]).includes(type);
}

/** Parse a comma-separated tag string into a trimmed, non-empty string array. */
export function parseTags(csv: string): string[] {
  return csv
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

// =============================================================================
// Request helper
// =============================================================================

const BASE = '/api/v1/collectives';

/** Extract a human-readable message from a FastAPI `{detail}` error body. */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    // 422 validation errors arrive as a list of {msg, loc}.
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (typeof first.msg === 'string') return first.msg;
    }
  } catch {
    // non-JSON body — fall through
  }
  return fallback;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Send the Authorization header even though the route is public. */
  auth?: boolean;
}

/** Issue a single fetch for the collectives API. */
function sendRequest(
  path: string,
  method: string,
  body: unknown,
  auth: boolean
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth) Object.assign(headers, getAuthHeaders());
  return fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

/**
 * Perform a collectives API request. Returns parsed JSON, or `null` for 204
 * responses. Throws `Error(detail)` on any non-2xx status.
 *
 * These routes use raw `fetch` rather than the SDK client, so a 401 from an
 * expired access token is handled here: refresh once and retry, mirroring the
 * SDK's own automatic 401 handling.
 */
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = false } = options;
  let response = await sendRequest(path, method, body, auth);

  if (response.status === 401 && auth) {
    try {
      await syftClient.auth.refresh();
      persistTokens();
    } catch {
      throw new Error('Your session has expired — please sign in again.');
    }
    response = await sendRequest(path, method, body, auth);
  }

  if (!response.ok) {
    throw new Error(await errorMessage(response, `Request failed (${response.status})`));
  }
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

// =============================================================================
// Collective CRUD
// =============================================================================

export interface ListCollectivesParams {
  skip?: number;
  limit?: number;
  ownerUsername?: string;
  /** Server-side search over name, description and tags. */
  search?: string;
}

/** List collectives, newest first. Optionally filter by owning username / search. */
export async function listCollectives(params: ListCollectivesParams = {}): Promise<Collective[]> {
  const query = new URLSearchParams();
  if (params.skip !== undefined) query.set('skip', String(params.skip));
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.ownerUsername) query.set('owner_username', params.ownerUsername);
  if (params.search?.trim()) query.set('search', params.search.trim());
  const suffix = query.toString();
  return request<Collective[]>(suffix ? `?${suffix}` : '');
}

/**
 * List distinct approved collectives where any endpoint owned by `username` is
 * a member. Public-readable. Returns an empty array when the user does not exist
 * or has no approved memberships.
 */
export async function listCollectivesForUserEndpoints(username: string): Promise<Collective[]> {
  const response = await fetch(`${BASE}/by-member-username/${encodeURIComponent(username)}`);
  if (response.status === 404) return [];
  if (!response.ok) {
    throw new Error(
      await errorMessage(response, `Failed to load collectives (${response.status})`)
    );
  }
  return (await response.json()) as Collective[];
}

/** A page of collectives plus whether another page follows. */
export interface PaginatedCollectivesResponse {
  items: Collective[];
  hasNextPage: boolean;
}

/**
 * Fetch one page of collectives with optional server-side search.
 *
 * Mirrors `getPublicEndpointsPaginated`: the backend has no total-count
 * endpoint, so we over-fetch by one row to detect whether a next page exists.
 */
export async function listCollectivesPaginated(
  params: { page?: number; limit?: number; search?: string } = {}
): Promise<PaginatedCollectivesResponse> {
  const { page = 1, limit = 12, search } = params;
  const skip = (page - 1) * limit;

  const data = await listCollectives({ skip, limit: limit + 1, search });
  const hasNextPage = data.length > limit;
  return { items: data.slice(0, limit), hasNextPage };
}

/**
 * List approved collectives that an `owner/slug` endpoint participates in.
 *
 * Public-readable. Returns an empty array when the endpoint exists but is not
 * an approved member of any collective, when the endpoint can't be resolved,
 * or on a 404 — callers render "no card" for both cases.
 */
export async function listCollectivesForEndpoint(
  owner: string,
  slug: string
): Promise<Collective[]> {
  const response = await fetch(
    `${BASE}/by-endpoint/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}`
  );
  if (response.status === 404) return [];
  if (!response.ok) {
    throw new Error(
      await errorMessage(response, `Failed to load collectives (${response.status})`)
    );
  }
  return (await response.json()) as Collective[];
}

/** Fetch a collective by slug. Returns `null` on 404 so callers can render a not-found state. */
export async function getCollectiveBySlug(slug: string): Promise<Collective | null> {
  const response = await fetch(`${BASE}/by-slug/${encodeURIComponent(slug)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await errorMessage(response, `Failed to load collective (${response.status})`));
  }
  return (await response.json()) as Collective;
}

/** Create a new collective owned by the current user. */
export function createCollective(input: CollectiveCreateInput): Promise<Collective> {
  return request<Collective>('', { method: 'POST', body: input, auth: true });
}

/** Update a collective. Owner only. */
export function updateCollective(id: number, input: CollectiveUpdateInput): Promise<Collective> {
  return request<Collective>(`/${id}`, { method: 'PATCH', body: input, auth: true });
}

/** Delete a collective and all its memberships. Owner only. */
export async function deleteCollective(id: number): Promise<void> {
  await request<null>(`/${id}`, { method: 'DELETE', auth: true });
}

// =============================================================================
// Membership
// =============================================================================

/**
 * List a collective's memberships. Non-owners see only approved members;
 * the owner sees every status. An auth token is always sent so the owner
 * gets the full view.
 */
export function listMembers(
  collectiveId: number,
  status?: MembershipStatus
): Promise<CollectiveMember[]> {
  const suffix = status ? `?status=${status}` : '';
  return request<CollectiveMember[]>(`/${collectiveId}/members${suffix}`, { auth: true });
}

/** Request that one of your endpoints join a collective. */
export function requestJoin(collectiveId: number, endpointId: number): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/members`, {
    method: 'POST',
    body: { endpoint_id: endpointId },
    auth: true
  });
}

/** Approve or reject a pending join request. Collective owner only. */
export function reviewRequest(
  collectiveId: number,
  endpointId: number,
  decision: ReviewDecision
): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/members/${endpointId}/review`, {
    method: 'POST',
    body: { decision },
    auth: true
  });
}

/** Remove an endpoint from a collective (collective owner or endpoint owner). */
export async function removeMember(collectiveId: number, endpointId: number): Promise<void> {
  await request<null>(`/${collectiveId}/members/${endpointId}`, {
    method: 'DELETE',
    auth: true
  });
}

/** Invite an endpoint into a collective. Collective owner only. */
export function inviteEndpoint(
  collectiveId: number,
  endpointId: number
): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/invitations`, {
    method: 'POST',
    body: { endpoint_id: endpointId },
    auth: true
  });
}

/**
 * Invite an endpoint into a collective by its `owner/slug` path. Collective
 * owner only. Used by the admin invite UI since the public endpoint API does
 * not expose numeric ids.
 */
export function inviteEndpointByPath(
  collectiveId: number,
  ownerUsername: string,
  slug: string
): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/invitations/by-path`, {
    method: 'POST',
    body: { owner_username: ownerUsername, slug },
    auth: true
  });
}

/**
 * Fetch the membership row for an invitation. Readable by the endpoint owner,
 * the collective owner, or an admin — backs the invitation-response landing
 * page reached from the invitation email.
 */
export function getInvitation(collectiveId: number, endpointId: number): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/invitations/${endpointId}`, {
    auth: true
  });
}

/** Accept or decline a collective invitation. Endpoint owner only. */
export function respondToInvitation(
  collectiveId: number,
  endpointId: number,
  decision: InvitationDecision
): Promise<CollectiveMember> {
  return request<CollectiveMember>(`/${collectiveId}/invitations/${endpointId}/respond`, {
    method: 'POST',
    body: { decision },
    auth: true
  });
}

// =============================================================================
// Shared endpoints — named, curated subsets of a collective's members
// =============================================================================

/**
 * One member endpoint inside a shared endpoint, enriched for UI rendering.
 *
 * `is_active` is `true` when the endpoint is currently an approved member of
 * the parent collective; `false` means the endpoint was configured into the
 * subset but has since left the collective and is silently skipped at
 * chat-time fan-out. Surface inactive members in the admin UI so owners can
 * either re-invite them or remove them from the selection.
 */
export interface CollectiveSharedEndpointMember {
  endpoint_id: number;
  endpoint_name: string | null;
  endpoint_slug: string | null;
  endpoint_owner_username: string | null;
  endpoint_type: string | null;
  is_active: boolean;
}

/**
 * A shared endpoint — named, curated subset of a collective's approved
 * member endpoints. Resolves at chat-time as `collective/<collective_slug>/<slug>`.
 */
export interface CollectiveSharedEndpoint {
  id: number;
  collective_id: number;
  collective_slug: string;
  name: string;
  slug: string;
  /** Derived: `collective/<collective_slug>/<slug>`. Read-only. */
  shared_endpoint_path: string;
  description: string;
  members: CollectiveSharedEndpointMember[];
  member_count: number;
  /**
   * Members that are currently approved in the parent collective and will
   * participate in chat fan-out — `<= member_count`.
   */
  active_member_count: number;
  created_at: string;
  updated_at: string;
}

/** Body for creating a shared endpoint. */
export interface CollectiveSharedEndpointCreateInput {
  name: string;
  description?: string;
  /** Optional — auto-derived from the name when omitted. */
  slug?: string;
  /**
   * Endpoints to include. Must all be currently approved members of the
   * parent collective; the backend rejects non-members with a 400.
   */
  endpoint_ids: number[];
}

/**
 * Body for updating a shared endpoint — all fields optional.
 *
 * `endpoint_ids` is a *full replacement* when present; omit it to leave the
 * member set untouched. Slug is immutable.
 */
export interface CollectiveSharedEndpointUpdateInput {
  name?: string;
  description?: string;
  endpoint_ids?: number[];
}

/** List a collective's shared endpoints by parent id. Public-readable. */
export function listSharedEndpoints(collectiveId: number): Promise<CollectiveSharedEndpoint[]> {
  return request<CollectiveSharedEndpoint[]>(`/${collectiveId}/shared-endpoints`);
}

/**
 * Bulk-list shared endpoints across multiple collectives in one request.
 *
 * Replaces the per-collective fan-out that the chat-view modal previously
 * issued (N collectives → N GETs). Returns an empty list when ``collectiveIds``
 * is empty so callers don't need to guard before invocation.
 */
export function listSharedEndpointsBulk(
  collectiveIds: readonly number[]
): Promise<CollectiveSharedEndpoint[]> {
  if (collectiveIds.length === 0) return Promise.resolve([]);
  const query = collectiveIds.map((id) => `collective_id=${id}`).join('&');
  return request<CollectiveSharedEndpoint[]>(`/shared-endpoints/bulk?${query}`);
}

/** List a collective's shared endpoints by parent slug. Public-readable.
 *
 * Returns an empty array on 404 so callers can render "no card" identically
 * whether the parent collective is missing or simply has no subsets.
 */
export async function listSharedEndpointsByCollectiveSlug(
  collectiveSlug: string
): Promise<CollectiveSharedEndpoint[]> {
  const response = await fetch(
    `${BASE}/by-slug/${encodeURIComponent(collectiveSlug)}/shared-endpoints`
  );
  if (response.status === 404) return [];
  if (!response.ok) {
    throw new Error(
      await errorMessage(response, `Failed to load Collective APIs (${response.status})`)
    );
  }
  return (await response.json()) as CollectiveSharedEndpoint[];
}

/** Get one shared endpoint by parent id + own slug. Public-readable. */
export function getSharedEndpoint(
  collectiveId: number,
  sharedSlug: string
): Promise<CollectiveSharedEndpoint> {
  return request<CollectiveSharedEndpoint>(
    `/${collectiveId}/shared-endpoints/${encodeURIComponent(sharedSlug)}`
  );
}

/** Create a shared endpoint under a collective. Collective owner only. */
export function createSharedEndpoint(
  collectiveId: number,
  input: CollectiveSharedEndpointCreateInput
): Promise<CollectiveSharedEndpoint> {
  return request<CollectiveSharedEndpoint>(`/${collectiveId}/shared-endpoints`, {
    method: 'POST',
    body: input,
    auth: true
  });
}

/** Update a shared endpoint. Collective owner only. */
export function updateSharedEndpoint(
  collectiveId: number,
  sharedSlug: string,
  input: CollectiveSharedEndpointUpdateInput
): Promise<CollectiveSharedEndpoint> {
  return request<CollectiveSharedEndpoint>(
    `/${collectiveId}/shared-endpoints/${encodeURIComponent(sharedSlug)}`,
    { method: 'PATCH', body: input, auth: true }
  );
}

/** Delete a shared endpoint and its member rows. Collective owner only. */
export async function deleteSharedEndpoint(
  collectiveId: number,
  sharedSlug: string
): Promise<void> {
  await request<null>(`/${collectiveId}/shared-endpoints/${encodeURIComponent(sharedSlug)}`, {
    method: 'DELETE',
    auth: true
  });
}

// =============================================================================
// Billing summary — aggregate pricing + per-member settlement metadata
// =============================================================================

/** How a single member endpoint bills (`MemberBillingDetail`). */
export type MemberBillingKind = 'prepaid' | 'mpp' | 'free';

/** A purchasable prepaid credit bundle advertised by a publisher policy. */
export interface BillingMoneyBundle {
  name: string;
  amount: number;
}

/**
 * Normalized billing detail for one member endpoint.
 *
 * - `prepaid` — Xendit/Stripe prepaid credits; the buyer needs a funded wallet
 *   with the publisher (`credits_url`) and tops it up via `payment_url`.
 * - `mpp` — metered against the buyer's single Hub wallet at request time.
 * - `free` — no enabled billing policy; no settlement needed.
 */
export interface MemberBillingDetail {
  kind: MemberBillingKind;
  provider: string | null;
  currency: string | null;
  price_per_unit: number | null;
  unit: string;
  payment_url: string | null;
  credits_url: string | null;
  invoices_url: string | null;
  bundles: BillingMoneyBundle[];
}

/** A member endpoint's identity plus its normalized billing detail. */
export interface CollectiveMemberBilling {
  endpoint_id: number;
  endpoint_name: string | null;
  endpoint_slug: string | null;
  endpoint_owner_username: string | null;
  endpoint_owner_full_name: string | null;
  endpoint_type: string | null;
  billing: MemberBillingDetail;
}

/** One currency's slice of an aggregated price — never converted to another. */
export interface PriceByCurrency {
  currency: string;
  amount: number;
}

/**
 * Aggregate pricing + settlement metadata for a shared endpoint
 * (`CollectiveBillingSummaryResponse`).
 *
 * `estimated_price` sums only prepaid per-request prices, grouped by currency;
 * metered MPP and free members do not contribute.
 */
export interface CollectiveBillingSummary {
  members: CollectiveMemberBilling[];
  estimated_price: PriceByCurrency[];
  free_count: number;
  prepaid_count: number;
  mpp_count: number;
}

/**
 * Fetch the billing summary for a shared endpoint. **Requires authentication**
 * — the response exposes per-member publisher payment/credits URLs, so the
 * backend route is auth-gated.
 *
 * Pass `sharedSlug` to scope to a curated subset; omit it (or pass `'all'`)
 * for the default `collective/<slug>` shared endpoint covering all approved
 * members.
 *
 * Returns `null` on 404 (no such collective/subset) and on 401 (the caller is
 * not signed in), so callers — the public detail-page price badge included —
 * can simply render nothing rather than surfacing an error to logged-out
 * visitors. Other non-2xx statuses still throw.
 */
export async function getCollectiveBillingSummary(
  collectiveSlug: string,
  sharedSlug?: string
): Promise<CollectiveBillingSummary | null> {
  const base = `/by-slug/${encodeURIComponent(collectiveSlug)}`;
  const path =
    sharedSlug && sharedSlug !== 'all'
      ? `${base}/shared-endpoints/${encodeURIComponent(sharedSlug)}/billing-summary`
      : `${base}/billing-summary`;

  // Refresh once on a stale access token (mirrors `request`), but treat a
  // still-unauthenticated response as "no pricing" instead of an error.
  let response = await sendRequest(path, 'GET', undefined, true);
  if (response.status === 401) {
    try {
      await syftClient.auth.refresh();
      persistTokens();
      response = await sendRequest(path, 'GET', undefined, true);
    } catch {
      return null;
    }
  }
  if (response.status === 401 || response.status === 404) return null;
  if (!response.ok) {
    throw new Error(
      await errorMessage(response, `Failed to load billing summary (${response.status})`)
    );
  }
  return (await response.json()) as CollectiveBillingSummary;
}
