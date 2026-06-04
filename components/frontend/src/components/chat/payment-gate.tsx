/**
 * PaymentGate
 *
 * Inline gate rendered in the chat history (right after the user's bubble)
 * when one or more selected endpoints carry an unfunded Xendit prepaid-
 * credits policy. Drives the buy flow via a popup checkout window; the
 * parent polls credits_url to detect when each wallet flips active and
 * unlocks Send.
 */
import { useMemo } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';

import { PrepaidAccountRow } from '@/components/chat/prepaid-account-row';
import {
  descriptorMapFromPending,
  usePrepaidWalletBalances
} from '@/hooks/use-prepaid-wallet-balances';
import { useRegisterOnFundingDetected } from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';

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

  // Stable descriptor per wallet — reused for both the poll engine and the
  // per-row `isWalletActive` lookups (avoids allocating a fresh descriptor per
  // row per render, which would defeat the stable-predicate memoization).
  const descriptorByKey = useMemo(() => descriptorMapFromPending(pending), [pending]);
  const wallets = useMemo(() => [...descriptorByKey.values()], [descriptorByKey]);

  const registerOnFunding = useRegisterOnFundingDetected();
  const { balances, isWalletActive, allActive } = usePrepaidWalletBalances({
    wallets,
    seedBalances,
    enabled: true,
    onWalletFunded: (wallet, balance) => {
      const p = pending.find((x) => x.walletKey === wallet.walletKey);
      if (!p) return;
      void registerOnFunding({
        creditsUrl: p.creditsUrl,
        paymentUrl: p.paymentUrl,
        endpointOwner: p.endpoints[0]?.owner ?? '',
        endpointSlug: p.endpoints[0]?.slug ?? null,
        currency: p.currency,
        lastKnownBalance: balance
      });
    }
  });

  if (pending.length === 0) return null;

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
        {pending.map((p) => {
          const key = `${p.walletKey}::${p.endpoints[0]?.path ?? ''}`;
          const descriptor = descriptorByKey.get(p.walletKey);
          return (
            <PrepaidAccountRow
              key={key}
              pending={p}
              liveBalance={balances[p.walletKey] ?? 0}
              isActive={descriptor ? isWalletActive(descriptor) : false}
              onRemove={() => {
                onRemovePending(p);
              }}
            />
          );
        })}
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
