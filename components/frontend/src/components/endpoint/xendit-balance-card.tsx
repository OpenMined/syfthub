import { memo, useEffect } from 'react';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import Wallet from 'lucide-react/dist/esm/icons/wallet';

import { Button } from '@/components/ui/button';
import { useXenditBalance } from '@/hooks/use-xendit-balance';
import { cn } from '@/lib/utils';

export interface XenditBalanceCardProperties {
  spaceBaseUrl: string;
  ownerUsername: string;
  balancePath: string;
  /** Increment to trigger a balance refresh from outside (e.g. after purchase) */
  refreshTrigger?: number;
}

export const XenditBalanceCard = memo(function XenditBalanceCard({
  spaceBaseUrl,
  ownerUsername,
  balancePath,
  refreshTrigger
}: Readonly<XenditBalanceCardProperties>) {
  const { remaining, total, isLoading, error, refetch } = useXenditBalance(
    spaceBaseUrl,
    ownerUsername,
    balancePath
  );

  // Re-fetch when refreshTrigger changes (after a purchase)
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      void refetch();
    }
  }, [refreshTrigger, refetch]);

  const hasBalance = remaining !== null && total !== null;
  const percentage = hasBalance && total > 0 ? Math.round((remaining / total) * 100) : 0;
  const isLow = hasBalance && total > 0 && percentage <= 20;

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      {/* Header */}
      <div className='mb-4 flex items-center justify-between'>
        <h3 className='font-rubik text-foreground flex items-center gap-1.5 text-sm font-medium'>
          <Wallet className='h-4 w-4 text-teal-600 dark:text-teal-400' />
          Credits
        </h3>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground hover:text-foreground h-7 w-7 p-0'
          onClick={() => void refetch()}
          disabled={isLoading}
          title='Refresh balance'
        >
          <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
        </Button>
      </div>

      {/* Content */}
      {isLoading && !hasBalance ? (
        <div className='flex items-center justify-center py-4'>
          <Loader2 className='text-muted-foreground h-5 w-5 animate-spin' />
        </div>
      ) : error ? (
        <div className='flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400'>
          <AlertCircle className='h-3.5 w-3.5 shrink-0' />
          <span>{error}</span>
        </div>
      ) : hasBalance ? (
        <div className='space-y-3'>
          {/* Balance display */}
          <div className='text-center'>
            <span className='text-foreground text-2xl font-bold'>{remaining.toLocaleString()}</span>
            <span className='text-muted-foreground text-sm'> of {total.toLocaleString()}</span>
            <p className='text-muted-foreground mt-0.5 text-xs'>requests remaining</p>
          </div>

          {/* Progress bar */}
          <div className='bg-muted h-2 overflow-hidden rounded-full'>
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                isLow ? 'bg-red-500 dark:bg-red-400' : 'bg-teal-500 dark:bg-teal-400'
              )}
              style={{ width: `${Math.min(percentage, 100)}%` }}
            />
          </div>

          {/* Low balance warning */}
          {isLow ? (
            <p className='text-center text-[10px] text-red-600 dark:text-red-400'>
              Low balance — purchase more bundles below
            </p>
          ) : null}
        </div>
      ) : (
        <p className='text-muted-foreground text-center text-xs'>No balance data available</p>
      )}
    </div>
  );
});
