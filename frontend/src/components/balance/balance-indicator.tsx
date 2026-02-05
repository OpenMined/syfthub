import { useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Coins from 'lucide-react/dist/esm/icons/coins';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import Settings from 'lucide-react/dist/esm/icons/settings';

import { OnboardingCallout } from '@/components/onboarding';
import { useAccountingContext } from '@/context/accounting-context';
import { useAccountingUser, useTransactions } from '@/hooks/use-accounting-api';
import { cn } from '@/lib/utils';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import {
  BalanceDisplay,
  formatBalance,
  getBalanceStatus,
  getDisplayText,
  statusColors,
  statusRingColors
} from './balance-display';
import { TransactionList } from './transaction-list';

/**
 * BalanceIndicator - Displays user's credits balance in a compact pill.
 *
 * Features:
 * - Shows balance with status indicator (green/yellow/red)
 * - Click to expand dropdown with details
 * - Shows recent transactions
 * - Links to payment settings
 */
export function BalanceIndicator() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);

  const { isConfigured, isLoading: isLoadingCredentials } = useAccountingContext();
  const { user, isLoading: isLoadingUser, error, refetch } = useAccountingUser();
  const {
    transactions,
    isLoading: isLoadingTransactions,
    refetch: refetchTransactions
  } = useTransactions({ pageSize: 5, autoFetch: isConfigured });
  const { openSettings } = useSettingsModalStore();

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownReference.current &&
        buttonReference.current &&
        !dropdownReference.current.contains(event.target as Node) &&
        !buttonReference.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  // Close on escape key
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.removeEventListener('keydown', handleEscape);
      };
    }
  }, [isOpen]);

  const handleRefresh = useCallback(async () => {
    await Promise.all([refetch(), refetchTransactions()]);
  }, [refetch, refetchTransactions]);

  const handleOpenSettings = useCallback(() => {
    setIsOpen(false);
    openSettings('payment');
  }, [openSettings]);

  const toggleOpen = useCallback(() => {
    setIsOpen((previous) => !previous);
  }, []);

  // Don't show if not authenticated or credentials are loading
  if (isLoadingCredentials) {
    return null;
  }

  // Show setup prompt if not configured
  if (!isConfigured) {
    return (
      <button
        onClick={handleOpenSettings}
        className={cn(
          'font-inter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors',
          'border-amber-200 bg-amber-50 text-amber-700',
          'hover:border-amber-300 hover:bg-amber-100'
        )}
      >
        <Coins className='h-3.5 w-3.5' aria-hidden='true' />
        <span>Set up billing</span>
      </button>
    );
  }

  const isLoading = isLoadingUser || isLoadingCredentials;
  const balance = user?.balance ?? 0;
  const status = getBalanceStatus(balance);

  // Get recent transactions (last 3)
  const recentTransactions = transactions.slice(0, 3);

  // Render status icon based on loading/error/success state
  const renderStatusIcon = () => {
    if (isLoading) {
      return <Loader2 className='text-muted-foreground h-3.5 w-3.5 animate-spin' />;
    }

    if (error) {
      return <AlertCircle className='h-3.5 w-3.5 text-red-500' />;
    }

    return (
      <div className='relative'>
        <div
          className={cn(
            'h-2 w-2 rounded-full',
            statusColors[status],
            status === 'empty' && 'animate-pulse'
          )}
        />
        <div
          className={cn('absolute inset-0 h-2 w-2 rounded-full ring-2', statusRingColors[status])}
        />
      </div>
    );
  };

  return (
    <OnboardingCallout step='balance' position='bottom'>
      <div className='relative'>
        {/* Balance Pill Button */}
        <button
          ref={buttonReference}
          onClick={toggleOpen}
          disabled={isLoading}
          className={cn(
            'font-inter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors transition-shadow',
            'border-border bg-muted',
            'hover:border-input hover:shadow-sm',
            'focus:ring-ring/20 focus:ring-2 focus:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50'
          )}
          aria-label={`Account balance: ${formatBalance(balance)} credits`}
          aria-expanded={isOpen}
          aria-haspopup='true'
        >
          {renderStatusIcon()}
          <span className='text-foreground font-medium tabular-nums'>
            {getDisplayText(isLoading, error, balance)}
          </span>
          <ChevronDown
            className={cn(
              'text-muted-foreground h-3 w-3 transition-transform',
              isOpen && 'rotate-180'
            )}
          />
        </button>

        {/* Dropdown */}
        <AnimatePresence>
          {isOpen ? (
            <motion.div
              ref={dropdownReference}
              initial={{ opacity: 0, y: -8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.96 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              className={cn(
                'absolute top-full right-0 z-50 mt-2 w-72',
                'bg-card border-border rounded-xl border shadow-lg'
              )}
            >
              {/* Header */}
              <div className='border-border border-b px-4 py-3'>
                <div className='flex items-center justify-between'>
                  <span className='font-inter text-muted-foreground text-xs font-medium tracking-wide uppercase'>
                    Available Credits
                  </span>
                  <button
                    onClick={() => void handleRefresh()}
                    disabled={isLoading}
                    className={cn(
                      'text-muted-foreground rounded-md p-1 transition-colors',
                      'hover:bg-muted hover:text-foreground',
                      'disabled:cursor-not-allowed disabled:opacity-50'
                    )}
                    aria-label='Refresh balance'
                  >
                    <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
                  </button>
                </div>

                <BalanceDisplay
                  isLoading={isLoading}
                  error={error}
                  balance={balance}
                  status={status}
                />
              </div>

              {/* Recent Transactions */}
              <div className='px-4 py-3'>
                <div className='mb-2 flex items-center justify-between'>
                  <span className='font-inter text-muted-foreground text-xs font-medium'>
                    Recent Activity
                  </span>
                </div>

                <TransactionList
                  isLoading={isLoadingTransactions}
                  transactions={recentTransactions}
                  userEmail={user?.email}
                />
              </div>

              {/* Footer Actions */}
              <div className='border-border border-t px-4 py-3'>
                <div className='flex gap-2'>
                  <button
                    onClick={handleOpenSettings}
                    className={cn(
                      'font-inter flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                      'bg-muted text-foreground',
                      'hover:bg-border'
                    )}
                  >
                    <Settings className='h-3.5 w-3.5' />
                    Settings
                  </button>
                  <button
                    onClick={handleOpenSettings}
                    className={cn(
                      'font-inter flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                      'bg-primary text-white',
                      'hover:bg-primary/90'
                    )}
                  >
                    <ExternalLink className='h-3.5 w-3.5' />
                    View All
                  </button>
                </div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </OnboardingCallout>
  );
}
