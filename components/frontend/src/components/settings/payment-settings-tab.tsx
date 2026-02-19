/**
 * Payment Settings Tab
 *
 * Allows users to configure their accounting service credentials.
 * Credentials are stored securely in the SyftHub backend.
 */

import React, { useCallback, useState } from 'react';

import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Eye from 'lucide-react/dist/esm/icons/eye';
import EyeOff from 'lucide-react/dist/esm/icons/eye-off';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Save from 'lucide-react/dist/esm/icons/save';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAccounting } from '@/hooks/use-accounting';

import { StatusMessage } from './status-message';

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
          <h3 className='text-foreground text-lg font-semibold'>Payment Settings</h3>
          <p className='text-muted-foreground mt-1 text-sm'>
            Your accounting service is configured.
          </p>
        </div>

        {/* Success Message */}
        <StatusMessage
          type='success'
          message={success ? 'Credentials updated successfully!' : null}
        />

        {/* Credentials Display */}
        <div className='space-y-4' data-testid='credentials-view'>
          <div className='border-border flex items-center gap-2 border-t pt-4'>
            <CreditCard className='text-muted-foreground h-4 w-4' />
            <h4 className='text-foreground font-medium'>Accounting Service Credentials</h4>
          </div>

          {/* URL */}
          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>URL</Label>
            <div className='bg-muted rounded-md px-3 py-2'>
              <span className='text-foreground text-sm'>{credentials?.url}</span>
            </div>
          </div>

          {/* Email */}
          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>Email</Label>
            <div className='bg-muted rounded-md px-3 py-2'>
              <span className='text-foreground text-sm'>{credentials?.email}</span>
            </div>
            <p className='text-muted-foreground text-xs'>Same as your SyftHub account email</p>
          </div>

          {/* Password */}
          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>Password</Label>
            <div className='bg-muted flex items-center gap-2 rounded-md px-3 py-2'>
              <span className='text-foreground flex-1 text-sm'>
                {showCurrentPassword
                  ? credentials?.password
                  : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
              </span>
              <button
                type='button'
                onClick={() => {
                  setShowCurrentPassword(!showCurrentPassword);
                }}
                className='text-muted-foreground hover:text-foreground'
                aria-label={showCurrentPassword ? 'Hide password' : 'Show password'}
              >
                {showCurrentPassword ? (
                  <EyeOff className='h-4 w-4' aria-hidden='true' />
                ) : (
                  <Eye className='h-4 w-4' aria-hidden='true' />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Edit Button */}
        <div className='border-border flex justify-end border-t pt-4'>
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
        <h3 className='text-foreground text-lg font-semibold'>Payment Settings</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          {isEditing
            ? 'Update your accounting service credentials.'
            : 'Configure your accounting service for payment processing.'}
        </p>
      </div>

      {/* Info Banner */}
      {isEditing ? null : (
        <div className='rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950'>
          <div className='flex items-start gap-3'>
            <CreditCard className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600 dark:text-blue-400' />
            <div>
              <h4 className='text-sm font-medium text-blue-900 dark:text-blue-100'>
                Secure Storage
              </h4>
              <p className='mt-1 text-xs text-blue-700 dark:text-blue-300'>
                Your accounting credentials are stored securely on our servers. Your email from
                SyftHub will be used to authenticate with the accounting service.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Messages */}
      <StatusMessage type='error' message={displayError} />

      {/* Setup/Edit Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='border-border flex items-center gap-2 border-t pt-4'>
          <CreditCard className='text-muted-foreground h-4 w-4' />
          <h4 className='text-foreground font-medium'>Accounting Service</h4>
        </div>

        {/* URL */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-url'>Accounting URL</Label>
          <Input
            id='accounting-url'
            name='accounting_url'
            type='url'
            value={formData.url}
            onChange={handleInputChange('url')}
            placeholder='https://accounting.example.com…'
            autoComplete='url'
            disabled={isLoading}
            data-testid='accounting-url'
          />
          <p className='text-muted-foreground text-xs'>
            The base URL of your accounting service API
          </p>
        </div>

        {/* Email (read-only info) */}
        {credentials?.email ? (
          <div className='space-y-2'>
            <Label>Email</Label>
            <div className='bg-muted rounded-md px-3 py-2'>
              <span className='text-muted-foreground text-sm'>{credentials.email}</span>
            </div>
            <p className='text-muted-foreground text-xs'>
              Your SyftHub email will be used for accounting service authentication
            </p>
          </div>
        ) : null}

        {/* Password - uses Input's built-in password toggle */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-password'>{isEditing ? 'New Password' : 'Password'}</Label>
          <Input
            id='accounting-password'
            name='accounting_password'
            type='password'
            value={formData.password}
            onChange={handleInputChange('password')}
            placeholder='Your accounting service password…'
            autoComplete='current-password'
            disabled={isLoading}
            data-testid='accounting-password'
          />
        </div>

        {/* Submit Buttons */}
        <div className='border-border flex items-center justify-end gap-3 border-t pt-4'>
          {isEditing ? (
            <Button type='button' variant='outline' onClick={handleCancelEditing}>
              Cancel
            </Button>
          ) : null}
          <Button
            type='submit'
            disabled={isLoading || !formData.url || !formData.password}
            className='flex items-center gap-2'
            data-testid='save-credentials'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Saving…
              </>
            ) : (
              <>
                <Save className='h-4 w-4' aria-hidden='true' />
                {isEditing ? 'Update Credentials' : 'Save Credentials'}
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
