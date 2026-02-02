import { useQuery } from '@tanstack/react-query';

import {
  getPublicEndpoints,
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
