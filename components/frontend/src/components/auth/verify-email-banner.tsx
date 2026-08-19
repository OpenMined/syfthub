import Mail from 'lucide-react/dist/esm/icons/mail';
import X from 'lucide-react/dist/esm/icons/x';

import { EmailVerificationControls } from '@/components/auth/email-verification-controls';
import { useAuth } from '@/context/auth-context';
import { useShouldPromptEmailVerification } from '@/hooks/use-auth-config';
import { useVerifyEmailBannerStore } from '@/stores/verify-email-banner-store';

/**
 * Prompt to prove the email address on the account.
 *
 * A nudge, not a barrier: an unverified address restricts nothing, so this is
 * dismissible and nothing waits on it. It returns next session while the address
 * is still unverified.
 *
 * Dismissing it is never a dead end — the profile page carries the same controls
 * permanently, so there is always a way back.
 *
 * Hidden entirely when the server cannot send email, since no code could arrive
 * and there would be nothing the reader could do about it.
 */
export function VerifyEmailBanner() {
  const { user } = useAuth();
  const shouldPrompt = useShouldPromptEmailVerification();
  const dismiss = useVerifyEmailBannerStore((state) => state.dismiss);

  if (!shouldPrompt || !user) {
    return null;
  }

  return (
    <div
      className='border-b border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950'
      data-testid='verify-email-banner'
      role='status'
    >
      <div className='mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-2.5 text-amber-900 dark:text-amber-100'>
        <Mail className='h-4 w-4 flex-shrink-0' aria-hidden='true' />
        <div className='flex flex-1 flex-wrap items-center gap-3'>
          <EmailVerificationControls email={user.email} compact>
            {/* String literals rather than bare JSX text: esbuild trims the
                whitespace around an element boundary, and prettier removes an
                explicit {' '} because it believes the literal space survives. The
                two disagree, and the space vanished from the build. */}
            <p className='font-inter text-sm'>
              {'Your email '}
              <strong>{user.email}</strong>
              {" isn't verified yet."}
            </p>
          </EmailVerificationControls>
        </div>

        <button
          type='button'
          onClick={dismiss}
          aria-label='Dismiss'
          className='text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100'
        >
          <X className='h-4 w-4' aria-hidden='true' />
        </button>
      </div>
    </div>
  );
}
