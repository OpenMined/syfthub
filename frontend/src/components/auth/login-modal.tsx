import React, { useEffect } from 'react';

import Mail from 'lucide-react/dist/esm/icons/mail';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { useForm } from '@/hooks/use-form';
import { validateEmail, validatePassword } from '@/lib/validation';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

interface LoginFormValues {
  email: string;
  password: string;
}

// Stable reference to prevent useForm from recreating resetForm on every render
const LOGIN_INITIAL_VALUES: LoginFormValues = {
  email: '',
  password: ''
};

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
  const { login, isLoading, error, clearError } = useAuth();

  const { values, errors, handleChange, handleSubmit, resetForm } = useForm<LoginFormValues>({
    initialValues: LOGIN_INITIAL_VALUES,
    validators: {
      email: (value) => validateEmail(value),
      password: (value) => validatePassword(value)
    },
    onSubmit: async (formValues) => {
      try {
        await login({
          email: formValues.email.trim(),
          password: formValues.password
        });
        onClose(); // Close modal on successful login
      } catch {
        // Error is handled by the auth context
        // No need to do anything here
      }
    }
  });

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      resetForm();
      clearError();
    }
  }, [isOpen, resetForm, clearError]);

  // Clear auth error when user starts typing
  const handleInputChange =
    (field: keyof LoginFormValues) => (e: React.ChangeEvent<HTMLInputElement>) => {
      handleChange(field)(e);
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
        <form onSubmit={handleSubmit} className='space-y-4'>
          <Input
            type='email'
            name='email'
            label='Email'
            placeholder='name@company.com…'
            value={values.email}
            onChange={handleInputChange('email')}
            error={errors.email}
            leftIcon={<Mail className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
            autoComplete='email'
            spellCheck={false}
          />

          <Input
            type='password'
            name='password'
            label='Password'
            placeholder='Enter your password…'
            value={values.password}
            onChange={handleInputChange('password')}
            error={errors.password}
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
