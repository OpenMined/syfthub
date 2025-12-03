/**
 * Payment Settings Tab
 *
 * Allows users to configure their accounting service credentials.
 * Credentials are stored encrypted in the browser, never sent to servers.
 */

import React, { useCallback, useState } from 'react';

import type { AccountingCredentials } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  Check,
  CreditCard,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Lock,
  LockOpen,
  Shield,
  Trash2
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAccounting, useAccountingSupported } from '@/hooks/use-accounting';

// =============================================================================
// Types
// =============================================================================

interface SetupFormData {
  url: string;
  email: string;
  password: string;
  pin: string;
  confirmPin: string;
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

function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Email is required';
  // Basic email validation - checking for @ and . characters
  // eslint-disable-next-line sonarjs/slow-regex -- Standard email validation pattern
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return 'Please enter a valid email address';
  }
  return null;
}

function validatePin(pin: string): string | null {
  if (!pin) return 'PIN is required';
  if (pin.length < 6) return 'PIN must be at least 6 characters';
  return null;
}

// =============================================================================
// VaultSetupForm
// =============================================================================

function VaultSetupForm() {
  const { createVault, error, clearError, isLoading } = useAccounting();

  const [formData, setFormData] = useState<SetupFormData>({
    url: '',
    email: '',
    password: '',
    pin: '',
    confirmPin: ''
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleInputChange = useCallback(
    (field: keyof SetupFormData) => (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData((previous) => ({ ...previous, [field]: e.target.value }));
      setLocalError(null);
      clearError();
    },
    [clearError]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    // Validate all fields
    const urlError = validateUrl(formData.url);
    if (urlError) {
      setLocalError(urlError);
      return;
    }

    const emailError = validateEmail(formData.email);
    if (emailError) {
      setLocalError(emailError);
      return;
    }

    if (!formData.password.trim()) {
      setLocalError('Password is required');
      return;
    }

    const pinError = validatePin(formData.pin);
    if (pinError) {
      setLocalError(pinError);
      return;
    }

    if (formData.pin !== formData.confirmPin) {
      setLocalError('PINs do not match');
      return;
    }

    const credentials: AccountingCredentials = {
      url: formData.url.trim(),
      email: formData.email.trim(),
      password: formData.password
    };

    const result = await createVault(credentials, formData.pin);
    if (result) {
      setSuccess(true);
    }
  };

  const displayError = localError || error?.message;

  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>
          Configure your accounting service for payment processing.
        </p>
      </div>

      {/* Security Info */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
        <div className='flex items-start gap-3'>
          <Shield className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600' />
          <div>
            <h4 className='text-sm font-medium text-blue-900'>Local Storage Only</h4>
            <p className='mt-1 text-xs text-blue-700'>
              Your credentials are encrypted and stored only in your browser. They are{' '}
              <strong>never</strong> sent to SyftHub servers. Remember your PIN - it cannot be
              recovered!
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
            <span className='text-sm text-green-800'>
              Payment credentials saved and encrypted successfully!
            </span>
          </motion.div>
        )}

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

      {/* Setup Form */}
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

        {/* Email */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-email'>Email</Label>
          <Input
            id='accounting-email'
            type='email'
            value={formData.email}
            onChange={handleInputChange('email')}
            placeholder='your-email@example.com'
            disabled={isLoading}
            data-testid='accounting-email'
          />
        </div>

        {/* Password */}
        <div className='space-y-2'>
          <Label htmlFor='accounting-password'>Password</Label>
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

        {/* PIN Section */}
        <div className='flex items-center gap-2 border-b border-gray-200 pt-4 pb-3'>
          <KeyRound className='h-4 w-4 text-gray-500' />
          <h4 className='font-medium text-gray-900'>Vault PIN</h4>
        </div>

        {/* PIN */}
        <div className='space-y-2'>
          <Label htmlFor='vault-pin'>PIN (6+ characters)</Label>
          <div className='relative'>
            <Input
              id='vault-pin'
              type={showPin ? 'text' : 'password'}
              value={formData.pin}
              onChange={handleInputChange('pin')}
              placeholder='Enter a secure PIN'
              disabled={isLoading}
              className='pr-10'
              data-testid='vault-pin'
            />
            <button
              type='button'
              onClick={() => {
                setShowPin(!showPin);
              }}
              className='absolute top-1/2 right-3 -translate-y-1/2 text-gray-400 hover:text-gray-600'
              tabIndex={-1}
            >
              {showPin ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
            </button>
          </div>
          <p className='text-xs text-gray-500'>
            This PIN encrypts your credentials. You&apos;ll need it to unlock your vault.
          </p>
        </div>

        {/* Confirm PIN */}
        <div className='space-y-2'>
          <Label htmlFor='vault-pin-confirm'>Confirm PIN</Label>
          <Input
            id='vault-pin-confirm'
            type='password'
            value={formData.confirmPin}
            onChange={handleInputChange('confirmPin')}
            placeholder='Confirm your PIN'
            disabled={isLoading}
            data-testid='vault-pin-confirm'
          />
          {formData.confirmPin && formData.pin !== formData.confirmPin && (
            <p className='text-xs text-red-600'>PINs do not match</p>
          )}
          {formData.confirmPin &&
            formData.pin === formData.confirmPin &&
            formData.pin.length >= 6 && <p className='text-xs text-green-600'>PINs match</p>}
        </div>

        {/* Submit Button */}
        <div className='flex justify-end pt-2'>
          <Button
            type='submit'
            disabled={
              isLoading ||
              !formData.url ||
              !formData.email ||
              !formData.password ||
              !formData.pin ||
              formData.pin !== formData.confirmPin
            }
            className='flex items-center gap-2'
            data-testid='save-vault'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Encrypting...
              </>
            ) : (
              <>
                <Lock className='h-4 w-4' />
                Save & Encrypt
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}

// =============================================================================
// VaultUnlockForm
// =============================================================================

function VaultUnlockForm() {
  const { unlock, deleteVault, error, clearError, isLoading, waitTime } = useAccounting();

  const [pin, setPin] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handlePinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPin(e.target.value);
    setLocalError(null);
    clearError();
  };

  const handleUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    if (!pin) {
      setLocalError('Please enter your PIN');
      return;
    }

    await unlock(pin);
  };

  const handleDelete = () => {
    deleteVault();
    setShowDeleteConfirm(false);
  };

  const displayError = localError || error?.message;
  const isRateLimited = waitTime > 0;

  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>
          Unlock your vault to access payment credentials.
        </p>
      </div>

      {/* Locked State Banner */}
      <div className='rounded-lg border border-amber-200 bg-amber-50 p-4'>
        <div className='flex items-start gap-3'>
          <Lock className='mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600' />
          <div>
            <h4 className='text-sm font-medium text-amber-900'>Vault Locked</h4>
            <p className='mt-1 text-xs text-amber-700'>
              Your payment credentials are encrypted. Enter your PIN to unlock.
            </p>
          </div>
        </div>
      </div>

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

        {isRateLimited && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-amber-600' />
            <span className='text-sm text-amber-800'>
              Too many attempts. Please wait {waitTime} second{waitTime === 1 ? '' : 's'}.
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Unlock Form */}
      <form onSubmit={handleUnlock} className='space-y-5'>
        <div className='space-y-2'>
          <Label htmlFor='unlock-pin'>Enter PIN</Label>
          <Input
            id='unlock-pin'
            type='password'
            value={pin}
            onChange={handlePinChange}
            placeholder='Enter your vault PIN'
            disabled={isLoading || isRateLimited}
            autoFocus
            data-testid='pin-input'
          />
        </div>

        <div className='flex items-center justify-between'>
          <Button
            type='button'
            variant='ghost'
            size='sm'
            onClick={() => {
              setShowDeleteConfirm(true);
            }}
            className='text-red-600 hover:bg-red-50 hover:text-red-700'
          >
            <Trash2 className='mr-1 h-4 w-4' />
            Delete Vault
          </Button>

          <Button
            type='submit'
            disabled={isLoading || !pin || isRateLimited}
            className='flex items-center gap-2'
          >
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Unlocking...
              </>
            ) : (
              <>
                <LockOpen className='h-4 w-4' />
                Unlock
              </>
            )}
          </Button>
        </div>
      </form>

      {/* Delete Confirmation */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='rounded-lg border border-red-200 bg-red-50 p-4'
          >
            <h4 className='text-sm font-medium text-red-900'>Delete Vault?</h4>
            <p className='mt-1 text-xs text-red-700'>
              This will permanently delete your encrypted credentials. You will need to set them up
              again.
            </p>
            <div className='mt-3 flex gap-2'>
              <Button
                size='sm'
                variant='outline'
                onClick={() => {
                  setShowDeleteConfirm(false);
                }}
              >
                Cancel
              </Button>
              <Button
                size='sm'
                variant='destructive'
                onClick={handleDelete}
                className='bg-red-600 hover:bg-red-700'
              >
                Delete
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// =============================================================================
// VaultUnlockedView
// =============================================================================

function VaultUnlockedView() {
  const { credentials, lock, deleteVault } = useAccounting();

  const [showPassword, setShowPassword] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleDelete = () => {
    deleteVault();
    setShowDeleteConfirm(false);
  };

  if (!credentials) {
    return null;
  }

  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>Your accounting service is configured.</p>
      </div>

      {/* Unlocked State Banner */}
      <div
        className='rounded-lg border border-green-200 bg-green-50 p-4'
        data-testid='vault-unlocked'
      >
        <div className='flex items-start gap-3'>
          <LockOpen className='mt-0.5 h-5 w-5 flex-shrink-0 text-green-600' />
          <div>
            <h4 className='text-sm font-medium text-green-900'>Vault Unlocked</h4>
            <p className='mt-1 text-xs text-green-700'>
              Your credentials are available for this session. They will be locked when you close
              this tab or log out.
            </p>
          </div>
        </div>
      </div>

      {/* Credentials Display */}
      <div className='space-y-4'>
        <div className='flex items-center gap-2 border-b border-gray-200 pb-3'>
          <CreditCard className='h-4 w-4 text-gray-500' />
          <h4 className='font-medium text-gray-900'>Accounting Service Credentials</h4>
        </div>

        {/* URL */}
        <div className='space-y-1'>
          <Label className='text-xs text-gray-500'>URL</Label>
          <div className='rounded-md bg-gray-50 px-3 py-2'>
            <span className='text-sm text-gray-900'>{credentials.url}</span>
          </div>
        </div>

        {/* Email */}
        <div className='space-y-1'>
          <Label className='text-xs text-gray-500'>Email</Label>
          <div className='rounded-md bg-gray-50 px-3 py-2'>
            <span className='text-sm text-gray-900'>{credentials.email}</span>
          </div>
        </div>

        {/* Password */}
        <div className='space-y-1'>
          <Label className='text-xs text-gray-500'>Password</Label>
          <div className='flex items-center gap-2 rounded-md bg-gray-50 px-3 py-2'>
            <span className='flex-1 text-sm text-gray-900'>
              {showPassword ? credentials.password : '••••••••••••'}
            </span>
            <button
              type='button'
              onClick={() => {
                setShowPassword(!showPassword);
              }}
              className='text-gray-400 hover:text-gray-600'
            >
              {showPassword ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
            </button>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className='flex items-center justify-between border-t border-gray-200 pt-4'>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          onClick={() => {
            setShowDeleteConfirm(true);
          }}
          className='text-red-600 hover:bg-red-50 hover:text-red-700'
        >
          <Trash2 className='mr-1 h-4 w-4' />
          Delete Vault
        </Button>

        <Button type='button' variant='outline' onClick={lock} className='flex items-center gap-2'>
          <Lock className='h-4 w-4' />
          Lock Now
        </Button>
      </div>

      {/* Delete Confirmation */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='rounded-lg border border-red-200 bg-red-50 p-4'
          >
            <h4 className='text-sm font-medium text-red-900'>Delete Vault?</h4>
            <p className='mt-1 text-xs text-red-700'>
              This will permanently delete your encrypted credentials. You will need to set them up
              again.
            </p>
            <div className='mt-3 flex gap-2'>
              <Button
                size='sm'
                variant='outline'
                onClick={() => {
                  setShowDeleteConfirm(false);
                }}
              >
                Cancel
              </Button>
              <Button
                size='sm'
                variant='destructive'
                onClick={handleDelete}
                className='bg-red-600 hover:bg-red-700'
              >
                Delete
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// =============================================================================
// CryptoNotSupported
// =============================================================================

function CryptoNotSupported() {
  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-gray-900'>Payment Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>Configure your accounting service.</p>
      </div>

      <div className='rounded-lg border border-red-200 bg-red-50 p-4'>
        <div className='flex items-start gap-3'>
          <AlertCircle className='mt-0.5 h-5 w-5 flex-shrink-0 text-red-600' />
          <div>
            <h4 className='text-sm font-medium text-red-900'>Browser Not Supported</h4>
            <p className='mt-1 text-xs text-red-700'>
              Your browser does not support the Web Crypto API, which is required for secure
              credential storage. Please use a modern browser like Chrome, Firefox, Safari, or Edge.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function PaymentSettingsTab() {
  const { status } = useAccounting();
  const isSupported = useAccountingSupported();

  // Check browser support first
  if (!isSupported) {
    return <CryptoNotSupported />;
  }

  // Render based on vault status
  if (status.isEmpty) {
    return <VaultSetupForm />;
  }

  if (status.isLocked) {
    return <VaultUnlockForm />;
  }

  if (status.isUnlocked) {
    return <VaultUnlockedView />;
  }

  // Fallback (should not happen)
  return <VaultSetupForm />;
}
