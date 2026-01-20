import React, { useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Key from 'lucide-react/dist/esm/icons/key';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { changePasswordAPI } from '@/lib/sdk-client';
import { getPasswordStrength } from '@/lib/validation';

// Helper functions moved outside component for consistent-function-scoping
function getPasswordStrengthInfo(password: string) {
  const score = getPasswordStrength(password);
  if (score < 2) return { score, label: 'Weak', color: 'bg-red-500' };
  if (score < 4) return { score, label: 'Medium', color: 'bg-yellow-500' };
  return { score, label: 'Strong', color: 'bg-green-500' };
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
}

interface PasswordFormData {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export function SecuritySettingsTab() {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [formData, setFormData] = useState<PasswordFormData>({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });

  const handleInputChange = (field: keyof PasswordFormData) => {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData((previous) => ({ ...previous, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate passwords
    if (!formData.current_password) {
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

    if (formData.new_password === formData.current_password) {
      setError('New password must be different from your current password');
      return;
    }

    setIsLoading(true);

    try {
      await changePasswordAPI({
        current_password: formData.current_password,
        new_password: formData.new_password
      });

      setSuccess('Password changed successfully!');
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
      setError(error_ instanceof Error ? error_.message : 'Failed to change password');
    } finally {
      setIsLoading(false);
    }
  };

  const passwordStrength = getPasswordStrengthInfo(formData.new_password);

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Security Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>Manage your password and account security.</p>
      </div>

      {/* Account Info Card */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
        <div className='flex items-start gap-3'>
          <Shield className='mt-0.5 h-5 w-5 text-blue-600' />
          <div>
            <h4 className='text-sm font-medium text-blue-900'>Account Security</h4>
            <p className='mt-1 text-xs text-blue-700'>
              Your account is secured with industry-standard encryption. Last profile update:{' '}
              {user?.updated_at ? formatDate(user.updated_at) : 'Unknown'}
            </p>
          </div>
        </div>
      </div>

      {/* Status Messages */}
      <AnimatePresence>
        {success && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3'
          >
            <Check className='h-4 w-4 text-green-600' />
            <span className='text-sm text-green-800'>{success}</span>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Password Change Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
          <Key className='h-4 w-4 text-gray-500' />
          <h4 className='font-medium text-gray-900'>Change Password</h4>
        </div>

        <div className='space-y-2'>
          <Label htmlFor='current_password'>Current Password</Label>
          <Input
            id='current_password'
            type='password'
            value={formData.current_password}
            onChange={handleInputChange('current_password')}
            placeholder='Enter your current password'
            disabled={isLoading}
          />
        </div>

        <div className='space-y-2'>
          <Label htmlFor='new_password'>New Password</Label>
          <Input
            id='new_password'
            type='password'
            value={formData.new_password}
            onChange={handleInputChange('new_password')}
            placeholder='Enter a new secure password'
            disabled={isLoading}
          />

          {/* Password Strength Indicator */}
          {formData.new_password && (
            <div className='space-y-1'>
              <div className='flex items-center gap-2'>
                <div className='h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200'>
                  <div
                    className={`h-full transition-all duration-300 ${passwordStrength.color}`}
                    style={{ width: `${String((passwordStrength.score / 5) * 100)}%` }}
                  />
                </div>
                <span className='min-w-0 text-xs text-gray-500'>{passwordStrength.label}</span>
              </div>
              <ul className='text-xs text-gray-500'>
                <li className={formData.new_password.length >= 8 ? 'text-green-600' : ''}>
                  {formData.new_password.length >= 8 ? '✓' : '○'} At least 8 characters
                </li>
                <li className={/\d/.test(formData.new_password) ? 'text-green-600' : ''}>
                  {/\d/.test(formData.new_password) ? '✓' : '○'} Contains a number
                </li>
                <li className={/[a-zA-Z]/.test(formData.new_password) ? 'text-green-600' : ''}>
                  {/[a-zA-Z]/.test(formData.new_password) ? '✓' : '○'} Contains a letter
                </li>
              </ul>
            </div>
          )}
        </div>

        <div className='space-y-2'>
          <Label htmlFor='confirm_password'>Confirm New Password</Label>
          <Input
            id='confirm_password'
            type='password'
            value={formData.confirm_password}
            onChange={handleInputChange('confirm_password')}
            placeholder='Confirm your new password'
            disabled={isLoading}
          />
          {formData.confirm_password && formData.new_password !== formData.confirm_password && (
            <p className='text-xs text-red-600'>Passwords do not match</p>
          )}
          {formData.confirm_password && formData.new_password === formData.confirm_password && (
            <p className='text-xs text-green-600'>Passwords match</p>
          )}
        </div>

        {/* Submit Button */}
        <div className='flex justify-end pt-2'>
          <Button
            type='submit'
            disabled={
              isLoading ||
              !formData.current_password ||
              !formData.new_password ||
              !formData.confirm_password ||
              formData.new_password !== formData.confirm_password
            }
            className='flex items-center gap-2'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Changing...
              </>
            ) : (
              <>
                <Lock className='h-4 w-4' />
                Change Password
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
