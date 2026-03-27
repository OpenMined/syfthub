/**
 * Wallet Settings Tab
 *
 * Allows users to create or import their wallet.
 * Wallet data is stored in the SyftHub backend.
 */

import React, { useCallback, useState } from 'react';

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Wallet from 'lucide-react/dist/esm/icons/wallet';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useWallet } from '@/hooks/use-wallet';
import { WalletAPIClient } from '@/hooks/use-wallet-api';

import { StatusMessage } from './status-message';

// =============================================================================
// Helpers
// =============================================================================

/** Truncate an Ethereum address for display */
function truncateAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

// =============================================================================
// View Modes
// =============================================================================

type ViewMode = 'view' | 'create' | 'import';

// =============================================================================
// Main Component
// =============================================================================

export function PaymentSettingsTab() {
  const {
    wallet,
    isConfigured,
    isLoading: isContextLoading,
    error: contextError,
    clearError,
    fetchWallet
  } = useWallet();

  const [viewMode, setViewMode] = useState<ViewMode>(isConfigured ? 'view' : 'create');
  const [privateKey, setPrivateKey] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const resetForm = useCallback(() => {
    setPrivateKey('');
    setLocalError(null);
    setSuccess(null);
    clearError();
  }, [clearError]);

  // Create a new wallet
  const handleCreateWallet = useCallback(async () => {
    setIsSubmitting(true);
    setLocalError(null);
    setSuccess(null);
    clearError();

    try {
      const client = new WalletAPIClient();
      const result = await client.createWallet();
      setSuccess(`Wallet created successfully! Address: ${result.address}`);
      await fetchWallet();
      setViewMode('view');
    } catch (error_) {
      setLocalError(error_ instanceof Error ? error_.message : 'Failed to create wallet');
    } finally {
      setIsSubmitting(false);
    }
  }, [clearError, fetchWallet]);

  // Import wallet via private key
  const handleImportWallet = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!privateKey.trim()) {
        setLocalError('Private key is required');
        return;
      }

      const trimmedKey = privateKey.trim();
      // Strip optional 0x prefix for validation
      const hexKey = trimmedKey.startsWith('0x') ? trimmedKey.slice(2) : trimmedKey;
      if (!/^[0-9a-fA-F]{64}$/.test(hexKey)) {
        setLocalError('Private key must be 64 hex characters (with optional 0x prefix)');
        return;
      }

      setIsSubmitting(true);
      setLocalError(null);
      setSuccess(null);
      clearError();

      try {
        const client = new WalletAPIClient();
        const result = await client.importWallet(privateKey.trim());
        setSuccess(`Wallet imported successfully! Address: ${result.address}`);
        setPrivateKey('');
        await fetchWallet();
        setViewMode('view');
      } catch (error_) {
        setLocalError(error_ instanceof Error ? error_.message : 'Failed to import wallet');
      } finally {
        setIsSubmitting(false);
      }
    },
    [privateKey, clearError, fetchWallet]
  );

  const displayError = localError ?? contextError;
  const isLoading = isContextLoading || isSubmitting;

  // -------------------------------------------------------------------------
  // View: Configured wallet
  // -------------------------------------------------------------------------
  if (isConfigured && viewMode === 'view') {
    return (
      <div className='space-y-6'>
        <div>
          <h3 className='text-foreground text-lg font-semibold'>Wallet Settings</h3>
          <p className='text-muted-foreground mt-1 text-sm'>Your wallet is configured.</p>
        </div>

        <StatusMessage type='success' message={success} />

        <div className='space-y-4' data-testid='wallet-view'>
          <div className='border-border flex items-center gap-2 border-t pt-4'>
            <Wallet className='text-muted-foreground h-4 w-4' />
            <h4 className='text-foreground font-medium'>Wallet Address</h4>
          </div>

          <div className='space-y-1'>
            <Label className='text-muted-foreground text-xs'>Address</Label>
            <div className='bg-muted rounded-md px-3 py-2'>
              <span className='text-foreground font-mono text-sm'>
                {wallet?.address ? truncateAddress(wallet.address) : 'N/A'}
              </span>
            </div>
            {wallet?.address ? (
              <p className='text-muted-foreground text-xs'>Full: {wallet.address}</p>
            ) : null}
          </div>
        </div>

        <div className='border-border flex justify-end gap-3 border-t pt-4'>
          <Button
            type='button'
            variant='outline'
            onClick={() => {
              resetForm();
              setViewMode('import');
            }}
            className='flex items-center gap-2'
          >
            Import Different Wallet
          </Button>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // View: Import wallet via private key
  // -------------------------------------------------------------------------
  if (viewMode === 'import') {
    return (
      <div className='space-y-6'>
        <div>
          <h3 className='text-foreground text-lg font-semibold'>Import Wallet</h3>
          <p className='text-muted-foreground mt-1 text-sm'>
            Import an existing wallet by entering your private key.
          </p>
        </div>

        <StatusMessage type='error' message={displayError} />

        <form onSubmit={handleImportWallet} className='space-y-5'>
          <div className='space-y-2'>
            <Label htmlFor='private-key'>Private Key</Label>
            <Input
              id='private-key'
              name='private_key'
              type='password'
              value={privateKey}
              onChange={(e) => {
                setPrivateKey(e.target.value);
                setLocalError(null);
              }}
              placeholder='Enter your private key...'
              disabled={isLoading}
              data-testid='wallet-private-key'
            />
            <p className='text-muted-foreground text-xs'>
              Your private key will be transmitted securely to the server.
            </p>
          </div>

          <div className='border-border flex items-center justify-end gap-3 border-t pt-4'>
            <Button
              type='button'
              variant='outline'
              onClick={() => {
                resetForm();
                setViewMode(isConfigured ? 'view' : 'create');
              }}
            >
              Cancel
            </Button>
            <Button
              type='submit'
              disabled={isLoading || !privateKey.trim()}
              className='flex items-center gap-2'
            >
              {isSubmitting ? (
                <>
                  <Loader2 className='h-4 w-4 animate-spin' />
                  Importing...
                </>
              ) : (
                'Import Wallet'
              )}
            </Button>
          </div>
        </form>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // View: No wallet — setup prompt
  // -------------------------------------------------------------------------
  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-foreground text-lg font-semibold'>Wallet Settings</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Set up your wallet for payment processing.
        </p>
      </div>

      {/* Info Banner */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950'>
        <div className='flex items-start gap-3'>
          <Wallet className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600 dark:text-blue-400' />
          <div>
            <h4 className='text-sm font-medium text-blue-900 dark:text-blue-100'>Tempo Wallet</h4>
            <p className='mt-1 text-xs text-blue-700 dark:text-blue-300'>
              Create a new wallet or import an existing one to enable payments for API usage across
              the network.
            </p>
          </div>
        </div>
      </div>

      <StatusMessage type='error' message={displayError} />
      <StatusMessage type='success' message={success} />

      <div className='space-y-4'>
        <Button
          onClick={() => void handleCreateWallet()}
          disabled={isLoading}
          className='flex w-full items-center justify-center gap-2'
          data-testid='create-wallet-btn'
        >
          {isSubmitting ? (
            <>
              <Loader2 className='h-4 w-4 animate-spin' />
              Creating Wallet...
            </>
          ) : (
            <>
              <Plus className='h-4 w-4' aria-hidden='true' />
              Create Wallet
            </>
          )}
        </Button>

        <div className='text-center'>
          <button
            type='button'
            onClick={() => {
              resetForm();
              setViewMode('import');
            }}
            className='text-muted-foreground hover:text-foreground text-sm underline'
            disabled={isLoading}
          >
            I already have a wallet
          </button>
        </div>
      </div>
    </div>
  );
}
