import React, { useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { deleteUserAccountAPI } from '@/lib/sdk-client';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import { StatusMessage } from './status-message';

export function DangerZoneTab() {
  const { user, logout } = useAuth();
  const { closeSettings } = useSettingsModalStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const expectedConfirmText = user?.username ?? 'delete';

  const handleDeleteAccount = async () => {
    if (confirmText !== expectedConfirmText) {
      setError(`Please type "${expectedConfirmText}" to confirm deletion`);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await deleteUserAccountAPI();

      // Close modal and logout
      closeSettings();
      await logout();
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to delete account');
      setIsLoading(false);
    }
  };

  // Memoized handlers for stable references
  const handleCancelDelete = useCallback(() => {
    setShowConfirmation(false);
    setConfirmText('');
    setError(null);
  }, []);

  const handleConfirmTextChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setConfirmText(e.target.value);
    setError(null);
  }, []);

  const handleShowConfirmation = useCallback(() => {
    setShowConfirmation(true);
  }, []);

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-destructive text-lg font-semibold'>Danger Zone</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Irreversible and destructive actions for your account.
        </p>
      </div>

      {/* Warning Banner */}
      <div className='rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950'>
        <div className='flex items-start gap-3'>
          <AlertTriangle className='mt-0.5 h-5 w-5 text-red-600 dark:text-red-400' />
          <div>
            <h4 className='text-sm font-medium text-red-900 dark:text-red-100'>
              Proceed with caution
            </h4>
            <p className='mt-1 text-xs text-red-700 dark:text-red-300'>
              Actions in this section can permanently affect your account. Make sure you understand
              the consequences before proceeding.
            </p>
          </div>
        </div>
      </div>

      {/* Delete Account Section */}
      <div className='rounded-lg border border-red-300 p-4 dark:border-red-700'>
        <div className='flex items-start justify-between gap-4'>
          <div className='flex-1'>
            <h4 className='text-foreground font-medium'>Delete Account</h4>
            <p className='text-muted-foreground mt-1 text-sm'>
              Permanently delete your account and all associated data. This action cannot be undone.
            </p>
            <ul className='text-muted-foreground mt-2 text-xs'>
              <li>All your endpoints will be deleted</li>
              <li>Your organization memberships will be removed</li>
              <li>Your profile information will be permanently erased</li>
            </ul>
          </div>
          {showConfirmation ? null : (
            <Button
              variant='outline'
              className='border-red-300 text-red-600 hover:bg-red-50 hover:text-red-700 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950 dark:hover:text-red-300'
              onClick={handleShowConfirmation}
            >
              <Trash2 className='mr-2 h-4 w-4' aria-hidden='true' />
              Delete Account
            </Button>
          )}
        </div>

        {/* Confirmation Form */}
        <AnimatePresence>
          {showConfirmation ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className='mt-4 overflow-hidden'
            >
              <div className='space-y-4 border-t border-red-200 pt-4 dark:border-red-800'>
                <StatusMessage type='error' message={error} />

                <div id='delete-warning' className='rounded-lg bg-red-100 p-3 dark:bg-red-900'>
                  <p className='text-sm font-medium text-red-800 dark:text-red-200'>
                    This action is <strong>permanent</strong> and cannot be reversed.
                  </p>
                </div>

                <div className='space-y-2'>
                  <Label htmlFor='confirm-delete' className='text-red-700 dark:text-red-400'>
                    Type <strong className='font-mono'>{expectedConfirmText}</strong> to confirm
                  </Label>
                  <Input
                    id='confirm-delete'
                    name='confirm_delete'
                    value={confirmText}
                    onChange={handleConfirmTextChange}
                    placeholder={expectedConfirmText}
                    autoComplete='off'
                    spellCheck={false}
                    disabled={isLoading}
                    className='border-red-300 focus:border-red-500 focus:ring-red-500'
                    aria-describedby='delete-warning'
                  />
                </div>

                <div className='flex justify-end gap-3'>
                  <Button
                    type='button'
                    variant='outline'
                    onClick={handleCancelDelete}
                    disabled={isLoading}
                  >
                    Cancel
                  </Button>
                  <Button
                    type='button'
                    variant='destructive'
                    onClick={handleDeleteAccount}
                    disabled={isLoading || confirmText !== expectedConfirmText}
                    className='flex items-center gap-2 bg-red-600 hover:bg-red-700'
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className='h-4 w-4 animate-spin' />
                        Deleting…
                      </>
                    ) : (
                      <>
                        <Trash2 className='h-4 w-4' aria-hidden='true' />
                        Permanently Delete Account
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
