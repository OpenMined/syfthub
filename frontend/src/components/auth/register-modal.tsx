import React, { useEffect, useState } from 'react';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Mail from 'lucide-react/dist/esm/icons/mail';
import User from 'lucide-react/dist/esm/icons/user';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { useForm } from '@/hooks/use-form';
import { AccountingAccountExistsError } from '@/lib/sdk-client';
import {
  getPasswordStrength,
  validateConfirmPassword,
  validateEmail,
  validateName,
  validatePassword
} from '@/lib/validation';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

// Password strength indicator - moved outside component for consistent-function-scoping
function getPasswordStrengthInfo(password: string) {
  const score = getPasswordStrength(password);
  if (score < 2) return { score, label: 'Weak', color: 'bg-red-500' };
  if (score < 4) return { score, label: 'Medium', color: 'bg-yellow-500' };
  return { score, label: 'Strong', color: 'bg-green-500' };
}

interface RegisterFormValues {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
  accountingPassword: string;
}

// Stable reference to prevent useForm from recreating resetForm on every render
const REGISTER_INITIAL_VALUES: RegisterFormValues = {
  name: '',
  email: '',
  password: '',
  confirmPassword: '',
  accountingPassword: ''
};

interface RegisterModalProperties {
  isOpen: boolean;
  onClose: () => void;
  onSwitchToLogin: () => void;
}

