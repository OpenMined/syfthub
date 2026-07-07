import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';

import { cn } from '@/lib/utils';

/**
 * Format balance for display.
 * Shows 2 decimal places, with thousands separator.
 */
export function formatBalance(balance: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(balance);
}

/**
 * Format balance compactly for the pill display.
 * Shows K/M suffix for large numbers.
 */
export function formatBalanceCompact(balance: number): string {
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
export function getBalanceStatus(balance: number): 'healthy' | 'low' | 'empty' {
  if (balance <= 0) return 'empty';
  if (balance < 100) return 'low';
  return 'healthy';
}

/**
 * Get display text for balance pill.
 */
export function getDisplayText(isLoading: boolean, error: string | null, balance: number): string {
  if (isLoading) return '…';
  if (error) return 'Error';
  return formatBalanceCompact(balance);
}

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

export { statusColors, statusRingColors };

export interface BalanceDisplayProps {
  /** Whether the balance data is still loading */
  isLoading: boolean;
  /** Error message if balance fetch failed */
  error: string | null;
  /** Current balance amount */
  balance: number;
  /** Balance status derived from amount */
  status: 'healthy' | 'low' | 'empty';
}

/**
 * BalanceDisplay - Renders the balance amount, status indicator,
 * and low-balance warning inside the dropdown header.
 */
export function BalanceDisplay({
  isLoading,
  error,
  balance,
  status
}: Readonly<BalanceDisplayProps>) {
  return (
    <>
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
            <span className='font-rubik text-foreground text-2xl font-semibold tabular-nums'>
              {isLoading ? '---' : formatBalance(balance)}
            </span>
            <span className='text-muted-foreground text-sm'>credits</span>
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
    </>
  );
}
