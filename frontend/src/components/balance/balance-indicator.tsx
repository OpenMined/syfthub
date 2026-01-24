import { useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import ArrowDownLeft from 'lucide-react/dist/esm/icons/arrow-down-left';
import ArrowUpRight from 'lucide-react/dist/esm/icons/arrow-up-right';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Coins from 'lucide-react/dist/esm/icons/coins';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import Settings from 'lucide-react/dist/esm/icons/settings';

import { useAccountingContext } from '@/context/accounting-context';
import { useSettingsModal } from '@/context/settings-modal-context';
import { useAccountingUser, useTransactions } from '@/hooks/use-accounting-api';
import { cn } from '@/lib/utils';

/**
 * Format balance for display.
 * Shows 2 decimal places, with thousands separator.
 */
function formatBalance(balance: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(balance);
}

/**
 * Format balance compactly for the pill display.
 * Shows K/M suffix for large numbers.
 */
function formatBalanceCompact(balance: number): string {
  if (balance >= 1_000_000) {
    return `${(balance / 1_000_000).toFixed(1)}M`;
  }
  if (balance >= 10_000) {
    return `${(balance / 1000).toFixed(1)}K`;
  }
  if (balance >= 1000) {
    return `${(balance / 1000).toFixed(2)}K`;
  }
  return formatBalance(balance);
}

/**
 * Get balance status based on amount.
 */
function getBalanceStatus(balance: number): 'healthy' | 'low' | 'empty' {
  if (balance <= 0) return 'empty';
  if (balance < 100) return 'low';
  return 'healthy';
}

/**
 * Get display text for balance pill.
 */
function getDisplayText(isLoading: boolean, error: string | null, balance: number): string {
  if (isLoading) return '…';
  if (error) return 'Error';
  return formatBalanceCompact(balance);
}

/**
 * Format relative time for transactions.
 */
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${String(diffMins)}m ago`;
  if (diffHours < 24) return `${String(diffHours)}h ago`;
  if (diffDays < 7) return `${String(diffDays)}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Truncate email for display.
 */
function truncateEmail(email: string | null | undefined, maxLength = 20): string {
  if (!email) return 'Unknown';
  if (email.length <= maxLength) return email;
  const atIndex = email.indexOf('@');
  if (atIndex === -1) return email.slice(0, maxLength) + '…';
  const local = email.slice(0, atIndex);
  const domain = email.slice(atIndex + 1);
  const availableLocal = maxLength - domain.length - 4; // 4 for "…@"
  if (availableLocal < 3) return email.slice(0, maxLength) + '…';
  return `${local.slice(0, availableLocal)}…@${domain}`;
}

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
  const { openSettings } = useSettingsModal();

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

  const statusColors = {
    healthy: 'bg-emerald-500',
    low: 'bg-amber-500',
    empty: 'bg-red-500'
  };

  const statusRingColors = {
    healthy: 'ring-emerald-500/20',
    low: 'ring-amber-500/20',
    empty: 'ring-red-500/20'
  };

  // Get recent transactions (last 3)
  const recentTransactions = transactions.slice(0, 3);

  // Render status icon based on loading/error/success state
  const renderStatusIcon = () => {
    if (isLoading) {
      return <Loader2 className='h-3.5 w-3.5 animate-spin text-[var(--syft-text-muted)]' />;
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

  // Render transactions list based on loading/empty/data state
  const renderTransactionsList = () => {
    if (isLoadingTransactions) {
      return (
        <div className='space-y-2'>
          {[0, 1, 2].map((index) => (
            <div key={index} className='flex animate-pulse items-center gap-3'>
              <div className='bg-muted h-6 w-6 rounded-full' />
              <div className='flex-1'>
                <div className='bg-muted h-3 w-24 rounded' />
                <div className='bg-muted mt-1 h-2 w-16 rounded' />
              </div>
              <div className='bg-muted h-3 w-12 rounded' />
            </div>
          ))}
        </div>
      );
    }

    if (recentTransactions.length === 0) {
      return (
        <div className='py-4 text-center text-xs text-[var(--syft-text-muted)]'>
          No recent transactions
        </div>
      );
    }

    return (
      <div className='space-y-2'>
        {recentTransactions.map((tx) => {
          const isIncoming = tx.recipientEmail === user?.email;
          const otherParty = isIncoming ? tx.senderEmail : tx.recipientEmail;

          return (
            <div key={tx.id} className='flex items-center gap-3'>
              <div
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full',
                  isIncoming ? 'bg-emerald-100' : 'bg-red-100'
                )}
              >
                {isIncoming ? (
                  <ArrowDownLeft className='h-3 w-3 text-emerald-600' />
                ) : (
                  <ArrowUpRight className='h-3 w-3 text-red-600' />
                )}
              </div>
              <div className='min-w-0 flex-1'>
                <div className='truncate text-xs font-medium text-[var(--syft-text)]'>
                  {isIncoming ? 'From ' : 'To '}
                  {truncateEmail(otherParty)}
                </div>
                <div className='text-[10px] text-[var(--syft-text-muted)]'>
                  {formatRelativeTime(tx.createdAt)}
                </div>
              </div>
              <div
                className={cn(
                  'text-xs font-medium',
                  isIncoming ? 'text-emerald-600' : 'text-red-600'
                )}
              >
                {isIncoming ? '+' : '-'}
                {formatBalance(tx.amount)}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className='relative'>
      {/* Balance Pill Button */}
      <button
        ref={buttonReference}
        onClick={toggleOpen}
        disabled={isLoading}
        className={cn(
          'font-inter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors transition-shadow',
          'border-[var(--syft-border)] bg-[var(--syft-surface)]',
          'hover:border-[var(--syft-border-light)] hover:shadow-sm',
          'focus:ring-2 focus:ring-[var(--syft-primary)]/20 focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50'
        )}
        aria-label={`Account balance: ${formatBalance(balance)} credits`}
        aria-expanded={isOpen}
        aria-haspopup='true'
      >
        {renderStatusIcon()}
        <span className='font-medium text-[var(--syft-text)] tabular-nums'>
          {getDisplayText(isLoading, error, balance)}
        </span>
        <ChevronDown
          className={cn(
            'h-3 w-3 text-[var(--syft-text-muted)] transition-transform',
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
              'bg-card rounded-xl border border-[var(--syft-border)] shadow-lg'
            )}
          >
            {/* Header */}
            <div className='border-b border-[var(--syft-border)] px-4 py-3'>
              <div className='flex items-center justify-between'>
                <span className='font-inter text-xs font-medium tracking-wide text-[var(--syft-text-muted)] uppercase'>
                  Available Credits
                </span>
                <button
                  onClick={() => void handleRefresh()}
                  disabled={isLoading}
                  className={cn(
                    'rounded-md p-1 text-[var(--syft-text-muted)] transition-colors',
                    'hover:bg-[var(--syft-surface)] hover:text-[var(--syft-text)]',
                    'disabled:cursor-not-allowed disabled:opacity-50'
                  )}
                  aria-label='Refresh balance'
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
                </button>
              </div>

              {/* Balance Display */}
              <div className='mt-2 flex items-baseline gap-2'>
                {error ? (
                  <div className='flex items-center gap-2 text-red-600'>
                    <AlertCircle className='h-4 w-4' aria-hidden='true' />
                    <span className='text-sm'>Failed to load balance</span>
                  </div>
                ) : (
                  <>
                    <div className='relative'>
                      <div
                        className={cn(
                          'h-2.5 w-2.5 rounded-full',
                          statusColors[status],
                          status === 'empty' && 'animate-pulse'
                        )}
                      />
                      <div
                        className={cn(
                          'absolute inset-0 h-2.5 w-2.5 rounded-full ring-2',
                          statusRingColors[status]
                        )}
                      />
                    </div>
                    <span className='font-rubik text-2xl font-semibold text-[var(--syft-text)] tabular-nums'>
                      {isLoading ? '---' : formatBalance(balance)}
                    </span>
                    <span className='text-sm text-[var(--syft-text-muted)]'>credits</span>
                  </>
                )}
              </div>

              {/* Low balance warning */}
              {!error && status !== 'healthy' ? (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className={cn(
                    'mt-3 rounded-lg px-3 py-2 text-xs',
                    status === 'low' && 'bg-amber-50 text-amber-700',
                    status === 'empty' && 'bg-red-50 text-red-700'
                  )}
                >
                  {status === 'empty'
                    ? 'Your balance is empty. Add credits to continue using services.'
                    : 'Your balance is running low. Consider adding more credits.'}
                </motion.div>
              ) : null}
            </div>

            {/* Recent Transactions */}
            <div className='px-4 py-3'>
              <div className='mb-2 flex items-center justify-between'>
                <span className='font-inter text-xs font-medium text-[var(--syft-text-muted)]'>
                  Recent Activity
                </span>
              </div>

              {renderTransactionsList()}
            </div>

            {/* Footer Actions */}
            <div className='border-t border-[var(--syft-border)] px-4 py-3'>
              <div className='flex gap-2'>
                <button
                  onClick={handleOpenSettings}
                  className={cn(
                    'font-inter flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                    'bg-[var(--syft-surface)] text-[var(--syft-text)]',
                    'hover:bg-[var(--syft-border)]'
                  )}
                >
                  <Settings className='h-3.5 w-3.5' />
                  Settings
                </button>
                <button
                  onClick={handleOpenSettings}
                  className={cn(
                    'font-inter flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                    'bg-[var(--syft-primary)] text-white',
                    'hover:bg-[var(--syft-primary)]/90'
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
  );
}
