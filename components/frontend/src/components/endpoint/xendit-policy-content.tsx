import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';

import { BundlePicker } from '@/components/endpoint/bundle-picker';
import { useRegisterOnFundingDetected } from '@/hooks/use-xendit-subscriptions';
import { syftClient } from '@/lib/sdk-client';
import { cn } from '@/lib/utils';
import {
  createInvoice,
  fetchBalance,
  getSatelliteToken,
  openCheckoutWindow,
  parseXenditConfig,
  POLL_INTERVAL_MS
} from '@/lib/xendit-client';

type SubscriptionState =
  | { state: 'loading' }
  | { state: 'active'; balance: number }
  | { state: 'inactive' };

type PurchaseState =
  | { state: 'idle' }
  | { state: 'creating'; bundleName: string }
  | { state: 'awaiting_payment'; bundleName: string; checkoutUrl: string }
  | { state: 'error'; message: string };

export interface XenditPolicyContentProperties {
  config: Record<string, unknown>;
  enabled: boolean;
  endpointSlug?: string;
  endpointOwner?: string;
}

export const XenditPolicyContent = memo(function XenditPolicyContent({
  config,
  enabled,
  endpointSlug,
  endpointOwner
}: Readonly<XenditPolicyContentProperties>) {
  // Re-parse only when config identity changes — otherwise the bundles array
  // would get a fresh reference each render and re-fire the validation effect.
  const parsed = useMemo(() => parseXenditConfig(config), [config]);
  const { bundles, currency, paymentUrl, creditsUrl } = parsed;

  const [subscription, setSubscription] = useState<SubscriptionState>({ state: 'loading' });
  const [purchase, setPurchase] = useState<PurchaseState>({ state: 'idle' });
  const [selectedBundleName, setSelectedBundleName] = useState<string>(
    () => bundles[0]?.name ?? ''
  );

  // Backend registration is best-effort + idempotent; ref-gate so we only
  // call it once per (component instance, wallet) for the lifetime of the
  // page. The server upsert covers cross-page re-funding.
  const registerOnFunding = useRegisterOnFundingDetected();
  const hasRegisteredReference = useRef(false);

  useEffect(() => {
    const first = bundles[0];
    if (!first) return;
    if (!bundles.some((b) => b.name === selectedBundleName)) {
      setSelectedBundleName(first.name);
    }
  }, [bundles, selectedBundleName]);

  // Shared balance check. `silent=true` skips the loading transition for
  // background polling. Updates state only when something actually changed,
  // so unchanged poll ticks don't trigger re-renders downstream.
  const checkBalance = useCallback(
    async (options: { silent?: boolean; signal?: AbortSignal } = {}) => {
      const tokens = syftClient.getTokens();
      if (!tokens || !creditsUrl || !endpointOwner) {
        setSubscription((previous) =>
          previous.state === 'inactive' ? previous : { state: 'inactive' }
        );
        return;
      }
      if (!options.silent) setSubscription({ state: 'loading' });
      const satelliteToken = await getSatelliteToken(endpointOwner);
      if (options.signal?.aborted) return;
      if (!satelliteToken) {
        setSubscription((previous) =>
          previous.state === 'inactive' ? previous : { state: 'inactive' }
        );
        return;
      }
      const balance = await fetchBalance(creditsUrl, satelliteToken, options.signal);
      if (options.signal?.aborted) return;
      if (balance === null || balance <= 0) {
        if (!options.silent) {
          setSubscription((previous) =>
            previous.state === 'inactive' ? previous : { state: 'inactive' }
          );
        }
        return;
      }
      setSubscription((previous) =>
        previous.state === 'active' && previous.balance === balance
          ? previous
          : { state: 'active', balance }
      );
      setPurchase((previous) => (previous.state === 'idle' ? previous : { state: 'idle' }));

      // Active wallet detected — record it on the user's account so the
      // unified credits panel can list it. Idempotent server-side.
      if (!hasRegisteredReference.current && paymentUrl && endpointOwner && creditsUrl) {
        hasRegisteredReference.current = true;
        void registerOnFunding({
          creditsUrl,
          paymentUrl,
          endpointOwner,
          endpointSlug: endpointSlug ?? null,
          currency,
          lastKnownBalance: balance
        });
      }
    },
    [creditsUrl, endpointOwner, paymentUrl, endpointSlug, currency, registerOnFunding]
  );

  const refreshBalance = useCallback(() => checkBalance(), [checkBalance]);

  // Initial balance load. The same `checkBalance` powers refresh and polling,
  // and aborts cleanly on unmount.
  useEffect(() => {
    const controller = new AbortController();
    void checkBalance({ signal: controller.signal });
    return () => {
      controller.abort();
    };
  }, [checkBalance]);

  // Background polling while the user completes payment in the popup. The
  // active-state branch in checkBalance auto-clears purchase to idle, which
  // tears this interval down — so the loop self-terminates on success.
  useEffect(() => {
    if (purchase.state !== 'awaiting_payment') return;
    const controller = new AbortController();
    const intervalId = setInterval(() => {
      void checkBalance({ silent: true, signal: controller.signal });
    }, POLL_INTERVAL_MS);
    return () => {
      clearInterval(intervalId);
      controller.abort();
    };
  }, [purchase.state, checkBalance]);

  const handleSubscribe = async (bundleName: string) => {
    if (!paymentUrl || !enabled) return;
    const tokens = syftClient.getTokens();
    if (!tokens) {
      setPurchase({ state: 'error', message: 'Sign in to subscribe.' });
      return;
    }
    if (!endpointOwner) {
      setPurchase({
        state: 'error',
        message: 'Endpoint owner unknown — cannot mint satellite token.'
      });
      return;
    }
    setPurchase({ state: 'creating', bundleName });
    const satelliteToken = await getSatelliteToken(endpointOwner);
    if (!satelliteToken) {
      setPurchase({ state: 'error', message: 'Failed to get satellite token from SyftHub.' });
      return;
    }
    const result = await createInvoice(paymentUrl, satelliteToken, bundleName, endpointSlug);
    if ('error' in result) {
      setPurchase({ state: 'error', message: result.error });
      return;
    }
    setPurchase({ state: 'awaiting_payment', bundleName, checkoutUrl: result.checkoutUrl });
    openCheckoutWindow(result.checkoutUrl);
  };

  const canPurchase = Boolean(paymentUrl && enabled);
  const isCreatingAny = purchase.state === 'creating';

  return (
    <div className='mt-3 space-y-2'>
      {subscription.state === 'loading' && (
        <div className='text-muted-foreground flex items-center gap-1.5 text-xs'>
          <Loader2 className='h-3 w-3 animate-spin' />
          Checking subscription…
        </div>
      )}

      {subscription.state === 'active' && (
        <div className='flex items-center justify-between gap-2 rounded-md border border-emerald-200 bg-emerald-50/70 px-2.5 py-1.5 dark:border-emerald-900/60 dark:bg-emerald-950/20'>
          <div className='flex min-w-0 items-center gap-1.5'>
            <CheckCircle2 className='h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400' />
            <span className='truncate text-[11px] font-medium text-emerald-700 dark:text-emerald-400'>
              Active
              <span className='mx-1 text-emerald-600/50 dark:text-emerald-500/50'>·</span>
              <span className='tabular-nums'>
                {currency} {subscription.balance.toLocaleString()}
              </span>
              <span className='ml-1 text-emerald-600/70 dark:text-emerald-500/70'>remaining</span>
            </span>
          </div>
          <button
            type='button'
            onClick={() => void refreshBalance()}
            className='shrink-0 rounded p-0.5 text-emerald-600/70 transition-colors hover:bg-emerald-100/60 hover:text-emerald-700 dark:text-emerald-500/70 dark:hover:bg-emerald-900/30 dark:hover:text-emerald-400'
            aria-label='Refresh balance'
          >
            <RefreshCw className='h-3 w-3' />
          </button>
        </div>
      )}

      {subscription.state === 'inactive' &&
        purchase.state !== 'awaiting_payment' &&
        bundles.length > 0 && (
          <div className='space-y-1.5'>
            <BundlePicker
              bundles={bundles}
              currency={currency}
              value={selectedBundleName}
              onChange={setSelectedBundleName}
              disabled={isCreatingAny}
            />
            <button
              type='button'
              disabled={!canPurchase || isCreatingAny}
              onClick={() => void handleSubscribe(selectedBundleName)}
              className={cn(
                'group inline-flex h-8 w-full items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors',
                'border border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
                !canPurchase || isCreatingAny
                  ? 'cursor-not-allowed opacity-50'
                  : 'cursor-pointer hover:bg-violet-100 dark:hover:bg-violet-900/40'
              )}
            >
              {isCreatingAny ? (
                <>
                  <Loader2 className='h-3 w-3 animate-spin' />
                  Opening checkout…
                </>
              ) : (
                <>
                  Buy
                  <ArrowRight className='h-3 w-3 transition-transform group-hover:translate-x-0.5' />
                </>
              )}
            </button>
          </div>
        )}

      {purchase.state === 'error' && (
        <div className='rounded-md border border-red-200 bg-red-50/70 px-2.5 py-1.5 text-[11px] text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300'>
          {purchase.message}
        </div>
      )}

      {purchase.state === 'awaiting_payment' && subscription.state !== 'active' && (
        <AwaitingPaymentBanner
          checkoutUrl={purchase.checkoutUrl}
          onCancel={() => {
            setPurchase({ state: 'idle' });
          }}
        />
      )}
    </div>
  );
});

