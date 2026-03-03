import { useEffect, useRef, useState } from 'react';

import type { PasswordResetConfirmFormValues, PasswordResetRequestFormValues } from '@/lib/schemas';

import { zodResolver } from '@hookform/resolvers/zod';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Mail from 'lucide-react/dist/esm/icons/mail';
import { useForm } from 'react-hook-form';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { passwordResetConfirmSchema, passwordResetRequestSchema } from '@/lib/schemas';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

type ResetStep = 'request' | 'confirm' | 'success';

interface PasswordResetModalProperties {
  isOpen: boolean;
  initialEmail?: string | null;
  onClose: () => void;
  onSwitchToLogin: () => void;
}

export function PasswordResetModal({
  isOpen,
  initialEmail,
  onClose,
  onSwitchToLogin
}: Readonly<PasswordResetModalProperties>) {
  const { requestPasswordReset, confirmPasswordReset, isLoading, error, clearError } = useAuth();
  const [step, setStep] = useState<ResetStep>('request');
  const [email, setEmail] = useState('');
  const [resendCooldown, setResendCooldown] = useState(0);
  const timerReference = useRef<ReturnType<typeof setTimeout>>(null);

  // Request form
  const requestForm = useForm<PasswordResetRequestFormValues>({
    resolver: zodResolver(passwordResetRequestSchema),
    defaultValues: { email: '' }
  });

  // Confirm form
  const confirmForm = useForm<PasswordResetConfirmFormValues>({
    resolver: zodResolver(passwordResetConfirmSchema),
    defaultValues: { code: '', newPassword: '', confirmPassword: '' }
  });

  // Set initial email when modal opens
  useEffect(() => {
    if (isOpen && initialEmail) {
      setEmail(initialEmail);
      requestForm.setValue('email', initialEmail);
    }
  }, [isOpen, initialEmail, requestForm]);

  const onRequestSubmit = async (data: PasswordResetRequestFormValues) => {
    try {
      await requestPasswordReset(data.email.trim());
      setEmail(data.email.trim());
      setStep('confirm');
    } catch {
      // Error displayed by auth context
    }
  };

  const onConfirmSubmit = async (data: PasswordResetConfirmFormValues) => {
    try {
      await confirmPasswordReset(email, data.code.trim(), data.newPassword);
      setStep('success');
    } catch {
      // Error displayed by auth context
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    try {
      clearError();
      await requestPasswordReset(email);
      setResendCooldown(60);
    } catch {
      // Error displayed by auth context
    }
  };

  // Cooldown timer — uses setTimeout chain to avoid re-running the effect on every tick
  useEffect(() => {
    if (resendCooldown <= 0) return;
    timerReference.current = setTimeout(() => {
      setResendCooldown((previous) => previous - 1);
    }, 1000);
    return () => {
      if (timerReference.current) clearTimeout(timerReference.current);
    };
  }, [resendCooldown]);

  // Reset when modal closes
  useEffect(() => {
    if (!isOpen) {
      setStep('request');
      setEmail('');
      setResendCooldown(0);
      requestForm.reset();
      confirmForm.reset();
      clearError();
    }
  }, [isOpen, requestForm, confirmForm, clearError]);

  const handleInputChange = () => {
    if (error) clearError();
  };

  const getTitle = () => {
    switch (step) {
      case 'request': {
        return 'Reset your password';
      }
      case 'confirm': {
        return 'Enter reset code';
      }
      case 'success': {
        return 'Password reset';
      }
    }
  };

  const getDescription = () => {
    switch (step) {
      case 'request': {
        return "Enter your email and we'll send you a reset code";
      }
      case 'confirm': {
        return `We sent a 6-digit code to ${email}`;
      }
      case 'success': {
        return 'Your password has been changed successfully';
      }
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={getTitle()}
      description={getDescription()}
      size='md'
    >
      <div className='relative space-y-4'>
        {isLoading && <AuthLoadingOverlay />}

        {error ? <AuthErrorAlert error={error} onDismiss={clearError} /> : null}

        {/* Step 1: Request */}
        {step === 'request' && (
          <form onSubmit={requestForm.handleSubmit(onRequestSubmit)} className='space-y-4'>
            <Input
              type='email'
              label='Email'
              placeholder='name@company.com…'
              {...requestForm.register('email', { onChange: handleInputChange })}
              error={requestForm.formState.errors.email?.message}
              leftIcon={<Mail className='h-4 w-4' />}
              isRequired
              disabled={isLoading}
              autoComplete='email'
              spellCheck={false}
            />

            <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
              {isLoading ? 'Sending…' : 'Send Reset Code'}
            </Button>
          </form>
        )}

        {/* Step 2: Confirm */}
        {step === 'confirm' && (
          <>
            <div className='flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3'>
              <Mail className='h-4 w-4 flex-shrink-0 text-blue-600' />
              <p className='font-inter text-xs text-blue-800'>
                Check your inbox for a reset code. It expires in 10 minutes.
              </p>
            </div>

            <form onSubmit={confirmForm.handleSubmit(onConfirmSubmit)} className='space-y-4'>
              <Input
                type='text'
                label='Reset Code'
                placeholder='123456'
                {...confirmForm.register('code', { onChange: handleInputChange })}
                error={confirmForm.formState.errors.code?.message}
                isRequired
                disabled={isLoading}
                autoComplete='one-time-code'
                inputMode='numeric'
                maxLength={6}
              />

              <Input
                type='password'
                label='New Password'
                placeholder='Enter your new password…'
                {...confirmForm.register('newPassword', { onChange: handleInputChange })}
                error={confirmForm.formState.errors.newPassword?.message}
                isRequired
                disabled={isLoading}
                autoComplete='new-password'
              />

              <Input
                type='password'
                label='Confirm Password'
                placeholder='Confirm your new password…'
                {...confirmForm.register('confirmPassword', { onChange: handleInputChange })}
                error={confirmForm.formState.errors.confirmPassword?.message}
                isRequired
                disabled={isLoading}
                autoComplete='new-password'
              />

              <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
                {isLoading ? 'Resetting…' : 'Reset Password'}
              </Button>
            </form>

            <div className='text-center'>
              <p className='font-inter text-muted-foreground text-xs'>
                Didn't receive the code?{' '}
                <button
                  type='button'
                  onClick={() => void handleResend()}
                  disabled={resendCooldown > 0 || isLoading}
                  className='text-foreground hover:text-secondary font-medium underline disabled:no-underline disabled:opacity-50'
                >
                  {resendCooldown > 0 ? `Resend in ${String(resendCooldown)}s` : 'Resend code'}
                </button>
              </p>
            </div>
          </>
        )}

        {/* Step 3: Success */}
        {step === 'success' && (
          <div className='space-y-4 text-center'>
            <div className='flex justify-center'>
              <CheckCircle className='h-12 w-12 text-green-500' />
            </div>
            <p className='font-inter text-muted-foreground text-sm'>
              Your password has been reset. You can now sign in with your new password.
            </p>
            <Button type='button' size='lg' className='font-inter w-full' onClick={onSwitchToLogin}>
              Sign In
            </Button>
          </div>
        )}

        {/* Back to login (on request/confirm steps) */}
        {step !== 'success' && (
          <div className='border-border border-t pt-4 text-center text-sm'>
            <p className='font-inter text-muted-foreground'>
              Remember your password?{' '}
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
        )}
      </div>
    </Modal>
  );
}
