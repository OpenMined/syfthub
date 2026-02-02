import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/context/auth-context';
import { getChatDataSources, getGuestAccessibleDataSources } from '@/lib/endpoint-utils';
import { dataSourceKeys } from '@/lib/query-keys';

export function useDataSourcesQuery(limit = 100) {
  const { user } = useAuth();
  const isAuthenticated = !!user;

  return useQuery({
    queryKey: dataSourceKeys.chat(limit, isAuthenticated),
    queryFn: () =>
      isAuthenticated ? getChatDataSources(limit) : getGuestAccessibleDataSources(limit)
  });
}