interface AwaitingPaymentBannerProperties {
  checkoutUrl: string;
  onCancel: () => void;
}

function AwaitingPaymentBanner({
  checkoutUrl,
  onCancel
}: Readonly<AwaitingPaymentBannerProperties>) {
  return (
    <div
      role='status'
      aria-live='polite'
      className={cn(
        'flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50/70 px-2.5 py-2',
        'dark:border-amber-900/60 dark:bg-amber-950/20'
      )}
    >
      <Loader2 className='mt-0.5 h-3 w-3 shrink-0 animate-spin text-amber-600 dark:text-amber-400' />
      <div className='min-w-0 flex-1 space-y-1'>
        <div className='text-[11px] font-medium text-amber-800 dark:text-amber-300'>
          Awaiting payment…
        </div>
        <div className='text-[11px] text-amber-700/80 dark:text-amber-400/70'>
          We'll detect it automatically once the popup completes.
        </div>
        <div className='flex items-center gap-2 pt-0.5'>
          <button
            type='button'
            onClick={() => {
              openCheckoutWindow(checkoutUrl);
            }}
            className={cn(
              'text-[11px] font-medium text-amber-800 underline-offset-2 hover:underline',
              'dark:text-amber-300'
            )}
          >
            Reopen checkout
          </button>
          <span className='text-amber-600/40 dark:text-amber-500/40'>·</span>
          <button
            type='button'
            onClick={onCancel}
            className={cn(
              'text-[11px] text-amber-700/70 underline-offset-2 hover:underline',
              'dark:text-amber-400/70'
            )}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
