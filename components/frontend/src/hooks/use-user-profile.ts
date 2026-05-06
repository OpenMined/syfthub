import { useQuery } from '@tanstack/react-query';

import { userKeys } from '@/lib/query-keys';
import { getPublicUserProfileAPI } from '@/lib/sdk-client';

/**
 * Hook for fetching a user's sanitized public profile by username.
 *
 * Returns ``null`` (rather than throwing) for 404s so callers can fall back
 * to identity inferred from the user's endpoints.
 */
export function useUserProfile(username: string | undefined) {
  return useQuery({
    queryKey: userKeys.publicProfile(username ?? ''),
    queryFn: () => (username ? getPublicUserProfileAPI(username) : null),
    enabled: !!username
  });
}
