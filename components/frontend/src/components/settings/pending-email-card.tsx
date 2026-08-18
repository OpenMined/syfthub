import { useState } from 'react';

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Mail from 'lucide-react/dist/esm/icons/mail';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useResendCooldown } from '@/hooks/use-resend-cooldown';
import {
  cancelEmailChangeAPI,
  resendEmailChangeCodeAPI,
  verifyEmailChangeAPI
} from '@/lib/sdk-client';

import { StatusMessage } from './status-message';

interface PendingEmailCardProps {
  /** The address awaiting verification, from `user.pending_email`. */
  readonly pendingEmail: string;
  /** The address still on the account, which stays active until confirmation. */
  readonly currentEmail: string;
  /** Called with the updated user once the change is confirmed or cancelled. */
  readonly onResolved: (updated: Awaited<ReturnType<typeof verifyEmailChangeAPI>> | null) => void;
}

const CODE_LENGTH = 6;

/**
 * Inline card for an email change awaiting verification.
 *
 * Rendered whenever the server reports a `pending_email`, which means it
 * survives a reload, a new session, and a different device — the pending state
 * lives in the database, not here. That is why this is an inline card rather
 * than a modal: a dismissed modal would leave a real pending change with no
 * route back to the code entry.
 *
 * Deliberately non-blocking. Unlike registration OTP, the account's current
 * address still works and still logs the user in while a change is pending, so
 * nothing here demands immediate attention.
 */
export function PendingEmailCard({
  pendingEmail,
  currentEmail,
  onResolved
}: PendingEmailCardProps) {
  const [code, setCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const cooldown = useResendCooldown();

  const busy = isVerifying || isResending || isCancelling;

  const handleCodeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    // Codes are always 6 digits; drop anything else rather than letting the
    // server reject it.
    setCode(event.target.value.replaceAll(/\D/g, '').slice(0, CODE_LENGTH));
    if (error) setError(null);
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (code.length !== CODE_LENGTH || busy) return;

    setIsVerifying(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await verifyEmailChangeAPI(code);
      onResolved(updated);
    } catch (error_) {
      // A rejected code leaves the pending change intact server-side, so the
      // card stays put and the user can retry.
      setError(error_ instanceof Error ? error_.message : 'Could not confirm that code');
      setCode('');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleResend = async () => {
    if (cooldown.isCoolingDown || busy) return;

    setIsResending(true);
    setError(null);
    try {
      await resendEmailChangeCodeAPI();
      cooldown.start();
      setNotice(`A new code is on its way to ${pendingEmail}.`);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not send a new code');
    } finally {
      setIsResending(false);
    }
  };

  const handleCancel = async () => {
    if (busy) return;

    setIsCancelling(true);
    setError(null);
    try {
      await cancelEmailChangeAPI();
      onResolved(null);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not cancel the change');
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div
      className='space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950'
      data-testid='pending-email-card'
    >
      <div className='flex items-start gap-2'>
        <Mail
          className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400'
          aria-hidden='true'
        />
        <div className='space-y-1'>
          <p className='font-inter text-sm font-medium text-amber-900 dark:text-amber-100'>
            Confirm your new email address
          </p>
          <p className='font-inter text-xs text-amber-800 dark:text-amber-200'>
            We sent a {CODE_LENGTH}-digit code to <strong>{pendingEmail}</strong>. Until you confirm
            it, <strong>{currentEmail}</strong> stays your address and you can keep signing in with
            it.
          </p>
        </div>
      </div>

      <StatusMessage type='error' message={error} />
      <StatusMessage type='success' message={notice} />

      <form onSubmit={(event) => void handleVerify(event)} className='flex items-end gap-2'>
        <div className='w-40'>
          <Input
            label='Verification code'
            value={code}
            onChange={handleCodeChange}
            placeholder='123456'
            disabled={busy}
            autoComplete='one-time-code'
            inputMode='numeric'
            maxLength={CODE_LENGTH}
            aria-label='Verification code for your new email address'
          />
        </div>
        <Button type='submit' disabled={busy || code.length !== CODE_LENGTH}>
          {isVerifying ? (
            <>
              <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
              Confirming…
            </>
          ) : (
            'Confirm'
          )}
        </Button>
      </form>

      <div className='font-inter flex items-center gap-4 text-xs'>
        <button
          type='button'
          onClick={() => void handleResend()}
          disabled={cooldown.isCoolingDown || busy}
          className='font-medium text-amber-900 underline underline-offset-2 disabled:no-underline disabled:opacity-50 dark:text-amber-100'
        >
          {cooldown.isCoolingDown ? `Resend in ${String(cooldown.remaining)}s` : 'Resend code'}
        </button>
        <button
          type='button'
          onClick={() => void handleCancel()}
          disabled={busy}
          className='text-amber-800 underline underline-offset-2 disabled:no-underline disabled:opacity-50 dark:text-amber-200'
        >
          {isCancelling ? 'Cancelling…' : 'Cancel change'}
        </button>
      </div>
    </div>
  );
}
