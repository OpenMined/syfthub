import type { EndpointType } from '@/lib/types';

import { keepPreviousData, useQuery } from '@tanstack/react-query';

import {
  getGroupedPublicEndpoints,
  getPublicEndpointByPath,
  getPublicEndpoints,
  getPublicEndpointsPaginated,
  getTotalEndpointsCount,
  getTrendingEndpoints
} from '@/lib/endpoint-utils';
import { endpointKeys } from '@/lib/query-keys';

export function usePublicEndpoints(limit = 10) {
  return useQuery({
    queryKey: endpointKeys.public(limit),
    queryFn: () => getPublicEndpoints({ limit })
  });
}

/**
 * Hook for fetching paginated public endpoints with server-side type filtering and search.
 *
 * @param page - Current page number (1-indexed)
 * @param pageSize - Number of items per page
 * @param endpointType - Optional filter for endpoint type (model or data_source)
 * @param search - Optional search query to filter by name, description, or tags
 * @returns Query result with items, hasNextPage, and loading/error states
 */
export function usePaginatedPublicEndpoints(
  page: number,
  pageSize = 12,
  endpointType?: EndpointType,
  search?: string
) {
  return useQuery({
    queryKey: endpointKeys.publicPaginated(page, pageSize, endpointType, search),
    queryFn: () =>
      getPublicEndpointsPaginated({ page, limit: pageSize, endpoint_type: endpointType, search }),
    placeholderData: keepPreviousData // Keep previous data while fetching new page
  });
}

export function useRecentEndpoints(limit = 4) {
  return usePublicEndpoints(limit);
}

/**
 * Hook for fetching public endpoints grouped by owner.
 *
 * This is designed for the Global Directory display, where showing endpoints
 * grouped by owner provides a better representation of the network's diversity.
 * It prevents a single owner with many endpoints from dominating the listing.
 *
 * @param maxPerOwner - Maximum endpoints to return per owner (default 15)
 * @returns Query result with groups ordered by total endpoint count (descending)
 */
export function useGroupedPublicEndpoints(maxPerOwner = 15) {
  return useQuery({
    queryKey: endpointKeys.publicGrouped(maxPerOwner),
    queryFn: () => getGroupedPublicEndpoints(maxPerOwner)
  });
}

export function useTrendingEndpoints(limit = 4) {
  return useQuery({
    queryKey: endpointKeys.trending(limit),
    queryFn: () => getTrendingEndpoints({ limit })
  });
}

export function usePublicEndpointCount() {
  return useQuery({
    queryKey: endpointKeys.count(),
    queryFn: () => getTotalEndpointsCount()
  });
}

export function useEndpointByPath(path: string | undefined) {
  return useQuery({
    queryKey: endpointKeys.byPath(path ?? ''),
    queryFn: () => (path ? getPublicEndpointByPath(path) : null),
    enabled: !!path
  });
}
