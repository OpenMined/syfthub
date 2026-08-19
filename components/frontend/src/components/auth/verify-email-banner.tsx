import { useState } from 'react';

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Mail from 'lucide-react/dist/esm/icons/mail';
import X from 'lucide-react/dist/esm/icons/x';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/auth-context';
import { useEmailVerificationAvailable } from '@/hooks/use-auth-config';
import { useResendCooldown } from '@/hooks/use-resend-cooldown';
import { resendEmailVerificationAPI, verifyEmailAPI } from '@/lib/sdk-client';

const CODE_LENGTH = 6;
const DISMISS_KEY = 'syft_verify_email_dismissed';

/**
 * Prompt to prove the email address on the account.
 *
 * A nudge, not a barrier: an unverified address does not restrict anything, so
 * this is dismissible and nothing waits on it. It reappears next session while
 * the address is still unverified, which is the point — persistent enough to be
 * acted on, never in the way.
 *
 * Hidden entirely when the server cannot send email, since no code could arrive
 * and there would be nothing the reader could do about it.
 */
export function VerifyEmailBanner() {
  const { user, updateUser } = useAuth();
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem(DISMISS_KEY) === '1');
  const [expanded, setExpanded] = useState(false);
  const [code, setCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const cooldown = useResendCooldown();
  const canVerify = useEmailVerificationAvailable();

  if (!user || user.is_email_verified || dismissed || !canVerify) {
    return null;
  }

  const busy = isVerifying || isResending;

  let sendLabel = 'Send me a code';
  if (cooldown.isCoolingDown) {
    sendLabel = `Resend in ${String(cooldown.remaining)}s`;
  } else if (expanded) {
    sendLabel = 'Resend code';
  }

  const handleDismiss = () => {
    // Session-scoped on purpose: dismissing means "not now", not "never".
    sessionStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  };

  const handleCodeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setCode(event.target.value.replaceAll(/\D/g, '').slice(0, CODE_LENGTH));
    if (error) setError(null);
  };

  const handleSend = async () => {
    if (cooldown.isCoolingDown || busy) return;
    setIsResending(true);
    setError(null);
    try {
      await resendEmailVerificationAPI();
      cooldown.start();
      setExpanded(true);
      setNotice(`Code sent to ${user.email}.`);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not send a code');
    } finally {
      setIsResending(false);
    }
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (code.length !== CODE_LENGTH || busy) return;
    setIsVerifying(true);
    setError(null);
    setNotice(null);
    try {
      updateUser(await verifyEmailAPI(code));
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not confirm that code');
      setCode('');
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div
      className='border-b border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950'
      data-testid='verify-email-banner'
      role='status'
    >
      <div className='mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-2.5'>
        <Mail
          className='h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400'
          aria-hidden='true'
        />
        <p className='font-inter flex-1 text-sm text-amber-900 dark:text-amber-100'>
          {error ?? notice ?? (
            <>
              Your email <strong>{user.email}</strong> isn&apos;t verified yet.
            </>
          )}
        </p>

        {expanded ? (
          <form onSubmit={(event) => void handleVerify(event)} className='flex gap-2'>
            <Input
              value={code}
              onChange={handleCodeChange}
              placeholder='123456'
              disabled={busy}
              autoComplete='one-time-code'
              inputMode='numeric'
              maxLength={CODE_LENGTH}
              aria-label='Email verification code'
              className='h-8 w-28'
            />
            <Button type='submit' size='sm' disabled={busy || code.length !== CODE_LENGTH}>
              {isVerifying ? (
                <Loader2 className='h-3.5 w-3.5 animate-spin' aria-hidden='true' />
              ) : (
                'Verify'
              )}
            </Button>
          </form>
        ) : null}

        <button
          type='button'
          onClick={() => void handleSend()}
          disabled={cooldown.isCoolingDown || busy}
          className='font-inter text-xs font-medium text-amber-900 underline underline-offset-2 disabled:no-underline disabled:opacity-50 dark:text-amber-100'
        >
          {sendLabel}
        </button>

        <button
          type='button'
          onClick={handleDismiss}
          aria-label='Dismiss'
          className='text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100'
        >
          <X className='h-4 w-4' aria-hidden='true' />
        </button>
      </div>
    </div>
  );
}
