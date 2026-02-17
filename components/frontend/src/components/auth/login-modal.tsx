import { useEffect } from 'react';

import type { LoginFormValues } from '@/lib/schemas';

import { zodResolver } from '@hookform/resolvers/zod';
import { GoogleLogin } from '@react-oauth/google';
import Mail from 'lucide-react/dist/esm/icons/mail';
import { useForm } from 'react-hook-form';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { loginSchema } from '@/lib/schemas';
import { isGoogleOAuthEnabled } from '@/lib/sdk-client';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

const googleOAuthEnabled = isGoogleOAuthEnabled();

interface LoginModalProperties {
  isOpen: boolean;
  onClose: () => void;
  onSwitchToRegister: () => void;
}

export function LoginModal({
  isOpen,
  onClose,
  onSwitchToRegister
}: Readonly<LoginModalProperties>) {
  const { login, loginWithGoogle, isLoading, error, clearError } = useAuth();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors }
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' }
  });

  const onSubmit = async (data: LoginFormValues) => {
    try {
      await login({
        email: data.email.trim(),
        password: data.password
      });
      onClose();
    } catch {
      // Error is handled by the auth context
    }
  };

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      reset();
      clearError();
    }
  }, [isOpen, reset, clearError]);

  // Clear auth error when user starts typing
  const handleInputChange = () => {
    if (error) {
      clearError();
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title='Welcome back'
      description='Sign in to your SyftHub account'
      size='md'
    >
      <div className='relative space-y-4'>
        {isLoading && <AuthLoadingOverlay />}

        {/* Global Error */}
        {error && <AuthErrorAlert error={error} onDismiss={clearError} />}

        {/* Email/Password Form */}
        <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
          <Input
            type='email'
            label='Email'
            placeholder='name@company.com…'
            {...register('email', { onChange: handleInputChange })}
            error={errors.email?.message}
            leftIcon={<Mail className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
            autoComplete='email'
            spellCheck={false}
          />

          <Input
            type='password'
            label='Password'
            placeholder='Enter your password…'
            {...register('password', { onChange: handleInputChange })}
            error={errors.password?.message}
            isRequired
            disabled={isLoading}
            autoComplete='current-password'
          />

          <div className='flex items-center justify-between text-sm'>
            <label htmlFor='remember-me' className='flex cursor-pointer items-center space-x-2'>
              <input
                type='checkbox'
                id='remember-me'
                name='remember-me'
                className='border-border text-foreground focus:ring-ring rounded focus:ring-offset-0'
              />
              <span className='font-inter text-muted-foreground'>Remember me</span>
            </label>
            <a href='#' className='font-inter text-foreground hover:text-secondary font-medium'>
              Forgot password?
            </a>
          </div>

          <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
            {isLoading ? 'Signing in…' : 'Sign In'}
          </Button>
        </form>

        {/* Google OAuth - only shown if configured */}
        {googleOAuthEnabled && (
          <>
            <div className='relative my-4'>
              <div className='absolute inset-0 flex items-center'>
                <span className='border-border w-full border-t' />
              </div>
              <div className='relative flex justify-center text-xs uppercase'>
                <span className='bg-background text-muted-foreground px-2'>Or continue with</span>
              </div>
            </div>

            <div className='flex justify-center'>
              <GoogleLogin
                onSuccess={(credentialResponse) => {
                  if (credentialResponse.credential) {
                    void loginWithGoogle(credentialResponse.credential).then(() => {
                      onClose();
                    });
                  }
                }}
                onError={() => {
                  clearError();
                }}
                theme='outline'
                size='large'
                width='100%'
                text='signin_with'
              />
            </div>
          </>
        )}

        {/* Switch to Register */}
        <div className='border-border border-t pt-4 text-center text-sm'>
          <p className='font-inter text-muted-foreground'>
            Don't have an account?{' '}
            <button
              type='button'
              onClick={onSwitchToRegister}
              className='text-foreground hover:text-secondary font-medium underline'
              disabled={isLoading}
            >
              Sign up
            </button>
          </p>
        </div>
      </div>
    </Modal>
  );
}
