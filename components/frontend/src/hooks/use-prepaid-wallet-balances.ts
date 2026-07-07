/**
 * usePrepaidWalletBalances
 *
 * Shared prepaid-wallet polling engine for the chat PaymentGate and the
 * collective accounts modal. Both sites poll a set of publisher wallets
 * (one per `credits_url`) on a fixed interval, minting one satellite token
 * per owner and fetching each wallet's live balance until it crosses the
 * per-request price threshold.
 *
 * This module exposes:
 *
 * - a small pure core (no React) — the {@link PrepaidWalletDescriptor} type plus
 *   {@link descriptorFromPending}, {@link dedupeWalletsByKey},
 *   {@link distinctWalletOwners}, {@link isWalletFunded} and the shared
 *   {@link fetchWalletBalances} fetch helper — reused by the React-Query-based
 *   {@link useCollectiveQueryReadiness} too; and
 * - {@link usePrepaidWalletBalances}, the `setInterval` engine hook that wraps
 *   that core in `useState` + polling for the two settlement UIs.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import { fetchBalance, getSatelliteToken, POLL_INTERVAL_MS } from '@/lib/xendit-client';

// ── shared pure core (no React) ──────────────────────────────────────────────

export interface PrepaidWalletDescriptor {
  /** Stable identity = credits_url. Multiple endpoints/members collapse to one. */
  walletKey: string;
  creditsUrl: string;
  /** Owner used to mint the satellite token. = endpoints[0].owner for the gate. */
  owner: string;
  /** Minimum balance considered "funded" — pricePerUnit ?? 1. */
  threshold: number;
}

/**
 * Adapt a PendingSubscription (gate + modal) to the core descriptor.
 *
 * NOTE: this bakes in the gate's "owner = first endpoint of the wallet"
 * assumption and the "threshold defaults to 1" rule. A call site that owns a
 * wallet via a non-first endpoint must build the descriptor itself.
 */
export function descriptorFromPending(p: PendingSubscription): PrepaidWalletDescriptor {
  return {
    walletKey: p.walletKey,
    creditsUrl: p.creditsUrl,
    owner: p.endpoints[0]?.owner ?? '',
    threshold: p.pricePerUnit ?? 1
  };
}

/**
 * Build a `walletKey -> descriptor` Map from pending subscriptions, first-wins.
 *
 * The Map doubles as the per-row `isWalletActive` lookup (keyed by walletKey)
 * and, via `.values()`, the already-deduped wallet list for the poll engine —
 * so callers never need a separate `dedupeWalletsByKey` pass.
 */
export function descriptorMapFromPending(
  pending: PendingSubscription[]
): Map<string, PrepaidWalletDescriptor> {
  const byKey = new Map<string, PrepaidWalletDescriptor>();
  for (const p of pending) {
    if (!byKey.has(p.walletKey)) byKey.set(p.walletKey, descriptorFromPending(p));
  }
  return byKey;
}

/** Dedup descriptors by walletKey (credits_url), first-wins. */
export function dedupeWalletsByKey(wallets: PrepaidWalletDescriptor[]): PrepaidWalletDescriptor[] {
  const byKey = new Map<string, PrepaidWalletDescriptor>();
  for (const wallet of wallets) {
    if (!byKey.has(wallet.walletKey)) byKey.set(wallet.walletKey, wallet);
  }
  return [...byKey.values()];
}

/** Distinct owners across descriptors, insertion order (token-fetch dedup). */
export function distinctWalletOwners(wallets: PrepaidWalletDescriptor[]): string[] {
  const owners = new Set<string>();
  for (const wallet of wallets) owners.add(wallet.owner);
  return [...owners];
}

/** balance >= threshold, with `balances[key] ?? 0` default. */
export function isWalletFunded(
  wallet: PrepaidWalletDescriptor,
  balances: Record<string, number>
): boolean {
  const balance = balances[wallet.walletKey] ?? 0;
  return balance >= wallet.threshold;
}

/**
 * Fetch the live balance for each wallet using a pre-built owner→token map.
 *
 * Returns `[walletKey, number | null]` tuples — `null` when the owner has no
 * token or the balance fetch fails. Callers decide what `null` means: the
 * engine drops nulls (keeps the previous balance), while readiness keeps them
 * to block the ready state. This helper never coerces missing to 0.
 */
