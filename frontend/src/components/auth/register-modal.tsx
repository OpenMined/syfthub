import { useEffect, useState } from 'react';

import type { RegisterFormValues } from '@/lib/schemas';

import { zodResolver } from '@hookform/resolvers/zod';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Mail from 'lucide-react/dist/esm/icons/mail';
import User from 'lucide-react/dist/esm/icons/user';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { registerSchema } from '@/lib/schemas';
import { AccountingAccountExistsError } from '@/lib/sdk-client';
import { getPasswordStrength } from '@/lib/validation';
import { useOnboardingStore } from '@/stores/onboarding-store';

import { AuthErrorAlert, AuthLoadingOverlay } from './auth-utils';

// Password strength indicator
function getPasswordStrengthInfo(password: string) {
  const score = getPasswordStrength(password);
  if (score < 2) return { score, label: 'Weak', color: 'bg-red-500' };
  if (score < 4) return { score, label: 'Medium', color: 'bg-yellow-500' };
  return { score, label: 'Strong', color: 'bg-green-500' };
}

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
  const { register: authRegister, isLoading, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [requiresAccountingPassword, setRequiresAccountingPassword] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors }
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      name: '',
      email: '',
      password: '',
      confirmPassword: '',
      accountingPassword: ''
    }
  });

  const passwordValue = watch('password');
  const passwordStrength = getPasswordStrengthInfo(passwordValue);

  const onSubmit = async (data: RegisterFormValues) => {
    try {
      await authRegister({
        name: data.name.trim(),
        email: data.email.trim(),
        password: data.password,
        accountingPassword: data.accountingPassword || undefined
      });
      onClose();
      useOnboardingStore.getState().startOnboarding();
      navigate('/chat');
    } catch (error_) {
      if (error_ instanceof AccountingAccountExistsError) {
        setRequiresAccountingPassword(true);
      }
    }
  };

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      reset();
      clearError();
      setRequiresAccountingPassword(false);
    }
  }, [isOpen, reset, clearError]);

  // Clear auth error when user starts typing
  const handleInputChange = () => {
    if (error) {
      clearError();
    }
  };

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
        <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
          <Input
            type='text'
            label='Full Name'
            placeholder='John Doe…'
            {...register('name', { onChange: handleInputChange })}
            error={errors.name?.message}
            leftIcon={<User className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
            autoComplete='name'
          />

          <Input
            type='email'
            label='Email'
            placeholder='name@company.com…'
            {...register('email', {
              onChange: () => {
                handleInputChange();
                if (requiresAccountingPassword) {
                  setRequiresAccountingPassword(false);
                }
              }
            })}
            error={errors.email?.message}
            leftIcon={<Mail className='h-4 w-4' />}
            isRequired
            disabled={isLoading}
            autoComplete='email'
            spellCheck={false}
          />

          <div className='space-y-2'>
            <Input
              type='password'
              label='Password'
              placeholder='Create a secure password…'
              {...register('password', { onChange: handleInputChange })}
              error={errors.password?.message}
              isRequired
              disabled={isLoading}
              autoComplete='new-password'
            />

            {/* Password Strength Indicator */}
            {passwordValue ? (
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
            label='Confirm Password'
            placeholder='Confirm your password…'
            {...register('confirmPassword', { onChange: handleInputChange })}
            error={errors.confirmPassword?.message}
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
                {...register('accountingPassword', { onChange: handleInputChange })}
                error={errors.accountingPassword?.message}
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
