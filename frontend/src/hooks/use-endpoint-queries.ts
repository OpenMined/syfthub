import type { EndpointType } from '@/lib/types';

import { keepPreviousData, useQuery } from '@tanstack/react-query';

import {
  getPublicEndpoints,
  getPublicEndpointsPaginated,
  getTotalEndpointsCount,
  getTrendingEndpoints,
  mapEndpointPublicToSource
} from '@/lib/endpoint-utils';
import { endpointKeys } from '@/lib/query-keys';
import { syftClient } from '@/lib/sdk-client';

export function usePublicEndpoints(limit = 10) {
  return useQuery({
    queryKey: endpointKeys.public(limit),
    queryFn: () => getPublicEndpoints({ limit })
  });
}

/**
 * Hook for fetching paginated public endpoints with server-side type filtering.
 *
 * @param page - Current page number (1-indexed)
 * @param pageSize - Number of items per page
 * @param endpointType - Optional filter for endpoint type (model or data_source)
 * @returns Query result with items, hasNextPage, and loading/error states
 */
export function usePaginatedPublicEndpoints(
  page: number,
  pageSize = 12,
  endpointType?: EndpointType
) {
  return useQuery({
    queryKey: endpointKeys.publicPaginated(page, pageSize, endpointType),
    queryFn: () =>
      getPublicEndpointsPaginated({ page, limit: pageSize, endpoint_type: endpointType }),
    placeholderData: keepPreviousData // Keep previous data while fetching new page
  });
}

export function useRecentEndpoints(limit = 4) {
  return usePublicEndpoints(limit);
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
    queryFn: async () => {
      if (!path) return null;
      const endpoints = await syftClient.hub.browse({ pageSize: 100 }).firstPage();
      const match = endpoints.find((ep) => `${ep.ownerUsername}/${ep.slug}` === path);
      return match ? mapEndpointPublicToSource(match) : null;
    },
    enabled: !!path
  });
}
