import { useEffect } from 'react';

import type { VerifyOtpFormValues } from '@/lib/schemas';

import { zodResolver } from '@hookform/resolvers/zod';
import Mail from 'lucide-react/dist/esm/icons/mail';
import { useForm } from 'react-hook-form';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { useResendCooldown } from '@/hooks/use-resend-cooldown';
import { verifyOtpSchema } from '@/lib/schemas';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

interface VerifyOtpModalProperties {
  isOpen: boolean;
  email: string;
  onClose: () => void;
  onSwitchToLogin: () => void;
}

export function VerifyOtpModal({
  isOpen,
  email,
  onClose,
  onSwitchToLogin
}: Readonly<VerifyOtpModalProperties>) {
  const { verifyOtp, resendOtp, isLoading, error, clearError } = useAuth();
  const cooldown = useResendCooldown();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors }
  } = useForm<VerifyOtpFormValues>({
    resolver: zodResolver(verifyOtpSchema),
    defaultValues: { code: '' }
  });

  const onSubmit = async (data: VerifyOtpFormValues) => {
    try {
      await verifyOtp(email, data.code.trim());
      onClose();
    } catch {
      // Error displayed by auth context
    }
  };

  const handleResend = async () => {
    if (cooldown.isCoolingDown) return;
    try {
      clearError();
      await resendOtp(email);
      cooldown.start();
    } catch {
      // Error displayed by auth context
    }
  };

  // Reset when modal closes
  useEffect(() => {
    if (!isOpen) {
      reset();
      clearError();
      cooldown.reset();
    }
  }, [isOpen, reset, clearError, cooldown]);

  const handleInputChange = () => {
    if (error) clearError();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title='Verify your email'
      description={`We sent a 6-digit code to ${email}`}
      size='md'
    >
      <div className='relative space-y-4'>
        {isLoading && <AuthLoadingOverlay />}

        {error ? <AuthErrorAlert error={error} onDismiss={clearError} /> : null}

        <div className='flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3'>
          <Mail className='h-4 w-4 flex-shrink-0 text-blue-600' />
          <p className='font-inter text-xs text-blue-800'>
            Check your inbox for a verification code. It expires in 10 minutes.
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
          <Input
            type='text'
            label='Verification Code'
            placeholder='123456'
            {...register('code', { onChange: handleInputChange })}
            error={errors.code?.message}
            isRequired
            disabled={isLoading}
            autoComplete='one-time-code'
            inputMode='numeric'
            maxLength={6}
          />

          <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
            {isLoading ? 'Verifying…' : 'Verify Email'}
          </Button>
        </form>

        <div className='text-center'>
          <p className='font-inter text-muted-foreground text-xs'>
            Didn't receive the code?{' '}
            <button
              type='button'
              onClick={() => void handleResend()}
              disabled={cooldown.isCoolingDown || isLoading}
              className='text-foreground hover:text-secondary font-medium underline disabled:no-underline disabled:opacity-50'
            >
              {cooldown.isCoolingDown ? `Resend in ${String(cooldown.remaining)}s` : 'Resend code'}
            </button>
          </p>
        </div>

        <div className='border-border border-t pt-4 text-center text-sm'>
          <p className='font-inter text-muted-foreground'>
            Already verified?{' '}
            <button
              type='button'
              onClick={onSwitchToLogin}
              className='text-foreground hover:text-secondary font-medium underline'
              disabled={isLoading}
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </Modal>
  );
}
