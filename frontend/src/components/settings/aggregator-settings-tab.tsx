/**
 * Aggregator Settings Tab
 *
 * Allows users to configure a custom aggregator URL for RAG/chat workflows.
 * If not configured, the default aggregator is used.
 */

import React, { useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Save from 'lucide-react/dist/esm/icons/save';
import Server from 'lucide-react/dist/esm/icons/server';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { syftClient } from '@/lib/sdk-client';

// =============================================================================
// Validation
// =============================================================================

function validateUrl(url: string): string | null {
  if (!url.trim()) return null; // Empty is valid (means use default)
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return 'URL must use http:// or https://';
    }
    return null;
  } catch {
    return 'Please enter a valid URL (e.g., https://aggregator.example.com)';
  }
}

// =============================================================================
// Main Component
// =============================================================================

export function AggregatorSettingsTab() {
  const { user, updateUser } = useAuth();

  const [formUrl, setFormUrl] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const currentUrl = user?.aggregator_url;
  const isConfigured = Boolean(currentUrl);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setFormUrl(e.target.value);
    setLocalError(null);
    setSuccess(false);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    setSuccess(false);

    // Validate URL (empty is allowed - means clear/use default)
    const trimmedUrl = formUrl.trim();
    if (trimmedUrl) {
      const urlError = validateUrl(trimmedUrl);
      if (urlError) {
        setLocalError(urlError);
        return;
      }
    }

    setIsLoading(true);

    try {
      // Get token from SDK client
      const tokens = syftClient.getTokens();
      const accessToken = tokens?.accessToken ?? '';

      const response = await fetch('/api/v1/users/me', {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          aggregator_url: trimmedUrl || null // null to clear
        })
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to update aggregator settings');
      }

      const updatedUser = (await response.json()) as { aggregator_url?: string | null };

      // Update local user state
      if (updateUser && user) {
        updateUser({
          ...user,
          aggregator_url: updatedUser.aggregator_url ?? undefined
        });
      }

      setSuccess(true);
      setIsEditing(false);
      setFormUrl('');
    } catch (error_) {
      setLocalError(error_ instanceof Error ? error_.message : 'An unknown error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = async () => {
    setLocalError(null);
    setSuccess(false);
    setIsLoading(true);

    try {
      const tokens = syftClient.getTokens();
      const accessToken = tokens?.accessToken ?? '';

      const response = await fetch('/api/v1/users/me', {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          aggregator_url: null
        })
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to clear aggregator settings');
      }

      // Update local user state
      if (updateUser && user) {
        updateUser({
          ...user,
          aggregator_url: undefined
        });
      }

      setSuccess(true);
    } catch (error_) {
      setLocalError(error_ instanceof Error ? error_.message : 'An unknown error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartEditing = () => {
    setIsEditing(true);
    setFormUrl(currentUrl ?? '');
    setSuccess(false);
  };

  const handleCancelEditing = () => {
    setIsEditing(false);
    setFormUrl('');
    setLocalError(null);
  };

  // If configured and not editing, show view mode
  if (isConfigured && !isEditing) {
    return (
      <div className='space-y-6'>
        {/* Header */}
        <div>
          <h3 className='text-lg font-semibold text-gray-900'>Aggregator Settings</h3>
          <p className='mt-1 text-sm text-gray-500'>
            You have a custom aggregator configured for chat operations.
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
              <span className='text-sm text-green-800'>Settings updated successfully!</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Error Message */}
        <AnimatePresence>
          {localError ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
            >
              <AlertCircle className='h-4 w-4 text-red-600' />
              <span className='text-sm text-red-800'>{localError}</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Current Configuration Display */}
        <div className='space-y-4' data-testid='aggregator-view'>
          <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
            <Server className='h-4 w-4 text-gray-500' />
            <h4 className='font-medium text-gray-900'>Custom Aggregator</h4>
          </div>

          {/* URL */}
          <div className='space-y-1'>
            <Label className='text-xs text-gray-500'>Aggregator URL</Label>
            <div className='rounded-md bg-gray-50 px-3 py-2'>
              <span className='text-sm break-all text-gray-900'>{currentUrl}</span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className='flex items-center justify-between border-t border-gray-200 pt-4'>
          <Button
            type='button'
            variant='outline'
            onClick={handleClear}
            disabled={isLoading}
            className='flex items-center gap-2 text-red-600 hover:bg-red-50 hover:text-red-700'
          >
            {isLoading ? (
              <Loader2 className='h-4 w-4 animate-spin' />
            ) : (
              <Trash2 className='h-4 w-4' />
            )}
            Use Default
          </Button>
          <Button
            type='button'
            variant='outline'
            onClick={handleStartEditing}
            className='flex items-center gap-2'
          >
            Update URL
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
        <h3 className='text-lg font-semibold text-gray-900'>Aggregator Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>
          {isEditing
            ? 'Update your custom aggregator URL.'
            : 'Configure a custom aggregator for chat operations.'}
        </p>
      </div>

      {/* Info Banner */}
      {isEditing ? null : (
        <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
          <div className='flex items-start gap-3'>
            <Server className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600' />
            <div>
              <h4 className='text-sm font-medium text-blue-900'>Optional Configuration</h4>
              <p className='mt-1 text-xs text-blue-700'>
                By default, SyftHub uses its built-in aggregator for chat operations. You can
                configure a custom aggregator if you want to use your own RAG orchestration service.
              </p>
            </div>
          </div>
        </div>
      )}

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
            <span className='text-sm text-green-800'>Settings updated successfully!</span>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Error Message */}
      <AnimatePresence>
        {localError ? (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{localError}</span>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Setup/Edit Form */}
      <form onSubmit={handleSubmit} className='space-y-5'>
        <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
          <Server className='h-4 w-4 text-gray-500' />
          <h4 className='font-medium text-gray-900'>Aggregator Service</h4>
        </div>

        {/* URL */}
        <div className='space-y-2'>
          <Label htmlFor='aggregator-url'>Aggregator URL</Label>
          <Input
            id='aggregator-url'
            name='aggregator_url'
            type='url'
            value={formUrl}
            onChange={handleInputChange}
            placeholder='https://aggregator.example.com/api/v1'
            autoComplete='url'
            disabled={isLoading}
            data-testid='aggregator-url'
          />
          <p className='text-xs text-gray-500'>
            The base URL of your aggregator service API. Leave empty to use the default.
          </p>
        </div>

        {/* Warning */}
        <div className='rounded-lg border border-amber-200 bg-amber-50 p-3'>
          <div className='flex items-start gap-2'>
            <AlertCircle className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600' />
            <p className='text-xs text-amber-800'>
              Using a custom aggregator means your chat queries will be sent to that service. Make
              sure you trust the aggregator you configure.
            </p>
          </div>
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
            disabled={isLoading}
            className='flex items-center gap-2'
            data-testid='save-aggregator'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Saving…
              </>
            ) : (
              <>
                <Save className='h-4 w-4' aria-hidden='true' />
                {isEditing ? 'Update URL' : 'Save Settings'}
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
