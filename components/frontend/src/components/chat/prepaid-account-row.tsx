/**
 * PrepaidAccountRow
 *
 * One publisher prepaid-wallet row: shows the buyer's account status with a
 * publisher (active balance vs. "needs settlement"), a bundle picker, and a
 * Buy / Initiate-invoice button that opens the publisher checkout in a popup.
 *
 * Extracted from the chat PaymentGate so the same mechanism + UI can back both
 * the chat gate and the collective "Check my accounts" modal. Balance polling
 * and active-state detection live in the parent (the chat gate polls per
 * wallet; the collective modal does the same), so this row is presentational
 * apart from the buy handler.
 */
import { useEffect, useState } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import Clock from 'lucide-react/dist/esm/icons/clock';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import X from 'lucide-react/dist/esm/icons/x';

import { BundlePicker } from '@/components/endpoint/bundle-picker';
import { cn } from '@/lib/utils';
import {
  createInvoice,
  getSatelliteToken,
  openCheckoutWindow,
  UNIT_LABEL
} from '@/lib/xendit-client';

type PurchaseState =
  | { state: 'idle' }
  | { state: 'creating' }
  | { state: 'awaiting'; checkoutUrl: string }
  | { state: 'error'; message: string };

function renderStatusLine(pending: PendingSubscription, isActive: boolean, liveBalance: number) {
  if (isActive) {
    return (
      <span className='inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400'>
        <CheckCircle2 className='h-3 w-3' />
        <span className='tabular-nums'>
          {pending.currency} {liveBalance.toLocaleString()} remaining
        </span>
      </span>
    );
  }
  if (pending.pricePerUnit === null) {
    return <>Prepaid credits required</>;
  }
  return (
    <span className='tabular-nums'>
      {pending.currency} {pending.pricePerUnit.toLocaleString()} per{' '}
      {UNIT_LABEL[pending.unit].singular}
    </span>
  );
}

export interface PrepaidAccountRowProps {
  pending: PendingSubscription;
  liveBalance: number;
  isActive: boolean;
  /** When provided, renders an × that removes the row from a selection (chat). */
  onRemove?: () => void;
  /**
   * Primary label. Defaults to the representative endpoint path (chat gate);
   * the collective modal passes the publisher's username (settlement is
   * per-user, and one wallet covers all that owner's endpoints).
   */
  label?: string;
  /** Secondary label. Defaults to the endpoint role ("Model" / "Data source"). */
  sublabel?: string;
}

