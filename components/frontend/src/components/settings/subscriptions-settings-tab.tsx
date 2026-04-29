/**
 * Subscriptions settings tab — manages publisher (Xendit) wallets the user
 * has funded. Each row shows the live balance fetched from the publisher
 * with a satellite token, plus Top-up and Forget actions.
 */
import { useCallback, useState } from 'react';

import type { XenditSubscription } from '@/lib/types';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import { Link } from 'react-router-dom';

import { formatBalance } from '@/components/balance/balance-display';
import { Button } from '@/components/ui/button';
import {
  useDeleteXenditSubscription,
  useSubscriptionBalance,
  useXenditSubscriptions
} from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';
import { openCheckoutWindow } from '@/lib/xendit-client';

export function SubscriptionsSettingsTab() {
  const subscriptionsQuery = useXenditSubscriptions();
  const subscriptions = subscriptionsQuery.data ?? [];

  return (
    <div className='space-y-4'>
      <div>
        <h2 className='text-foreground text-lg font-semibold'>Endpoint subscriptions</h2>
        <p className='text-muted-foreground mt-1 text-sm'>
          Publisher-side wallets you've funded via Xendit. Balances are fetched live from each
          publisher.
        </p>
      </div>

      <div className='flex items-center justify-between'>
        <span className='text-muted-foreground text-xs'>
          {subscriptions.length} subscription{subscriptions.length === 1 ? '' : 's'}
        </span>
        <Button
          variant='ghost'
          size='sm'
          disabled={subscriptionsQuery.isFetching}
          onClick={() => void subscriptionsQuery.refetch()}
          className='gap-1.5'
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', subscriptionsQuery.isFetching && 'animate-spin')}
          />
          Refresh
        </Button>
      </div>

      {renderBody({
        isLoading: subscriptionsQuery.isLoading,
        error: subscriptionsQuery.error,
        subscriptions,
        onRetry: () => void subscriptionsQuery.refetch()
      })}
    </div>
  );
}

interface RenderBodyArguments {
  isLoading: boolean;
  error: Error | null;
  subscriptions: XenditSubscription[];
  onRetry: () => void;
}

function renderBody({ isLoading, error, subscriptions, onRetry }: RenderBodyArguments) {
  if (isLoading) {
    return (
      <div className='text-muted-foreground flex items-center gap-2 py-8 text-sm'>
        <Loader2 className='h-4 w-4 animate-spin' />
        Loading subscriptions…
      </div>
    );
  }
  if (error) return <ErrorState message={error.message} onRetry={onRetry} />;
  if (subscriptions.length === 0) return <EmptyState />;
  return (
    <div className='space-y-2'>
      {subscriptions.map((sub) => (
        <SubscriptionCard key={sub.id} subscription={sub} />
      ))}
    </div>
  );
}

// ── per-row card ───────────────────────────────────────────────────────────

