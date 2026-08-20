import { useState } from 'react';

import { useAuth } from '@/context/auth-context';
import { useResendCooldown } from '@/hooks/use-resend-cooldown';
import { resendEmailVerificationAPI, verifyEmailAPI } from '@/lib/sdk-client';

const CODE_LENGTH = 6;

/**
 * Sending and confirming proof of the address on the account.
 *
 * Held here rather than in a component because two surfaces need it: the
 * page-level banner, and the always-present control on the profile page. The
 * banner is dismissible, so it cannot be the only way in — dismissing it means
 * "not now", and something must still be there afterwards.
 */
export function useEmailVerification() {
  const { updateUser } = useAuth();
  const [code, setCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [codeRequested, setCodeRequested] = useState(false);
  const cooldown = useResendCooldown();

  const busy = isVerifying || isSending;

  /** Keep only digits, capped at the code length. */
  const onCodeChange = (value: string) => {
    setCode(value.replaceAll(/\D/g, '').slice(0, CODE_LENGTH));
    if (error) setError(null);
  };

  const send = async (address: string) => {
    if (cooldown.isCoolingDown || busy) return;
    setIsSending(true);
    setError(null);
    try {
      await resendEmailVerificationAPI();
      cooldown.start();
      setCodeRequested(true);
      setNotice(`Code sent to ${address}.`);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not send a code');
    } finally {
      setIsSending(false);
    }
  };

  const verify = async () => {
    if (code.length !== CODE_LENGTH || busy) return;
    setIsVerifying(true);
    setError(null);
    setNotice(null);
    try {
      // Folding the result into the session is what makes both surfaces
      // disappear at once: they render off the user's verified state.
      updateUser(await verifyEmailAPI(code));
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Could not confirm that code');
      setCode('');
    } finally {
      setIsVerifying(false);
    }
  };

  let sendLabel = 'Send me a code';
  if (cooldown.isCoolingDown) {
    sendLabel = `Resend in ${String(cooldown.remaining)}s`;
  } else if (codeRequested) {
    sendLabel = 'Resend code';
  }

  return {
    code,
    onCodeChange,
    /** True once a code has been asked for, so the input can be revealed. */
    codeRequested,
    send,
    verify,
    sendLabel,
    canSend: !cooldown.isCoolingDown && !busy,
    canVerify: code.length === CODE_LENGTH && !busy,
    busy,
    isVerifying,
    isSending,
    error,
    notice,
    codeLength: CODE_LENGTH
  };
}
