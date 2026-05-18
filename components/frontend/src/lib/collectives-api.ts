/**
 * Collectives API client.
 *
 * Thin `fetch` wrappers over the backend `/api/v1/collectives` routes. A
 * collective is a user-owned grouping of *endpoints* — its members are
 * endpoint routes, not people. See `components/backend/.../api/endpoints/collectives.py`.
 */

import { getStoredAccessToken, persistTokens, syftClient } from '@/lib/sdk-client';

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
  description: string;
  /** When true, join requests are approved immediately. */
  auto_approve: boolean;
  icon_url: string | null;
  tags: string[];
  /** Platform-granted trust signal. Not user-settable. */
  verified: boolean;
  /** Number of approved endpoint members. */
  member_count: number;
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
  endpoint_slug: string | null;
  endpoint_owner_username: string | null;
  endpoint_type: string | null;
}

/** Body for `POST /collectives` (`CollectiveCreate`). */
export interface CollectiveCreateInput {
  name: string;
  description?: string;
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
  auto_approve?: boolean;
  icon_url?: string | null;
  tags?: string[];
}

/** A collective owner's decision on a pending join request. */
export type ReviewDecision = 'approve' | 'reject';

/** An endpoint owner's response to a collective invitation. */
export type InvitationDecision = 'accept' | 'decline';

// =============================================================================
// Request helper
// =============================================================================

const BASE = '/api/v1/collectives';

function authHeaders(): Record<string, string> {
  // Prefer the SDK client's in-memory token — it is the one kept current by
  // the SDK's automatic refresh; fall back to the persisted token.
  const token = syftClient.getTokens()?.accessToken ?? getStoredAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

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
  if (auth) Object.assign(headers, authHeaders());
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
  ownerId?: number;
}

/** List collectives, newest first. Optionally filter by owning user. */
export async function listCollectives(params: ListCollectivesParams = {}): Promise<Collective[]> {
  const query = new URLSearchParams();
  if (params.skip !== undefined) query.set('skip', String(params.skip));
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.ownerId !== undefined) query.set('owner_id', String(params.ownerId));
  const suffix = query.toString();
  return request<Collective[]>(suffix ? `?${suffix}` : '');
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
