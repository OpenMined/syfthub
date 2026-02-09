import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';

import { cn } from '@/lib/utils';

/**
 * Convert balance from cents to dollars.
 * The ledger stores balance in smallest currency unit (cents).
 */
function centsToDollars(cents: number): number {
  return cents / 100;
}

/**
 * Format balance for display.
 * Converts from cents to dollars and shows 2 decimal places with $ prefix.
 */
export function formatBalance(balanceInCents: number): string {
  const dollars = centsToDollars(balanceInCents);
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(dollars);
}

/**
 * Format balance compactly for the pill display.
 * Shows K/M suffix for large numbers, with $ prefix.
 */
export function formatBalanceCompact(balanceInCents: number): string {
  const dollars = centsToDollars(balanceInCents);
  if (dollars >= 1_000_000) {
    return `$${(dollars / 1_000_000).toFixed(1)}M`;
  }
  if (dollars >= 10_000) {
    return `$${(dollars / 1000).toFixed(1)}K`;
  }
  if (dollars >= 1000) {
    return `$${(dollars / 1000).toFixed(2)}K`;
  }
  return formatBalance(balanceInCents);
}

/**
 * Get balance status based on amount (in cents).
 * - empty: $0 or negative
 * - low: under $10
 * - healthy: $10 or more
 */
export function getBalanceStatus(balanceInCents: number): 'healthy' | 'low' | 'empty' {
  if (balanceInCents <= 0) return 'empty';
  if (balanceInCents < 1000) return 'low'; // $10.00
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
