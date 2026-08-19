import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useEmailVerification } from '@/hooks/use-email-verification';

interface EmailVerificationControlsProps {
  /** The address being proven — shown back in the confirmation notice. */
  readonly email: string;
  /** Tighter spacing and smaller text, for use inside a single-line banner. */
  readonly compact?: boolean;
  /** Rendered above the controls, e.g. the banner's own message. */
  readonly children?: React.ReactNode;
}

/**
 * Ask for a code, then enter it.
 *
 * Shared by the dismissible banner and the profile page, so dismissing the banner
 * never removes the only way to verify. Both read the same session state, so
 * confirming in one makes the other disappear.
 */
export function EmailVerificationControls({
  email,
  compact = false,
  children
}: EmailVerificationControlsProps) {
  const v = useEmailVerification();

  return (
    <>
      {children}
      {(v.error ?? v.notice) ? (
        <p
          className={`font-inter text-xs ${v.error ? 'text-red-600' : 'text-green-600'}`}
          role='status'
        >
          {v.error ?? v.notice}
        </p>
      ) : null}

      <div className={`flex items-center gap-2 ${compact ? '' : 'mt-1'}`}>
        {v.codeRequested ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void v.verify();
            }}
            className='flex items-center gap-2'
          >
            <Input
              value={v.code}
              onChange={(event) => {
                v.onCodeChange(event.target.value);
              }}
              placeholder='123456'
              disabled={v.busy}
              autoComplete='one-time-code'
              inputMode='numeric'
              maxLength={v.codeLength}
              aria-label='Email verification code'
              className='h-8 w-28'
            />
            <Button type='submit' size='sm' disabled={!v.canVerify}>
              {v.isVerifying ? (
                <Loader2 className='h-3.5 w-3.5 animate-spin' aria-hidden='true' />
              ) : (
                'Verify'
              )}
            </Button>
          </form>
        ) : null}

        <button
          type='button'
          onClick={() => void v.send(email)}
          disabled={!v.canSend}
          className='font-inter text-xs font-medium underline underline-offset-2 disabled:no-underline disabled:opacity-50'
        >
          {v.codeRequested ? v.sendLabel : 'Verify now'}
        </button>
      </div>
    </>
  );
}
