import React, { useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, AlertTriangle, Loader2, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { useSettingsModal } from '@/context/settings-modal-context';
import { deleteUserAccountAPI } from '@/lib/real-auth-api';

export function DangerZoneTab() {
  const { user, logout } = useAuth();
  const { closeSettings } = useSettingsModal();
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

  const handleCancelDelete = () => {
    setShowConfirmation(false);
    setConfirmText('');
    setError(null);
  };

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-red-600'>Danger Zone</h3>
        <p className='mt-1 text-sm text-gray-500'>
          Irreversible and destructive actions for your account.
        </p>
      </div>

      {/* Warning Banner */}
      <div className='rounded-lg border border-red-200 bg-red-50 p-4'>
        <div className='flex items-start gap-3'>
          <AlertTriangle className='mt-0.5 h-5 w-5 text-red-600' />
          <div>
            <h4 className='text-sm font-medium text-red-900'>Proceed with caution</h4>
            <p className='mt-1 text-xs text-red-700'>
              Actions in this section can permanently affect your account. Make sure you understand
              the consequences before proceeding.
            </p>
          </div>
        </div>
      </div>

      {/* Delete Account Section */}
      <div className='rounded-lg border border-red-300 p-4'>
        <div className='flex items-start justify-between gap-4'>
          <div className='flex-1'>
            <h4 className='font-medium text-gray-900'>Delete Account</h4>
            <p className='mt-1 text-sm text-gray-500'>
              Permanently delete your account and all associated data. This action cannot be undone.
            </p>
            <ul className='mt-2 text-xs text-gray-500'>
              <li>• All your endpoints will be deleted</li>
              <li>• Your organization memberships will be removed</li>
              <li>• Your profile information will be permanently erased</li>
            </ul>
          </div>
          {!showConfirmation && (
            <Button
              variant='outline'
              className='border-red-300 text-red-600 hover:bg-red-50 hover:text-red-700'
              onClick={() => {
                setShowConfirmation(true);
              }}
            >
              <Trash2 className='mr-2 h-4 w-4' />
              Delete Account
            </Button>
          )}
        </div>

        {/* Confirmation Form */}
        <AnimatePresence>
          {showConfirmation && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className='mt-4 overflow-hidden'
            >
              <div className='space-y-4 border-t border-red-200 pt-4'>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
                  >
                    <AlertCircle className='h-4 w-4 text-red-600' />
                    <span className='text-sm text-red-800'>{error}</span>
                  </motion.div>
                )}

                <div className='rounded-lg bg-red-100 p-3'>
                  <p className='text-sm font-medium text-red-800'>
                    This action is <strong>permanent</strong> and cannot be reversed.
                  </p>
                </div>

                <div className='space-y-2'>
                  <Label htmlFor='confirm-delete' className='text-red-700'>
                    Type <strong className='font-mono'>{expectedConfirmText}</strong> to confirm
                  </Label>
                  <Input
                    id='confirm-delete'
                    value={confirmText}
                    onChange={(e) => {
                      setConfirmText(e.target.value);
                      setError(null);
                    }}
                    placeholder={expectedConfirmText}
                    disabled={isLoading}
                    className='border-red-300 focus:border-red-500 focus:ring-red-500'
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
                        Deleting...
                      </>
                    ) : (
                      <>
                        <Trash2 className='h-4 w-4' />
                        Permanently Delete Account
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