export function PrepaidAccountRow({
  pending,
  liveBalance,
  isActive,
  onRemove,
  label,
  sublabel
}: Readonly<PrepaidAccountRowProps>) {
  const [purchase, setPurchase] = useState<PurchaseState>({ state: 'idle' });
  const [selectedBundleName, setSelectedBundleName] = useState<string>(
    () => pending.bundles[0]?.name ?? ''
  );

  // Once the wallet flips active the awaiting/creating chrome would just
  // confuse the user, so reset it.
  useEffect(() => {
    if (isActive && purchase.state !== 'idle') {
      setPurchase({ state: 'idle' });
    }
  }, [isActive, purchase.state]);

  const selectedBundle =
    pending.bundles.find((b) => b.name === selectedBundleName) ?? pending.bundles[0];

  const primaryEndpoint = pending.endpoints[0];
  const primaryLabel = label ?? primaryEndpoint?.path ?? 'Unknown endpoint';
  const secondaryLabel = sublabel ?? (primaryEndpoint?.role === 'model' ? 'Model' : 'Data source');

  const handleBuy = async () => {
    if (!selectedBundle || !primaryEndpoint) return;
    setPurchase({ state: 'creating' });
    const token = await getSatelliteToken(primaryEndpoint.owner);
    if (!token) {
      setPurchase({
        state: 'error',
        message: 'Could not authenticate with the endpoint operator.'
      });
      return;
    }
    const result = await createInvoice(
      pending.paymentUrl,
      token,
      selectedBundle.name,
      primaryEndpoint.slug
    );
    if ('error' in result) {
      setPurchase({ state: 'error', message: result.error });
      return;
    }
    setPurchase({ state: 'awaiting', checkoutUrl: result.checkoutUrl });
    openCheckoutWindow(result.checkoutUrl);
  };

  const isBusy = purchase.state === 'creating';
  const isAwaiting = purchase.state === 'awaiting';

  let buttonContent: React.ReactNode;
  if (isBusy) {
    buttonContent = (
      <>
        <Loader2 className='h-3 w-3 animate-spin' />
        Opening…
      </>
    );
  } else if (isAwaiting) {
    buttonContent = (
      <>
        <Clock className='h-3 w-3' />
        Reopen
      </>
    );
  } else {
    buttonContent = (
      <>
        Buy
        <ArrowRight className='h-3 w-3 transition-transform group-hover:translate-x-0.5' />
      </>
    );
  }

  return (
    <div
      className={cn(
        'rounded-md border bg-white px-3 py-2.5 transition-colors',
        'dark:bg-card',
        isActive
          ? 'border-emerald-200 dark:border-emerald-900/50'
          : 'border-amber-200/60 dark:border-amber-900/40'
      )}
    >
      <div className='flex flex-wrap items-center justify-between gap-x-3 gap-y-2'>
        {/* Left: icon + endpoint/owner + status */}
        <div className='flex min-w-0 flex-1 items-center gap-2.5'>
          <div
            className={cn(
              'flex h-7 w-7 shrink-0 items-center justify-center rounded-md border',
              isActive
                ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-400'
                : 'border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-400'
            )}
          >
            <CreditCard className='h-3.5 w-3.5' />
          </div>
          <div className='min-w-0'>
            <div className='flex items-center gap-1.5'>
              <span className='text-foreground truncate text-sm font-medium'>{primaryLabel}</span>
              <span className='text-muted-foreground text-[11px]'>· {secondaryLabel}</span>
            </div>
            <div className='text-muted-foreground mt-0.5 text-[11px]'>
              {renderStatusLine(pending, isActive, liveBalance)}
            </div>
          </div>
        </div>

        {/* Right: actions */}
        <div className='flex shrink-0 items-center gap-1.5'>
          {!isActive && pending.bundles.length > 0 && selectedBundle && (
            <>
              <BundlePicker
                bundles={pending.bundles}
                currency={pending.currency}
                value={selectedBundleName}
                onChange={setSelectedBundleName}
                disabled={isBusy}
                triggerClassName='h-8 min-w-[7rem]'
                pricePerUnit={pending.pricePerUnit}
                unit={pending.unit}
              />
              <button
                type='button'
                disabled={isBusy}
                onClick={() => void handleBuy()}
                className={cn(
                  'group inline-flex h-8 items-center justify-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors',
                  'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
                  isBusy
                    ? 'cursor-not-allowed opacity-50'
                    : 'cursor-pointer hover:bg-violet-100 dark:hover:bg-violet-900/40'
                )}
              >
                {buttonContent}
              </button>
            </>
          )}
          {onRemove && (
            <button
              type='button'
              onClick={onRemove}
              aria-label='Remove from selection'
              title='Remove from selection'
              className={cn(
                'text-muted-foreground hover:text-foreground rounded-md p-1 transition-colors',
                'hover:bg-muted/60 focus:ring-ring/30 focus:ring-2 focus:outline-none'
              )}
            >
              <X className='h-3.5 w-3.5' />
            </button>
          )}
        </div>
      </div>

      {purchase.state === 'awaiting' && !isActive && (
        <div className='mt-2 text-[11px] text-amber-700 dark:text-amber-400'>
          Complete payment in the popup window. We'll detect it automatically.
        </div>
      )}

      {purchase.state === 'error' && (
        <div className='mt-2 rounded-md border border-red-200 bg-red-50/70 px-2 py-1 text-[11px] text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300'>
          {purchase.message}
        </div>
      )}
    </div>
  );
}
