import React, { useState } from 'react';

import { Mail } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { validateEmail, validatePassword } from '@/lib/validation';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

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
  const { login, loginWithGoogle, loginWithGitHub, isLoading, error, clearError } = useAuth();

  const [formData, setFormData] = useState({
    email: '',
    password: ''
  });

  const [formErrors, setFormErrors] = useState({
    email: '',
    password: ''
  });

  // Reset form when modal closes
  React.useEffect(() => {
    if (!isOpen) {
      setFormData({ email: '', password: '' });
      setFormErrors({ email: '', password: '' });
      clearError();
    }
  }, [isOpen, clearError]);

  const validateForm = (): boolean => {
    const emailError = validateEmail(formData.email) || '';
    const passwordError = validatePassword(formData.password) || '';

    setFormErrors({
      email: emailError,
      password: passwordError
    });

    return !emailError && !passwordError;
  };

  const handleInputChange =
    (field: 'email' | 'password') => (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value;
      setFormData((previous) => ({ ...previous, [field]: value }));

      // Clear field error when user starts typing
      if (formErrors[field]) {
        setFormErrors((previous) => ({ ...previous, [field]: '' }));
      }

      // Clear global error when user starts typing
      if (error) {
        clearError();
      }
    };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      await login({
        email: formData.email.trim(),
        password: formData.password
      });
      onClose(); // Close modal on successful login
    } catch (error) {
      // Error is handled by the auth context
      console.error('Login failed:', error);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      await loginWithGoogle();
      onClose(); // Close modal on successful login
    } catch (error) {
      console.error('Google login failed:', error);
    }
  };

  const handleGitHubLogin = async () => {
    try {
      await loginWithGitHub();
      onClose(); // Close modal on successful login
    } catch (error) {
      console.error('GitHub login failed:', error);
    }
  };

  const handleSwitchToRegister = () => {
    onSwitchToRegister();
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

        {/* OAuth Buttons */}
        <div className='space-y-2'>
          <Button
            type='button'
            variant='outline'
            size='lg'
            className='font-inter w-full'
            onClick={handleGoogleLogin}
            disabled={isLoading}
          >
            <svg className='mr-2 h-4 w-4' viewBox='0 0 24 24'>
              <path
                d='M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z'
                fill='#4285F4'
              />
              <path
                d='M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z'
                fill='#34A853'
              />
              <path
                d='M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z'
                fill='#FBBC05'
              />
              <path
                d='M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z'
                fill='#EA4335'
              />
            </svg>
            Continue with Google
          </Button>

          <Button
            type='button'
            variant='outline'
            size='lg'
            className='font-inter w-full'
            onClick={handleGitHubLogin}
            disabled={isLoading}
          >
            <svg className='mr-2 h-4 w-4' fill='currentColor' viewBox='0 0 24 24'>
              <path d='M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' />
            </svg>
            Continue with GitHub
          </Button>
        </div>

        {/* Divider */}
        <div className='relative'>
          <div className='absolute inset-0 flex items-center'>
            <span className='w-full border-t border-[#ecebef]' />
          </div>
          <div className='relative flex justify-center text-xs uppercase'>
            <span className='font-inter bg-white px-2 text-[#5e5a72]'>Or continue with</span>
          </div>
        </div>

        {/* Email/Password Form */}
        <form onSubmit={handleSubmit} className='space-y-4'>
          <Input
            type='email'
            label='Email'
            placeholder='name@company.com'
            value={formData.email}
            onChange={handleInputChange('email')}
            error={formErrors.email}
            leftIcon={<Mail className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
          />

          <Input
            type='password'
            label='Password'
            placeholder='Enter your password'
            value={formData.password}
            onChange={handleInputChange('password')}
            error={formErrors.password}
            isRequired
            disabled={isLoading}
          />

          <div className='flex items-center justify-between text-sm'>
            <label className='flex items-center space-x-2'>
              <input
                type='checkbox'
                className='rounded border-[#cfcdd6] text-[#272532] focus:ring-[#272532] focus:ring-offset-0'
              />
              <span className='font-inter text-[#5e5a72]'>Remember me</span>
            </label>
            <a href='#' className='font-inter font-medium text-[#272532] hover:text-[#6976ae]'>
              Forgot password?
            </a>
          </div>

          <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
            {isLoading ? 'Signing in...' : 'Sign in'}
          </Button>
        </form>

        {/* Switch to Register */}
        <div className='border-t border-[#ecebef] pt-4 text-center text-sm'>
          <p className='font-inter text-[#5e5a72]'>
            Don't have an account?{' '}
            <button
              type='button'
              onClick={handleSwitchToRegister}
              className='font-medium text-[#272532] underline hover:text-[#6976ae]'
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
