import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';

import { cn } from '@/lib/utils';

/**
 * Currency conversion constants.
 *
 * The Unified Global Ledger uses CREDITS as the smallest unit:
 * - 1 USD = 1000 CREDITS (allows $0.001 precision for micropayments)
 * - This differs from cents (1 USD = 100 cents)
 *
 * All balance values from the API are in CREDITS.
 */
const CREDITS_PER_DOLLAR = 1000;

/**
 * Convert balance from credits to dollars.
 * The Unified Global Ledger stores balance in CREDITS (1 USD = 1000 CREDITS).
 */
function creditsToDollars(credits: number): number {
  return credits / CREDITS_PER_DOLLAR;
}

/**
 * Format balance for display.
 * Converts from credits to dollars and shows 2-3 decimal places with $ prefix.
 * Uses 3 decimal places to support sub-cent precision when needed.
 */
export function formatBalance(balanceInCredits: number): string {
  const dollars = creditsToDollars(balanceInCredits);
  // Use 3 decimal places if there are sub-cent amounts, otherwise 2
  const hasSubCentPrecision = balanceInCredits % 10 !== 0;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: hasSubCentPrecision ? 3 : 2
  }).format(dollars);
}

/**
 * Format balance compactly for the pill display.
 * Shows K/M suffix for large numbers, with $ prefix.
 */
export function formatBalanceCompact(balanceInCredits: number): string {
  const dollars = creditsToDollars(balanceInCredits);
  if (dollars >= 1_000_000) {
    return `$${(dollars / 1_000_000).toFixed(1)}M`;
  }
  if (dollars >= 10_000) {
    return `$${(dollars / 1000).toFixed(1)}K`;
  }
  if (dollars >= 1000) {
    return `$${(dollars / 1000).toFixed(2)}K`;
  }
  return formatBalance(balanceInCredits);
}

/**
 * Get balance status based on amount (in credits).
 * - empty: $0 or negative
 * - low: under $10 (10,000 credits)
 * - healthy: $10 or more
 */
export function getBalanceStatus(balanceInCredits: number): 'healthy' | 'low' | 'empty' {
  if (balanceInCredits <= 0) return 'empty';
  if (balanceInCredits < 10_000) return 'low'; // $10.00 = 10,000 credits
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
