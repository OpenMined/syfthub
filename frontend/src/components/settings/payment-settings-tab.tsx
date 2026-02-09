/**
 * Payment Settings Tab
 *
 * Allows users to configure their Unified Global Ledger credentials.
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
  apiToken: string;
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
    return 'Please enter a valid URL (e.g., https://ledger.example.com)';
  }
}

function validateApiToken(token: string): string | null {
  if (!token.trim()) return 'API token is required';
  if (!token.startsWith('at_')) {
    return 'API token must start with "at_" prefix';
  }
  return null;
}

// =============================================================================
// Main Component
// =============================================================================

export function PaymentSettingsTab() {
  const { credentials, isConfigured, isLoading, error, clearError, updateCredentials } =
    useAccounting();

  const [formData, setFormData] = useState<FormData>({
    url: '',
    apiToken: ''
  });
  const [showToken, setShowToken] = useState(false);
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

    // Validate API token
    const tokenError = validateApiToken(formData.apiToken);
    if (tokenError) {
      setLocalError(tokenError);
      return;
    }

    const result = await updateCredentials(formData.url.trim(), formData.apiToken.trim());
    if (result) {
      setSuccess(true);
      setIsEditing(false);
      // Clear form
      setFormData({ url: '', apiToken: '' });
    }
  };

  const handleStartEditing = () => {
    setIsEditing(true);
    setFormData({
      url: credentials?.url ?? '',
      apiToken: ''
    });
    setSuccess(false);
  };

  const handleCancelEditing = () => {
    setIsEditing(false);
    setFormData({ url: '', apiToken: '' });
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
            Your Unified Global Ledger is configured.
          </p>
        </div>

        {/* Success Message */}
        <AnimatePresence>
          {success ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3'
            >
              <Check className='h-4 w-4 text-green-600' />
              <span className='text-sm text-green-800'>Credentials updated successfully!</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Credentials Display */}
        <div className='space-y-4' data-testid='credentials-view'>
          <div className='border-border flex items-center gap-2 border-b pb-3'>
            <CreditCard className='text-muted-foreground h-4 w-4' />
            <h4 className='text-foreground font-medium'>Ledger Configuration</h4>
          </div>

          {/* URL */}
          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>Ledger URL</Label>
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

          {/* Account ID */}
          {credentials?.account_id ? (
            <div className='space-y-1'>
              <Label className='text-muted-foreground text-xs'>Account ID</Label>
              <div className='bg-muted rounded-md px-3 py-2'>
                <span className='text-foreground font-mono text-sm'>{credentials.account_id}</span>
              </div>
            </div>
          ) : null}

          {/* API Token Status */}
          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>API Token</Label>
            <div className='bg-muted flex items-center gap-2 rounded-md px-3 py-2'>
              <span className='text-foreground flex-1 text-sm'>
                {credentials?.has_api_token ? (
                  <span className='flex items-center gap-2'>
                    <Check className='h-4 w-4 text-green-600' />
                    <span>Configured</span>
                  </span>
                ) : (
                  <span className='text-amber-600'>Not configured</span>
                )}
              </span>
            </div>
            <p className='text-muted-foreground text-xs'>
              API tokens are stored securely and never displayed
            </p>
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
            ? 'Update your Unified Global Ledger credentials.'
            : 'Configure your Unified Global Ledger for payment processing.'}
        </p>
      </div>

      {/* Info Banner */}
      {isEditing ? null : (
        <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
          <div className='flex items-start gap-3'>
            <CreditCard className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600' />
            <div>
              <h4 className='text-sm font-medium text-blue-900'>API Token Authentication</h4>
              <p className='mt-1 text-xs text-blue-700'>
                Generate an API token from your ledger account and enter it below. The token should
                start with &quot;at_&quot; and have the required scopes for your operations.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Messages */}
      <AnimatePresence>
        {displayError ? (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{displayError}</span>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Setup/Edit Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='border-border flex items-center gap-2 border-b pb-3'>
          <CreditCard className='text-muted-foreground h-4 w-4' />
          <h4 className='text-foreground font-medium'>Ledger Configuration</h4>
        </div>

        {/* URL */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-url'>Ledger URL</Label>
          <Input
            id='accounting-url'
            name='accounting_url'
            type='url'
            value={formData.url}
            onChange={handleInputChange('url')}
            placeholder='https://ledger.example.com…'
            autoComplete='url'
            disabled={isLoading}
            data-testid='accounting-url'
          />
          <p className='text-muted-foreground text-xs'>
            The base URL of your Unified Global Ledger API
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
              Your SyftHub email is linked to your ledger account
            </p>
          </div>
        ) : null}

        {/* API Token */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-token'>{isEditing ? 'New API Token' : 'API Token'}</Label>
          <div className='relative'>
            <Input
              id='accounting-token'
              name='accounting_api_token'
              type={showToken ? 'text' : 'password'}
              value={formData.apiToken}
              onChange={handleInputChange('apiToken')}
              placeholder='at_xxxxxxxx_...'
              autoComplete='off'
              disabled={isLoading}
              className='pr-10 font-mono'
              data-testid='accounting-token'
            />
            <button
              type='button'
              onClick={() => {
                setShowToken(!showToken);
              }}
              className='text-muted-foreground hover:text-muted-foreground absolute top-1/2 right-3 -translate-y-1/2'
              tabIndex={-1}
              aria-label={showToken ? 'Hide token' : 'Show token'}
            >
              {showToken ? (
                <EyeOff className='h-4 w-4' aria-hidden='true' />
              ) : (
                <Eye className='h-4 w-4' aria-hidden='true' />
              )}
            </button>
          </div>
          <p className='text-muted-foreground text-xs'>
            Generate an API token from your ledger dashboard with required scopes
          </p>
        </div>

        {/* Submit Buttons */}
        <div className='flex items-center justify-end gap-2 pt-2'>
          {isEditing ? (
            <Button type='button' variant='outline' onClick={handleCancelEditing}>
              Cancel
            </Button>
          ) : null}
          <Button
            type='submit'
            disabled={isLoading || !formData.url || !formData.apiToken}
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
