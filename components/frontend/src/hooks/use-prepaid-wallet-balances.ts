/**
 * usePrepaidWalletBalances
 *
 * Shared prepaid-wallet polling engine for the chat PaymentGate and the
 * collective accounts modal. Both sites poll a set of publisher wallets
 * (one per `credits_url`) on a fixed interval, minting one satellite token
 * per host and fetching each wallet's live balance until it crosses the
 * per-request price threshold.
 *
 * This module exposes:
 *
 * - a small pure core (no React) — the {@link PrepaidWalletDescriptor} type plus
 *   {@link descriptorFromPending}, {@link dedupeWalletsByKey},
 *   {@link distinctWalletTargets}, {@link isWalletFunded} and the shared
 *   {@link fetchWalletBalances} fetch helper — reused by the React-Query-based
 *   {@link useCollectiveQueryReadiness} too; and
 * - {@link usePrepaidWalletBalances}, the `setInterval` engine hook that wraps
 *   that core in `useState` + polling for the two settlement UIs.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { PendingSubscription } from '@/hooks/use-xendit-precheck';

import { fetchBalance, getSatelliteToken, POLL_INTERVAL_MS, tokenScope } from '@/lib/xendit-client';

// ── shared pure core (no React) ──────────────────────────────────────────────

export interface PrepaidWalletDescriptor {
  /** Stable identity: wallet_id (cluster) or credits_url (self-hosted). */
  walletKey: string;
  creditsUrl: string;
  /**
   * Satellite-token audience for this wallet: the wallet-hosting account
   * (cluster) or the endpoint owner (self-hosted).
   */
  owner: string;
  /** Minimum balance considered "funded" — pricePerUnit ?? 1. */
  threshold: number;
}

/**
 * Adapt a PendingSubscription (gate + modal) to the core descriptor.
 *
 * NOTE: this bakes in the "threshold defaults to 1" rule. The token audience
 * comes pre-resolved on the subscription (`audience`), so shared cluster
 * wallets mint for the wallet-hosting account, not the first endpoint's owner.
 */
export function descriptorFromPending(p: PendingSubscription): PrepaidWalletDescriptor {
  return {
    walletKey: p.walletKey,
    creditsUrl: p.creditsUrl,
    owner: p.audience,
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

/** Dedup descriptors by walletKey, first-wins. */
export function dedupeWalletsByKey(wallets: PrepaidWalletDescriptor[]): PrepaidWalletDescriptor[] {
  const byKey = new Map<string, PrepaidWalletDescriptor>();
  for (const wallet of wallets) {
    if (!byKey.has(wallet.walletKey)) byKey.set(wallet.walletKey, wallet);
  }
  return [...byKey.values()];
}

/**
 * One wallet per token scope, insertion order — the token-fetch dedup set.
 *
 * Keyed by {@link tokenScope}, not by owner: a token is bound to the host it is
 * sent to, so an account serving two hosts needs one token each. Wallets on the
 * same host still share a token.
 */
export function distinctWalletTargets(
  wallets: PrepaidWalletDescriptor[]
): [string, PrepaidWalletDescriptor][] {
  const byScope = new Map<string, PrepaidWalletDescriptor>();
  for (const wallet of wallets) {
    const scope = tokenScope(wallet.creditsUrl);
    if (!byScope.has(scope)) byScope.set(scope, wallet);
  }
  return [...byScope];
}

/** Mint one token per distinct scope. Wallets whose mint fails are absent. */
export async function mintWalletTokens(
  wallets: PrepaidWalletDescriptor[]
): Promise<Map<string, string>> {
  const tokenByScope = new Map<string, string>();
  await Promise.all(
    distinctWalletTargets(wallets).map(async ([scope, wallet]) => {
      const token = await getSatelliteToken(wallet.owner, wallet.creditsUrl);
      if (token) tokenByScope.set(scope, token);
    })
  );
  return tokenByScope;
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
 * Fetch the live balance for each wallet using a pre-built scope→token map.
 *
 * Returns `[walletKey, number | null]` tuples — `null` when the wallet has no
 * token or the balance fetch fails. Callers decide what `null` means: the
 * engine drops nulls (keeps the previous balance), while readiness keeps them
 * to block the ready state. This helper never coerces missing to 0.
 */
export async function fetchWalletBalances(
  wallets: PrepaidWalletDescriptor[],
  tokenByScope: Map<string, string>,
  signal: AbortSignal
): Promise<[string, number | null][]> {
  return Promise.all(
    wallets.map(async (wallet) => {
      const token = tokenByScope.get(tokenScope(wallet.creditsUrl));
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

  // One satellite token per distinct host, fetched when enabled (and refreshed
  // only when the wallet set changes). Gated by `enabled` so a disabled modal
  // never mints tokens.
  const tokensReference = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void (async () => {
      const next = await mintWalletTokens(wallets);
      if (controller.signal.aborted) return;
      tokensReference.current = next;
    })();
    return () => {
      controller.abort();
    };
  }, [wallets, enabled]);

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
