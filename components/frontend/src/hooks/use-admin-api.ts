/**
 * React Query hooks for the admin user-overview dashboard.
 *
 * The SDK exposes no admin methods, so these talk to the backend admin routes
 * (`/api/v1/admin/*`) directly with `fetch`, sending the persisted bearer
 * token. A 401 clears the persisted tokens and rethrows so the auth context
 * can fall back to the unauthenticated state. The real authorization boundary
 * is the backend `require_admin` dependency — these hooks only render data the
 * server already decided the caller may see.
 */
import type { AdminUserPage, AdminUsersQuery, UserOverviewStats } from '@/lib/types';

import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { AuthenticationError, clearPersistedTokens, getAuthHeaders } from '@/lib/sdk-client';

const BASE = '/api/v1/admin';

/** Trend-window options for the signup trend chart. */
export type TrendDays = 7 | 30 | 90;

/** Query keys for the admin dashboard caches. */
export const adminKeys = {
  all: ['admin'] as const,
  overview: (trendDays: TrendDays) => [...adminKeys.all, 'overview', trendDays] as const,
  users: (query: AdminUsersQuery) => [...adminKeys.all, 'users', query] as const
};

/** Extract a human-readable message from a FastAPI `{detail}` error body. */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (typeof first.msg === 'string') return first.msg;
    }
  } catch {
    // non-JSON body — fall through
  }
  return fallback;
}

/**
 * Issue an authenticated GET against the admin API and parse the JSON body.
 *
 * On 401 we clear the persisted tokens and throw {@link AuthenticationError}
 * so the session is treated as expired; all other non-2xx statuses throw a
 * plain `Error` carrying the backend `detail`. The 403 (authenticated
 * non-admin) case surfaces here too, but the route guard normally prevents a
 * non-admin from ever reaching a screen that calls these hooks.
 */
async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: 'GET',
    headers: { ...getAuthHeaders() }
  });

  throwIfExpired(response);
  if (!response.ok) {
    throw new Error(await errorMessage(response, `Request failed (${response.status})`));
  }

  return (await response.json()) as T;
}

/** Clear the persisted session and throw if the response is a 401. */
function throwIfExpired(response: Response): void {
  if (response.status === 401) {
    clearPersistedTokens();
    throw new AuthenticationError('Your session has expired — please sign in again.');
  }
}

/** Apply the shared filter/sort params (everything except pagination). */
function applyFilterParams(params: URLSearchParams, query: AdminUsersQuery): void {
  if (query.sort_by !== undefined) params.set('sort_by', query.sort_by);
  if (query.sort_dir !== undefined) params.set('sort_dir', query.sort_dir);
  if (query.search?.trim()) params.set('search', query.search.trim());
  if (query.role !== undefined) params.set('role', query.role);
  if (query.is_active !== undefined) params.set('is_active', String(query.is_active));
  if (query.is_email_verified !== undefined) {
    params.set('is_email_verified', String(query.is_email_verified));
  }
}

/** Render a `URLSearchParams` as a `?…` suffix (empty string when no params). */
function toQuerySuffix(params: URLSearchParams): string {
  const suffix = params.toString();
  return suffix ? `?${suffix}` : '';
}

/** Serialize {@link AdminUsersQuery} into a `URLSearchParams` query string. */
function buildUsersQuery(query: AdminUsersQuery): string {
  const params = new URLSearchParams();
  if (query.page !== undefined) params.set('page', String(query.page));
  if (query.page_size !== undefined) params.set('page_size', String(query.page_size));
  applyFilterParams(params, query);
  return toQuerySuffix(params);
}

/** Pull the suggested filename out of a `Content-Disposition` header. */
function filenameFromDisposition(value: string | null): string | undefined {
  if (!value) return undefined;
  const match = /filename="?([^"]+)"?/.exec(value);
  return match?.[1];
}

/**
 * Download the filtered user base as a CSV file. Sends the same filters as the
 * table (minus pagination — the export returns every matching row), then
 * triggers a browser download from the returned blob. Throws on 401 (expired
 * session) and other non-2xx so the caller can surface the error.
 */
export async function downloadUsersCsv(query: AdminUsersQuery): Promise<void> {
  const params = new URLSearchParams();
  applyFilterParams(params, query);
  const queryString = toQuerySuffix(params);

  const response = await fetch(`${BASE}/users/export${queryString}`, {
    method: 'GET',
    headers: { ...getAuthHeaders() }
  });

  throwIfExpired(response);
  if (!response.ok) {
    throw new Error(await errorMessage(response, `Export failed (${response.status})`));
  }

  const blob = await response.blob();
  const filename =
    filenameFromDisposition(response.headers.get('content-disposition')) ?? 'syfthub-users.csv';
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Fetch the user-overview metrics for the given trend window. */
export function useAdminOverview(trendDays: TrendDays) {
  return useQuery({
    queryKey: adminKeys.overview(trendDays),
    queryFn: () => getJson<UserOverviewStats>(`/overview?trend_days=${trendDays}`)
  });
}

/**
 * Fetch a page of admin users. `keepPreviousData` keeps the table populated
 * while a new page / sort / filter is in flight so it doesn't flash empty.
 */
export function useAdminUsers(query: AdminUsersQuery) {
  return useQuery({
    queryKey: adminKeys.users(query),
    queryFn: () => getJson<AdminUserPage>(`/users${buildUsersQuery(query)}`),
    placeholderData: keepPreviousData
  });
}
