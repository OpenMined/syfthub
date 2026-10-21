import React, { useCallback, useState } from 'react';

import Key from 'lucide-react/dist/esm/icons/key';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { formatDateLong } from '@/lib/date-utils';
import { changePasswordAPI } from '@/lib/sdk-client';
import { getPasswordStrengthInfo } from '@/lib/validation';

import { StatusMessage } from './status-message';

interface PasswordFormData {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export function SecuritySettingsTab() {
  const { user, refreshUser } = useAuth();
  // An account created with Google sign-in has no password yet. It sets its
  // first one without a "current password": the signed-in session is the proof.
  const hasPassword = user?.has_password !== false;
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [formData, setFormData] = useState<PasswordFormData>({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });

  const handleInputChange = useCallback((field: keyof PasswordFormData) => {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData((previous) => ({ ...previous, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate passwords
    if (hasPassword && !formData.current_password) {
      setError('Please enter your current password');
      return;
    }

    if (!formData.new_password) {
      setError('Please enter a new password');
      return;
    }

    if (formData.new_password.length < 8) {
      setError('New password must be at least 8 characters long');
      return;
    }

    if (!/\d/.test(formData.new_password)) {
      setError('New password must contain at least one digit');
      return;
    }

    if (!/[a-zA-Z]/.test(formData.new_password)) {
      setError('New password must contain at least one letter');
      return;
    }

    if (formData.new_password !== formData.confirm_password) {
      setError('New passwords do not match');
      return;
    }

    if (hasPassword && formData.new_password === formData.current_password) {
      setError('New password must be different from your current password');
      return;
    }

    setIsLoading(true);
    const fallbackError = hasPassword ? 'Failed to change password' : 'Failed to set password';

    try {
      await changePasswordAPI({
        current_password: hasPassword ? formData.current_password : '',
        new_password: formData.new_password
      });

      if (hasPassword) {
        setSuccess('Password changed successfully!');
      } else {
        setSuccess('Password set. You can now sign in with your email and password too.');
        // Flip has_password so the form switches to "change" mode.
        await refreshUser();
      }
      setFormData({
        current_password: '',
        new_password: '',
        confirm_password: ''
      });

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : fallbackError);
    } finally {
      setIsLoading(false);
    }
  };

  const passwordStrength = getPasswordStrengthInfo(formData.new_password);
  const strengthPercent = Math.round((passwordStrength.score / 5) * 100);

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-foreground text-lg font-semibold'>Security Settings</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Manage your password and account security.
        </p>
      </div>

      {/* Account Info Card */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950'>
        <div className='flex items-start gap-3'>
          <Shield className='mt-0.5 h-5 w-5 text-blue-600 dark:text-blue-400' />
          <div>
            <h4 className='text-sm font-medium text-blue-900 dark:text-blue-100'>
              Account Security
            </h4>
            <p className='mt-1 text-xs text-blue-700 dark:text-blue-300'>
              {hasPassword
                ? 'Your account is secured with industry-standard encryption.'
                : 'You sign in with Google. Add a password below to also sign in with your email.'}{' '}
              Last profile update: {user?.updated_at ? formatDateLong(user.updated_at) : 'Unknown'}
            </p>
          </div>
        </div>
      </div>

      {/* Status Messages */}
      <StatusMessage type='success' message={success} />
      <StatusMessage type='error' message={error} />

      {/* Password Change Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='border-border flex items-center gap-2 border-t pt-4'>
          <Key className='text-muted-foreground h-4 w-4' />
          <h4 className='text-foreground font-medium'>
            {hasPassword ? 'Change Password' : 'Set a Password'}
          </h4>
        </div>

        {hasPassword ? (
          <div className='space-y-2'>
            <Label htmlFor='current_password'>Current Password</Label>
            <Input
              id='current_password'
              name='current_password'
              type='password'
              value={formData.current_password}
              onChange={handleInputChange('current_password')}
              placeholder='Enter your current password…'
              autoComplete='current-password'
              disabled={isLoading}
            />
          </div>
        ) : (
          <p className='text-muted-foreground text-sm'>
            Your account has no password yet. Choose one to sign in with your email as well as with
            Google.
          </p>
        )}

        <div className='space-y-2'>
          <Label htmlFor='new_password'>New Password</Label>
          <Input
            id='new_password'
            name='new_password'
            type='password'
            value={formData.new_password}
            onChange={handleInputChange('new_password')}
            placeholder='Enter a new secure password…'
            autoComplete='new-password'
            disabled={isLoading}
          />

          {/* Password Strength Indicator */}
          {formData.new_password ? (
            <div className='space-y-1'>
              <div className='flex items-center gap-2'>
                <div
                  role='progressbar'
                  aria-label='Password strength'
                  aria-valuenow={strengthPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className='bg-muted h-1.5 flex-1 overflow-hidden rounded-full'
                >
                  <div
                    className={`h-full transition-[width] duration-300 ${passwordStrength.color}`}
                    style={{ width: `${String(strengthPercent)}%` }}
                  />
                </div>
                <span className='text-muted-foreground min-w-0 text-xs'>
                  {passwordStrength.label}
                </span>
              </div>
              <ul className='text-muted-foreground text-xs'>
                <li
                  className={
                    formData.new_password.length >= 8 ? 'text-green-600 dark:text-green-400' : ''
                  }
                >
                  {formData.new_password.length >= 8 ? '\u2713' : '\u25CB'} At least 8 characters
                </li>
                <li
                  className={
                    /\d/.test(formData.new_password) ? 'text-green-600 dark:text-green-400' : ''
                  }
                >
                  {/\d/.test(formData.new_password) ? '\u2713' : '\u25CB'} Contains a number
                </li>
                <li
                  className={
                    /[a-zA-Z]/.test(formData.new_password)
                      ? 'text-green-600 dark:text-green-400'
                      : ''
                  }
                >
                  {/[a-zA-Z]/.test(formData.new_password) ? '\u2713' : '\u25CB'} Contains a letter
                </li>
              </ul>
            </div>
          ) : null}
        </div>

        <div className='space-y-2'>
          <Label htmlFor='confirm_password'>Confirm New Password</Label>
          <Input
            id='confirm_password'
            name='confirm_password'
            type='password'
            value={formData.confirm_password}
            onChange={handleInputChange('confirm_password')}
            placeholder='Confirm your new password…'
            autoComplete='new-password'
            disabled={isLoading}
          />
          {formData.confirm_password && formData.new_password !== formData.confirm_password ? (
            <p className='text-xs text-red-600 dark:text-red-400'>Passwords do not match</p>
          ) : null}
          {formData.confirm_password && formData.new_password === formData.confirm_password ? (
            <p className='text-xs text-green-600 dark:text-green-400'>Passwords match</p>
          ) : null}
        </div>

        {/* Submit Button */}
        <div className='border-border flex justify-end border-t pt-4'>
          <Button
            type='submit'
            disabled={
              isLoading ||
              (hasPassword && !formData.current_password) ||
              !formData.new_password ||
              !formData.confirm_password ||
              formData.new_password !== formData.confirm_password
            }
            className='flex items-center gap-2'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                {hasPassword ? 'Changing…' : 'Setting…'}
              </>
            ) : (
              <>
                <Lock className='h-4 w-4' aria-hidden='true' />
                {hasPassword ? 'Change Password' : 'Set Password'}
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