export async function fetchWalletBalances(
  wallets: PrepaidWalletDescriptor[],
  tokenByOwner: Map<string, string>,
  signal: AbortSignal
): Promise<[string, number | null][]> {
  return Promise.all(
    wallets.map(async (wallet) => {
      const token = tokenByOwner.get(wallet.owner);
      const balance = token ? await fetchBalance(wallet.creditsUrl, token, signal) : null;
      return [wallet.walletKey, balance] as [string, number | null];
    })
  );
}

// ── setInterval engine hook (payment-gate + collective-accounts-modal) ───────

export interface UsePrepaidWalletBalancesOptions {
  /** Already-normalized wallets. Caller memoizes; identity drives effects. */
  wallets: PrepaidWalletDescriptor[];
  /** walletKey -> seed balance (p.balance / 0). Two-step seed sync preserved. */
  seedBalances: Record<string, number>;
  /** Master switch. payment-gate passes true; modal passes isOpen.
   *  Gates BOTH token fetch and poll, replacing the modal's `if (!isOpen) return`. */
  enabled?: boolean;
  /** Defaults to POLL_INTERVAL_MS (3000). */
  pollIntervalMs?: number;
  /** Per-wallet callback fired once (locally deduped) when balance first > 0. */
  onWalletFunded?: (wallet: PrepaidWalletDescriptor, balance: number) => void;
}

export interface UsePrepaidWalletBalancesResult {
  /** walletKey -> live balance. Reference-stable across no-op polls (diffing setState). */
  balances: Record<string, number>;
  /** Stable callback: balance >= threshold. Recreated only when `balances` changes. */
  isWalletActive: (wallet: PrepaidWalletDescriptor) => boolean;
  /** wallets.every(isWalletActive). Cheap O(n), recomputed by caller or exposed here. */
  allActive: boolean;
}

export function usePrepaidWalletBalances(
  options: UsePrepaidWalletBalancesOptions
): UsePrepaidWalletBalancesResult {
  const {
    wallets,
    seedBalances,
    enabled = true,
    pollIntervalMs = POLL_INTERVAL_MS,
    onWalletFunded
  } = options;

  // Two-step seed: state is initialized from the seed and re-synced whenever the
  // caller recomputes seedBalances (e.g. pending/prepaidGroups changed).
  const [balances, setBalances] = useState<Record<string, number>>(seedBalances);
  useEffect(() => {
    setBalances(seedBalances);
  }, [seedBalances]);

  const isWalletActive = useCallback(
    (wallet: PrepaidWalletDescriptor) => isWalletFunded(wallet, balances),
    [balances]
  );

  // One satellite token per distinct owner, fetched when enabled (and refreshed
  // only when the owner set changes). Gated by `enabled` so a disabled modal
  // never mints tokens.
  const owners = useMemo(() => distinctWalletOwners(wallets), [wallets]);
  const tokensReference = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    if (!enabled) return;
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
  }, [owners, enabled]);

  // Fire the funding callback the first time we observe a non-zero balance for a
  // wallet — locally deduped so it runs once per wallet per session.
  const registeredKeysReference = useRef<Set<string>>(new Set());
  const onWalletFundedReference = useRef(onWalletFunded);
  onWalletFundedReference.current = onWalletFunded;
  useEffect(() => {
    for (const wallet of wallets) {
      const balance = balances[wallet.walletKey] ?? 0;
      if (balance <= 0) continue;
      if (registeredKeysReference.current.has(wallet.walletKey)) continue;
      registeredKeysReference.current.add(wallet.walletKey);
      onWalletFundedReference.current?.(wallet, balance);
    }
  }, [balances, wallets]);

  // Poll once per *wallet* that's still inactive — wallets are already deduped
  // by walletKey by the caller, so each credits_url is fetched once per tick.
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const tick = async () => {
      const inactive = wallets.filter((wallet) => !isWalletActive(wallet));
      if (inactive.length === 0) return;
      const updates = await fetchWalletBalances(
        inactive,
        tokensReference.current,
        controller.signal
      );
      setBalances((previous) => {
        let next: Record<string, number> | null = null;
        for (const [walletKey, balance] of updates) {
          if (balance !== null && previous[walletKey] !== balance) {
            next ??= { ...previous };
            next[walletKey] = balance;
          }
        }
        return next ?? previous;
      });
    };
    const intervalId = setInterval(() => void tick(), pollIntervalMs);
    return () => {
      clearInterval(intervalId);
      controller.abort();
    };
  }, [wallets, isWalletActive, enabled, pollIntervalMs]);

  const allActive = wallets.every((wallet) => isWalletActive(wallet));

  return { balances, isWalletActive, allActive };
}
