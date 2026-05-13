import type { EndpointUptimeResponse } from '@/lib/uptime';

import { useQuery } from '@tanstack/react-query';

import { endpointKeys } from '@/lib/query-keys';
import { getStoredAccessToken } from '@/lib/sdk-client';

function buildAuthHeaders(): Record<string, string> {
  // Public uptime is readable without auth, but a token lets the backend
  // surface PRIVATE/INTERNAL endpoints to their owners.
  const token = getStoredAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchEndpointUptime(
  owner: string,
  slug: string,
  windowHours: number
): Promise<EndpointUptimeResponse> {
  const response = await fetch(
    `/api/v1/endpoints/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}/uptime?window_hours=${windowHours}`,
    { headers: buildAuthHeaders() }
  );
  if (!response.ok) {
    throw new Error(`Uptime fetch failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as EndpointUptimeResponse;
}

interface UseEndpointUptimeOptions {
  /**
   * If false, the query stays disabled. Used to lazy-mount the uptime tab —
   * pass `enabled` only when the user has activated the tab at least once.
   */
  enabled?: boolean;
  /** Window in hours. Defaults to 720 (30 days). */
  windowHours?: number;
}

/**
 * Fetch a per-endpoint uptime time series. The endpoint is public, so this
 * works whether or not the user is signed in.
 */
export function useEndpointUptime(
  owner: string | undefined,
  slug: string | undefined,
  { enabled = true, windowHours = 720 }: UseEndpointUptimeOptions = {}
) {
  const ownerKey = owner ?? '';
  const slugKey = slug ?? '';
  return useQuery({
    queryKey: endpointKeys.uptime(ownerKey, slugKey, windowHours),
    queryFn: () => fetchEndpointUptime(ownerKey, slugKey, windowHours),
    enabled: enabled && Boolean(owner && slug),
    // Buckets update at most every 30s server-side; a 60s stale window keeps
    // the cache hot during tab toggling without spamming the API.
    staleTime: 60 * 1000
  });
}
