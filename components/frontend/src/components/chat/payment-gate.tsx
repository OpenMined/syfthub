/**
 * PaymentGate
 *
 * Inline gate rendered in the chat history (right after the user's bubble)
 * when one or more selected endpoints carry an unfunded Xendit policy.
 * Each row drives its own buy flow (popup checkout window); the parent polls
 * credits_url to detect when each wallet flips active and unlocks Send.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import Clock from 'lucide-react/dist/esm/icons/clock';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import X from 'lucide-react/dist/esm/icons/x';

import { BundlePicker } from '@/components/endpoint/bundle-picker';
import { useRegisterOnFundingDetected } from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';
import {
  createInvoice,
  fetchBalance,
  getSatelliteToken,
  openCheckoutWindow,
  POLL_INTERVAL_MS
} from '@/lib/xendit-client';

function distinctOwners(pending: PendingSubscription[]): string[] {
  const owners = new Set<string>();
  for (const p of pending) {
    for (const e of p.endpoints) owners.add(e.owner);
  }
  return [...owners];
}

// ── per-row sub-component ──────────────────────────────────────────────────

type PurchaseState =
  | { state: 'idle' }
  | { state: 'creating' }
  | { state: 'awaiting'; checkoutUrl: string }
  | { state: 'error'; message: string };

interface RowProperties {
  pending: PendingSubscription;
  liveBalance: number;
  isActive: boolean;
  onRemove: () => void;
}

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
  if (pending.pricePerRequest === null) {
    return <>Pay-in-advance required</>;
  }
  return (
    <span className='tabular-nums'>
      {pending.currency} {pending.pricePerRequest.toLocaleString()} per request
    </span>
  );
}

function PaymentGateRow({ pending, liveBalance, isActive, onRemove }: Readonly<RowProperties>) {
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
  const roleLabel = primaryEndpoint?.role === 'model' ? 'Model' : 'Data source';

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
        {/* Left: icon + endpoint + status */}
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
              <span className='text-foreground truncate text-sm font-medium'>
                {primaryEndpoint?.path ?? 'Unknown endpoint'}
              </span>
              <span className='text-muted-foreground text-[11px]'>· {roleLabel}</span>
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

// ── PaymentGate ────────────────────────────────────────────────────────────

export interface PaymentGateProperties {
  pending: PendingSubscription[];
  /** User cancels — the queued send is dropped. */
  onCancel: () => void;
  /** All wallets active and user clicks Send — fire the queued request. */
  onConfirmSend: () => void;
  /** User clicks the × on a row — drop those endpoints from the chat selection. */
  onRemovePending: (pending: PendingSubscription) => void;
}

