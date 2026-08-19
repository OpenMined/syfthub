import { useQuery } from '@tanstack/react-query';

import { authKeys } from '@/lib/query-keys';
import { getAuthConfigAPI } from '@/lib/sdk-client';

/**
 * The server's public auth configuration.
 *
 * Deployment-level and fixed for the life of the process, so it is fetched once
 * and never refetched.
 */
export function useAuthConfig() {
  return useQuery({
    queryKey: authKeys.config(),
    queryFn: getAuthConfigAPI,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    retry: false
  });
}

/**
 * Whether an address can be proven at all in this deployment.
 *
 * False when the server has no mail transport: no code could ever arrive, so a
 * prompt to verify would be a dead end and nothing is ever marked verified.
 * Defaults to false until the config resolves, so the prompt cannot flash.
 */
export function useEmailVerificationAvailable(): boolean {
  const { data } = useAuthConfig();
  return data?.smtpConfigured ?? false;
}