export function RegisterModal({
  isOpen,
  onClose,
  onSwitchToLogin
}: Readonly<RegisterModalProperties>) {
  const { register, isLoading, error, clearError } = useAuth();
  const [requiresAccountingPassword, setRequiresAccountingPassword] = useState(false);

  const { values, errors, handleChange, handleSubmit, resetForm, setFieldError } =
    useForm<RegisterFormValues>({
      initialValues: REGISTER_INITIAL_VALUES,
      validators: {
        name: (value) => validateName(value),
        email: (value) => validateEmail(value),
        password: (value) => validatePassword(value),
        confirmPassword: (value, allValues) => validateConfirmPassword(allValues.password, value)
      },
      onSubmit: async (formValues) => {
        try {
          await register({
            name: formValues.name.trim(),
            email: formValues.email.trim(),
            password: formValues.password,
            // Only include accounting password if required (after 409 error)
            accountingPassword: formValues.accountingPassword || undefined
          });
          onClose(); // Close modal on successful registration
        } catch (error_) {
          // Check if this is an accounting account exists error
          if (error_ instanceof AccountingAccountExistsError) {
            // Show accounting password field to link existing account
            setRequiresAccountingPassword(true);
          }
          // Other errors are handled by the auth context
        }
      }
    });

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      resetForm();
      clearError();
      setRequiresAccountingPassword(false);
    }
  }, [isOpen, resetForm, clearError]);

  // Clear auth error when user starts typing
  const handleInputChange =
    (field: keyof RegisterFormValues) => (e: React.ChangeEvent<HTMLInputElement>) => {
      handleChange(field)(e);

      // Clear confirm password error if user is typing in password field
      if (field === 'password' && errors.confirmPassword) {
        setFieldError('confirmPassword', null);
      }

      // Reset accounting requirement if email changes (different email might not have existing account)
      if (field === 'email' && requiresAccountingPassword) {
        setRequiresAccountingPassword(false);
      }

      if (error) {
        clearError();
      }
    };

  // OAuth handlers commented out - not supported in v1
  // const handleGoogleRegister = async () => {
  //   try {
  //     await loginWithGoogle();
  //     onClose();
  //   } catch {
  //     // Error handled by context
  //   }
  // };

  // const handleGitHubRegister = async () => {
  //   try {
  //     await loginWithGitHub();
  //     onClose();
  //   } catch {
  //     // Error handled by context
  //   }
  // };

  const passwordStrength = getPasswordStrengthInfo(values.password);

  // Determine submit button text based on state
  const getSubmitButtonText = () => {
    if (isLoading) return 'Creating Account…';
    if (requiresAccountingPassword) return 'Link & Create Account';
    return 'Create Account';
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title='Create your account'
      description='Join SyftHub and start building privacy-first AI'
      size='lg'
    >
      <div className='relative space-y-4'>
        {isLoading && <AuthLoadingOverlay />}

        {/* Global Error */}
        {error ? <AuthErrorAlert error={error} onDismiss={clearError} /> : null}

        {/* OAuth Buttons - Hidden for v1, uncomment when OAuth is implemented
        <div className='space-y-2'>
          <Button
            type='button'
            variant='outline'
            size='lg'
            className='font-inter w-full'
            onClick={handleGoogleRegister}
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
            Sign up with Google
          </Button>

          <Button
            type='button'
            variant='outline'
            size='lg'
            className='font-inter w-full'
            onClick={handleGitHubRegister}
            disabled={isLoading}
          >
            <svg className='mr-2 h-4 w-4' fill='currentColor' viewBox='0 0 24 24'>
              <path d='M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' />
            </svg>
            Sign up with GitHub
          </Button>
        </div>

        <div className='relative'>
          <div className='absolute inset-0 flex items-center'>
            <span className='border-syft-border w-full border-t' />
          </div>
          <div className='relative flex justify-center text-xs uppercase'>
            <span className='font-inter text-syft-muted bg-white px-2'>Or create account with</span>
          </div>
        </div>
        End of OAuth section */}

        {/* Registration Form */}
        <form onSubmit={handleSubmit} className='space-y-4'>
          <Input
            type='text'
            name='name'
            label='Full Name'
            placeholder='John Doe…'
            value={values.name}
            onChange={handleInputChange('name')}
            error={errors.name}
            leftIcon={<User className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
            autoComplete='name'
          />

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

          <div className='space-y-2'>
            <Input
              type='password'
              name='password'
              label='Password'
              placeholder='Create a secure password…'
              value={values.password}
              onChange={handleInputChange('password')}
              error={errors.password}
              isRequired
              disabled={isLoading}
              autoComplete='new-password'
            />

            {/* Password Strength Indicator */}
            {values.password ? (
              <div className='space-y-1'>
                <div className='flex items-center gap-2'>
                  <div className='h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200'>
                    <div
                      className={`h-full transition-[width] duration-300 ${passwordStrength.color}`}
                      style={{ width: `${String((passwordStrength.score / 5) * 100)}%` }}
                    />
                  </div>
                  <span className='font-inter text-syft-muted min-w-0 text-xs'>
                    {passwordStrength.label}
                  </span>
                </div>
              </div>
            ) : null}
          </div>

          <Input
            type='password'
            name='confirmPassword'
            label='Confirm Password'
            placeholder='Confirm your password…'
            value={values.confirmPassword}
            onChange={handleInputChange('confirmPassword')}
            error={errors.confirmPassword}
            isRequired
            disabled={isLoading}
            autoComplete='new-password'
          />

          {/* Accounting Password Section - Only shown when email exists in accounting service */}
          {requiresAccountingPassword ? (
            <div className='space-y-3 rounded-lg border border-amber-400 bg-amber-50 p-4'>
              <div className='flex items-start gap-2'>
                <AlertCircle className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600' />
                <p className='font-inter text-xs text-amber-800'>
                  An accounting account with this email already exists. Please enter your existing
                  accounting password to link your accounts.
                </p>
              </div>

              <Input
                type='password'
                label='Accounting Password'
                placeholder='Enter your existing accounting password…'
                value={values.accountingPassword}
                onChange={handleInputChange('accountingPassword')}
                error={errors.accountingPassword}
                leftIcon={<Lock className='h-4 w-4' />}
                disabled={isLoading}
                isRequired
              />
            </div>
          ) : null}

          <div className='space-y-2 text-sm'>
            <label htmlFor='terms-agreement' className='flex cursor-pointer items-start space-x-2'>
              <input
                type='checkbox'
                id='terms-agreement'
                name='terms-agreement'
                required
                className='border-syft-border text-syft-primary focus:ring-syft-primary mt-0.5 rounded focus:ring-offset-0'
                disabled={isLoading}
              />
              <span className='font-inter text-syft-muted text-xs leading-relaxed'>
                I agree to the{' '}
                <a href='#' className='text-syft-primary hover:text-syft-secondary underline'>
                  Terms of Service
                </a>{' '}
                and{' '}
                <a href='#' className='text-syft-primary hover:text-syft-secondary underline'>
                  Privacy Policy
                </a>
              </span>
            </label>
          </div>

          <Button type='submit' size='lg' className='font-inter w-full' disabled={isLoading}>
            {getSubmitButtonText()}
          </Button>
        </form>

        {/* Switch to Login */}
        <div className='border-syft-border border-t pt-4 text-center text-sm'>
          <p className='font-inter text-syft-muted'>
            Already have an account?{' '}
            <button
              type='button'
              onClick={onSwitchToLogin}
              className='text-syft-primary hover:text-syft-secondary font-medium underline'
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