function SubscriptionCard({ subscription }: Readonly<{ subscription: XenditSubscription }>) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const deleteMutation = useDeleteXenditSubscription();
  const { balance, isLoading, error, refetch } = useSubscriptionBalance(subscription, {
    enabled: true,
    pollIntervalMs: 30_000
  });

  const liveBalance = balance ?? subscription.last_known_balance ?? 0;
  const label = subscription.endpoint_slug
    ? `${subscription.endpoint_owner}/${subscription.endpoint_slug}`
    : subscription.endpoint_owner;
  const targetPath = subscription.endpoint_slug
    ? `/${subscription.endpoint_owner}/${subscription.endpoint_slug}`
    : `/${subscription.endpoint_owner}`;

  const handleTopUp = useCallback(() => {
    openCheckoutWindow(subscription.payment_url);
  }, [subscription.payment_url]);

  const handleForget = useCallback(async () => {
    await deleteMutation.mutateAsync(subscription.id);
  }, [deleteMutation, subscription.id]);

  return (
    <div
      className={cn(
        'rounded-lg border p-4',
        'border-border bg-card',
        'transition-shadow hover:shadow-sm'
      )}
    >
      <div className='flex items-start justify-between gap-3'>
        <div className='flex min-w-0 items-start gap-3'>
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
              'border-violet-200 bg-violet-100 text-violet-700',
              'dark:border-violet-900/60 dark:bg-violet-900/30 dark:text-violet-400'
            )}
          >
            <CreditCard className='h-4 w-4' />
          </div>
          <div className='min-w-0'>
            <Link
              to={targetPath}
              className='text-foreground inline-flex items-center gap-1 text-sm font-medium hover:underline'
            >
              {label}
              <ExternalLink className='h-3 w-3 opacity-60' />
            </Link>
            <div className='text-muted-foreground mt-0.5 text-xs'>
              Xendit · {subscription.currency}
              {subscription.first_funded_at && (
                <>
                  {' · '}
                  Active since {new Date(subscription.first_funded_at).toLocaleDateString()}
                </>
              )}
            </div>
          </div>
        </div>
        <div className='shrink-0 text-right'>
          <BalanceCell
            isLoading={isLoading && balance === null}
            error={error}
            liveBalance={liveBalance}
            currency={subscription.currency}
            isCached={subscription.last_checked_at !== null && balance === null}
            onRetry={() => void refetch()}
          />
        </div>
      </div>

      <div className='mt-3 flex items-center justify-end gap-2 border-t pt-3'>
        {isConfirmingDelete ? (
          <div className='flex w-full items-center justify-between gap-2'>
            <span className='text-muted-foreground text-xs'>
              Forget this subscription? You can re-add it by paying again.
            </span>
            <div className='flex shrink-0 gap-2'>
              <Button
                variant='ghost'
                size='sm'
                onClick={() => {
                  setIsConfirmingDelete(false);
                }}
                disabled={deleteMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant='destructive'
                size='sm'
                onClick={() => void handleForget()}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? (
                  <Loader2 className='h-3.5 w-3.5 animate-spin' />
                ) : (
                  'Forget'
                )}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <Button variant='ghost' size='sm' onClick={handleTopUp} className='gap-1.5'>
              <ExternalLink className='h-3.5 w-3.5' />
              Top up
            </Button>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setIsConfirmingDelete(true);
              }}
              className='text-muted-foreground hover:text-destructive gap-1.5'
            >
              <Trash2 className='h-3.5 w-3.5' />
              Forget
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

// ── balance cell ───────────────────────────────────────────────────────────

interface BalanceCellProperties {
  isLoading: boolean;
  error: Error | null;
  liveBalance: number;
  currency: string;
  isCached: boolean;
  onRetry: () => void;
}

function BalanceCell({
  isLoading,
  error,
  liveBalance,
  currency,
  isCached,
  onRetry
}: Readonly<BalanceCellProperties>) {
  if (isLoading) {
    return <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />;
  }
  if (error) {
    return (
      <button
        type='button'
        onClick={onRetry}
        className='inline-flex items-center gap-1 text-xs text-red-600 hover:underline dark:text-red-400'
      >
        <AlertCircle className='h-3 w-3' />
        Retry
      </button>
    );
  }
  return (
    <>
      <div className='text-foreground text-base font-semibold tabular-nums'>
        {formatBalance(liveBalance)}
      </div>
      <div className='text-muted-foreground text-[10px]'>
        {currency}
        {isCached && <> · cached</>}
      </div>
    </>
  );
}

// ── states ─────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className='border-border text-muted-foreground rounded-lg border border-dashed bg-transparent px-6 py-10 text-center text-sm'>
      <CreditCard className='mx-auto mb-2 h-6 w-6 opacity-40' />
      You haven't funded any endpoint subscriptions yet.
      <br />
      <span className='text-xs'>Pay for any Xendit-gated endpoint and it will appear here.</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: Readonly<{ message: string; onRetry: () => void }>) {
  return (
    <div className='rounded-lg border border-red-200 bg-red-50/60 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300'>
      <div className='flex items-start gap-2'>
        <AlertCircle className='mt-0.5 h-4 w-4 shrink-0' />
        <div className='min-w-0 flex-1'>
          <div className='font-medium'>Failed to load subscriptions</div>
          <div className='mt-0.5 text-xs opacity-80'>{message}</div>
          <Button variant='ghost' size='sm' onClick={onRetry} className='mt-2 gap-1.5'>
            <RefreshCw className='h-3.5 w-3.5' />
            Retry
          </Button>
        </div>
      </div>
    </div>
  );
}
