/**
 * Payment Settings Tab
 *
 * Allows users to configure their accounting service credentials.
 * Credentials are stored securely in the SyftHub backend.
 */

import React, { useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Eye from 'lucide-react/dist/esm/icons/eye';
import EyeOff from 'lucide-react/dist/esm/icons/eye-off';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Save from 'lucide-react/dist/esm/icons/save';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAccounting } from '@/hooks/use-accounting';

// =============================================================================
// Types
// =============================================================================

interface FormData {
  url: string;
  password: string;
}

// =============================================================================
// Validation
// =============================================================================

function validateUrl(url: string): string | null {
  if (!url.trim()) return 'URL is required';
  try {
    new URL(url);
    return null;
  } catch {
    return 'Please enter a valid URL (e.g., https://accounting.example.com)';
  }
}

// =============================================================================
// Main Component
// =============================================================================

export function PaymentSettingsTab() {
  const { credentials, isConfigured, isLoading, error, clearError, updateCredentials } =
    useAccounting();

  const [formData, setFormData] = useState<FormData>({
    url: '',
    password: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const handleInputChange = useCallback(
    (field: keyof FormData) => (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData((previous) => ({ ...previous, [field]: e.target.value }));
      setLocalError(null);
      setSuccess(false);
      clearError();
    },
    [clearError]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    setSuccess(false);
    clearError();

    // Validate URL
    const urlError = validateUrl(formData.url);
    if (urlError) {
      setLocalError(urlError);
      return;
    }

    if (!formData.password.trim()) {
      setLocalError('Password is required');
      return;
    }

    const result = await updateCredentials(formData.url.trim(), formData.password);
    if (result) {
      setSuccess(true);
      setIsEditing(false);
      // Clear form
      setFormData({ url: '', password: '' });
    }
  };

  const handleStartEditing = () => {
    setIsEditing(true);
    setFormData({
      url: credentials?.url ?? '',
      password: ''
    });
    setSuccess(false);
  };

  const handleCancelEditing = () => {
    setIsEditing(false);
    setFormData({ url: '', password: '' });
    setLocalError(null);
    clearError();
  };

  const displayError = localError ?? error;

  // If credentials are configured and not editing, show view mode
  if (isConfigured && !isEditing) {
    return (
      <div className='space-y-6'>
        {/* Header */}
        <div>
          <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
          <p className='mt-1 text-sm text-gray-500'>Your accounting service is configured.</p>
        </div>

        {/* Success Message */}
        <AnimatePresence>
          {success && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3'
            >
              <Check className='h-4 w-4 text-green-600' />
              <span className='text-sm text-green-800'>Credentials updated successfully!</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Credentials Display */}
        <div className='space-y-4' data-testid='credentials-view'>
          <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
            <CreditCard className='h-4 w-4 text-gray-500' />
            <h4 className='font-medium text-gray-900'>Accounting Service Credentials</h4>
          </div>

          {/* URL */}
          <div className='space-y-1'>
            <Label className='text-xs text-gray-500'>URL</Label>
            <div className='rounded-md bg-gray-50 px-3 py-2'>
              <span className='text-sm text-gray-900'>{credentials?.url}</span>
            </div>
          </div>

          {/* Email */}
          <div className='space-y-1'>
            <Label className='text-xs text-gray-500'>Email</Label>
            <div className='rounded-md bg-gray-50 px-3 py-2'>
              <span className='text-sm text-gray-900'>{credentials?.email}</span>
            </div>
            <p className='text-xs text-gray-500'>Same as your SyftHub account email</p>
          </div>

          {/* Password */}
          <div className='space-y-1'>
            <Label className='text-xs text-gray-500'>Password</Label>
            <div className='flex items-center gap-2 rounded-md bg-gray-50 px-3 py-2'>
              <span className='flex-1 text-sm text-gray-900'>
                {showCurrentPassword ? credentials?.password : '••••••••••••'}
              </span>
              <button
                type='button'
                onClick={() => {
                  setShowCurrentPassword(!showCurrentPassword);
                }}
                className='text-gray-400 hover:text-gray-600'
              >
                {showCurrentPassword ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
              </button>
            </div>
          </div>
        </div>

        {/* Edit Button */}
        <div className='flex justify-end border-t border-gray-200 pt-4'>
          <Button
            type='button'
            variant='outline'
            onClick={handleStartEditing}
            className='flex items-center gap-2'
          >
            Update Credentials
          </Button>
        </div>
      </div>
    );
  }

  // Setup or Edit form
  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>
          {isEditing
            ? 'Update your accounting service credentials.'
            : 'Configure your accounting service for payment processing.'}
        </p>
      </div>

      {/* Info Banner */}
      {!isEditing && (
        <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
          <div className='flex items-start gap-3'>
            <CreditCard className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600' />
            <div>
              <h4 className='text-sm font-medium text-blue-900'>Secure Storage</h4>
              <p className='mt-1 text-xs text-blue-700'>
                Your accounting credentials are stored securely on our servers. Your email from
                SyftHub will be used to authenticate with the accounting service.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Messages */}
      <AnimatePresence>
        {displayError && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{displayError}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Setup/Edit Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
          <CreditCard className='h-4 w-4 text-gray-500' />
          <h4 className='font-medium text-gray-900'>Accounting Service</h4>
        </div>

        {/* URL */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-url'>Accounting URL</Label>
          <Input
            id='accounting-url'
            type='url'
            value={formData.url}
            onChange={handleInputChange('url')}
            placeholder='https://accounting.example.com'
            disabled={isLoading}
            data-testid='accounting-url'
          />
          <p className='text-xs text-gray-500'>The base URL of your accounting service API</p>
        </div>

        {/* Email (read-only info) */}
        {credentials?.email && (
          <div className='space-y-2'>
            <Label>Email</Label>
            <div className='rounded-md bg-gray-50 px-3 py-2'>
              <span className='text-sm text-gray-600'>{credentials.email}</span>
            </div>
            <p className='text-xs text-gray-500'>
              Your SyftHub email will be used for accounting service authentication
            </p>
          </div>
        )}

        {/* Password */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-password'>{isEditing ? 'New Password' : 'Password'}</Label>
          <div className='relative'>
            <Input
              id='accounting-password'
              type={showPassword ? 'text' : 'password'}
              value={formData.password}
              onChange={handleInputChange('password')}
              placeholder='Your accounting service password'
              disabled={isLoading}
              className='pr-10'
              data-testid='accounting-password'
            />
            <button
              type='button'
              onClick={() => {
                setShowPassword(!showPassword);
              }}
              className='absolute top-1/2 right-3 -translate-y-1/2 text-gray-400 hover:text-gray-600'
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
            </button>
          </div>
        </div>

        {/* Submit Buttons */}
        <div className='flex items-center justify-end gap-2 pt-2'>
          {isEditing && (
            <Button type='button' variant='outline' onClick={handleCancelEditing}>
              Cancel
            </Button>
          )}
          <Button
            type='submit'
            disabled={isLoading || !formData.url || !formData.password}
            className='flex items-center gap-2'
            data-testid='save-credentials'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Saving...
              </>
            ) : (
              <>
                <Save className='h-4 w-4' />
                {isEditing ? 'Update Credentials' : 'Save Credentials'}
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
