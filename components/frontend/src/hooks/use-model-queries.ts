import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/context/auth-context';
import { getChatModels, getGuestAccessibleModels } from '@/lib/endpoint-utils';
import { modelKeys } from '@/lib/query-keys';

export function useModelsQuery(limit = 20) {
  const { user } = useAuth();
  const isAuthenticated = !!user;

  return useQuery({
    queryKey: modelKeys.chat(limit, isAuthenticated),
    queryFn: () => (isAuthenticated ? getChatModels(limit) : getGuestAccessibleModels(limit))
  });
}
