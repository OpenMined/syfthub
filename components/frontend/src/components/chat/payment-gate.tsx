/**
 * PaymentGate
 *
 * Inline gate rendered in the chat history (right after the user's bubble)
 * when one or more selected endpoints carry an unfunded Xendit prepaid-
 * credits policy. Drives the buy flow via a popup checkout window; the
 * parent polls credits_url to detect when each wallet flips active and
 * unlocks Send.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';

import { PrepaidAccountRow } from '@/components/chat/prepaid-account-row';
import { useRegisterOnFundingDetected } from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';
import { fetchBalance, getSatelliteToken, POLL_INTERVAL_MS } from '@/lib/xendit-client';

function distinctOwners(pending: PendingSubscription[]): string[] {
  const owners = new Set<string>();
  for (const p of pending) {
    for (const e of p.endpoints) owners.add(e.owner);
  }
  return [...owners];
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
      const threshold = p.pricePerUnit ?? 1;
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
        {pending.map((p) => {
          const key = `${p.walletKey}::${p.endpoints[0]?.path ?? ''}`;
          return (
            <PrepaidAccountRow
              key={key}
              pending={p}
              liveBalance={balances[p.walletKey] ?? 0}
              isActive={isWalletActive(p)}
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
