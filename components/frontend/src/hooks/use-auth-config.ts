import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/context/auth-context';
import { authKeys } from '@/lib/query-keys';
import { getAuthConfigAPI } from '@/lib/sdk-client';
import { useVerifyEmailBannerStore } from '@/stores/verify-email-banner-store';

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

/**
 * Whether the "verify your email" prompt should be on screen.
 *
 * Shared by the banner and by the layout, which needs it to shift its floating
 * header down so the two do not overlap. Keeping the decision in one place stops
 * the two disagreeing.
 */
export function useShouldPromptEmailVerification(): boolean {
  const { user } = useAuth();
  const dismissed = useVerifyEmailBannerStore((state) => state.dismissed);
  const canVerify = useEmailVerificationAvailable();

  return Boolean(user) && !user?.is_email_verified && !dismissed && canVerify;
}
