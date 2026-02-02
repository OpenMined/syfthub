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
                  <div className='bg-muted h-1.5 flex-1 overflow-hidden rounded-full'>
                    <div
                      className={`h-full transition-[width] duration-300 ${passwordStrength.color}`}
                      style={{ width: `${String((passwordStrength.score / 5) * 100)}%` }}
                    />
                  </div>
                  <span className='font-inter text-muted-foreground min-w-0 text-xs'>
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
                className='border-border text-foreground focus:ring-ring mt-0.5 rounded focus:ring-offset-0'
                disabled={isLoading}
              />
              <span className='font-inter text-muted-foreground text-xs leading-relaxed'>
                I agree to the{' '}
                <a href='#' className='text-foreground hover:text-secondary underline'>
                  Terms of Service
                </a>{' '}
                and{' '}
                <a href='#' className='text-foreground hover:text-secondary underline'>
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
        <div className='border-border border-t pt-4 text-center text-sm'>
          <p className='font-inter text-muted-foreground'>
            Already have an account?{' '}
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