export function PaymentGate({
  pending,
  onCancel,
  onConfirmSend,
  onRemovePending
}: Readonly<PaymentGateProperties>) {
  const seedBalances = useMemo(() => {
    const map: Record<string, number> = {};
    for (const p of pending) map[p.walletKey] = p.balance;
    return map;
  }, [pending]);
  const [balances, setBalances] = useState<Record<string, number>>(seedBalances);
  useEffect(() => {
    setBalances(seedBalances);
  }, [seedBalances]);

  // One satellite token per distinct owner, fetched once when the gate mounts.
  const tokensReference = useRef<Map<string, string>>(new Map());
  const owners = useMemo(() => distinctOwners(pending), [pending]);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const next = new Map<string, string>();
      await Promise.all(
        owners.map(async (owner) => {
          const token = await getSatelliteToken(owner);
          if (token) next.set(owner, token);
        })
      );
      if (controller.signal.aborted) return;
      tokensReference.current = next;
    })();
    return () => {
      controller.abort();
    };
  }, [owners]);

  const isWalletActive = useCallback(
    (p: PendingSubscription) => {
      const balance = balances[p.walletKey] ?? 0;
      const threshold = p.pricePerRequest ?? 1;
      return balance >= threshold;
    },
    [balances]
  );

  // Register a subscription on the SyftHub backend the first time we observe
  // a non-zero balance. Idempotent on the server, but we also dedupe locally
  // so the mutation only fires once per wallet per gate session.
  const registerOnFunding = useRegisterOnFundingDetected();
  const registeredKeysReference = useRef<Set<string>>(new Set());
  useEffect(() => {
    for (const p of pending) {
      const balance = balances[p.walletKey] ?? 0;
      if (balance <= 0) continue;
      if (registeredKeysReference.current.has(p.walletKey)) continue;
      registeredKeysReference.current.add(p.walletKey);
      const owner = p.endpoints[0]?.owner ?? '';
      const slug = p.endpoints[0]?.slug ?? null;
      void registerOnFunding({
        creditsUrl: p.creditsUrl,
        paymentUrl: p.paymentUrl,
        endpointOwner: owner,
        endpointSlug: slug,
        currency: p.currency,
        lastKnownBalance: balance
      });
    }
  }, [balances, pending, registerOnFunding]);

  // Poll once per *wallet* that's still inactive — multiple rows sharing a
  // credits_url collapse into one fetch, and the result updates every row
  // bound to that wallet.
  useEffect(() => {
    const controller = new AbortController();
    const tick = async () => {
      const inactive = new Map<string, PendingSubscription>();
      for (const p of pending) {
        if (isWalletActive(p)) continue;
        if (!inactive.has(p.walletKey)) inactive.set(p.walletKey, p);
      }
      if (inactive.size === 0) return;
      const updates = await Promise.all(
        [...inactive.values()].map(async (p) => {
          const owner = p.endpoints[0]?.owner;
          if (!owner) return null;
          const token = tokensReference.current.get(owner);
          if (!token) return null;
          const balance = await fetchBalance(p.creditsUrl, token, controller.signal);
          if (balance === null) return null;
          return [p.walletKey, balance] as const;
        })
      );
      setBalances((previous) => {
        let next: Record<string, number> | null = null;
        for (const u of updates) {
          if (u && previous[u[0]] !== u[1]) {
            next ??= { ...previous };
            next[u[0]] = u[1];
          }
        }
        return next ?? previous;
      });
    };
    const intervalId = setInterval(() => void tick(), POLL_INTERVAL_MS);
    return () => {
      clearInterval(intervalId);
      controller.abort();
    };
  }, [pending, isWalletActive]);

  if (pending.length === 0) return null;

  const allActive = pending.every((p) => isWalletActive(p));

  return (
    <div
      role='region'
      aria-label='Payment required'
      className={cn(
        'max-w-3xl rounded-xl border p-4',
        'border-amber-200 bg-amber-50/70',
        'dark:border-amber-900/50 dark:bg-amber-950/20'
      )}
    >
      <div className='flex items-start gap-2.5'>
        <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400' />
        <div className='min-w-0 flex-1'>
          <h3 className='font-rubik text-sm font-semibold text-amber-900 dark:text-amber-200'>
            Some endpoints need payment
          </h3>
          <p className='font-inter mt-0.5 text-xs text-amber-800/80 dark:text-amber-300/80'>
            Buy credits for each endpoint to send this message, or remove them from the selection to
            continue without.
          </p>
        </div>
      </div>

      <div className='mt-3 space-y-1.5'>
        {pending.map((p) => (
          <PaymentGateRow
            key={`${p.walletKey}::${p.endpoints[0]?.path ?? ''}`}
            pending={p}
            liveBalance={balances[p.walletKey] ?? 0}
            isActive={isWalletActive(p)}
            onRemove={() => {
              onRemovePending(p);
            }}
          />
        ))}
      </div>

      <div className='mt-4 flex items-center justify-end gap-2 border-t border-amber-200/60 pt-3 dark:border-amber-900/40'>
        <button
          type='button'
          onClick={onCancel}
          className='inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-100/60 dark:text-amber-300 dark:hover:bg-amber-900/30'
        >
          Cancel
        </button>
        <button
          type='button'
          disabled={!allActive}
          onClick={onConfirmSend}
          className={cn(
            'group inline-flex h-8 items-center gap-1.5 rounded-md px-3.5 text-xs font-medium transition-colors',
            allActive
              ? 'bg-primary text-primary-foreground hover:bg-primary/90 cursor-pointer'
              : 'cursor-not-allowed bg-amber-200/60 text-amber-900/50 dark:bg-amber-900/30 dark:text-amber-300/40'
          )}
        >
          Send message
          <ArrowRight className='h-3 w-3 transition-transform group-hover:translate-x-0.5' />
        </button>
      </div>
    </div>
  );
}
