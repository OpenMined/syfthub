/**
 * CollectiveAccountsModal
 *
 * "Who do I have an account with?" view for a collective shared endpoint.
 * Mirrors the chat PaymentGate / wallet-panel settlement UX, but scoped to the
 * members participating in a single shared endpoint:
 *
 * - Prepaid (Xendit/Stripe) members are grouped per publisher wallet
 *   (`credits_url`, one per owner) — settlement is per actual user, not per
 *   endpoint. Each row shows your live balance, or a Buy / Initiate-invoice
 *   action when you're not yet settled. Reuses {@link PrepaidAccountRow}.
 * - MPP members collapse into a single Hub-wallet row (one per-user wallet,
 *   pathUSD) with a top-up link to wallet settings. They still bill per
 *   request — only the settlement route (the Hub wallet) differs.
 * - Free members are summarised as "no payment required".
 *
 * Balance fetching + polling follow the same shape as the chat gate: one
 * satellite token per owner, one balance fetch per `credits_url`, polled while
 * the modal is open and a wallet is still unfunded.
 */
import { useMemo } from 'react';

import type { EndpointReference, PendingSubscription } from '@/hooks/use-xendit-precheck';
import type { CollectiveBillingSummary } from '@/lib/collectives-api';
import type { PolicyUnit } from '@/lib/xendit-client';

import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import Coins from 'lucide-react/dist/esm/icons/coins';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Wallet from 'lucide-react/dist/esm/icons/wallet';

import { PrepaidAccountRow } from '@/components/chat/prepaid-account-row';
import { Modal } from '@/components/ui/modal';
import { useWalletContext } from '@/context/wallet-context';
import { useCollectiveBilling } from '@/hooks/use-collective-billing';
import {
  descriptorMapFromPending,
  usePrepaidWalletBalances
} from '@/hooks/use-prepaid-wallet-balances';
import { useWalletBalance } from '@/hooks/use-wallet-api';
import { useRegisterOnFundingDetected } from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

export interface CollectiveAccountsModalProps {
  isOpen: boolean;
  onClose: () => void;
  collectiveSlug: string;
  /** Omit (or pass 'all') for the default `collective/<slug>` shared endpoint. */
  sharedSlug?: string;
  /** Human label for the shared endpoint being settled (path or name). */
  title?: string;
}

/** Group prepaid members by publisher wallet (credits_url ≈ per owner). */
function buildPrepaidGroups(summary: CollectiveBillingSummary | null): PendingSubscription[] {
  if (!summary) return [];
  const byWallet = new Map<string, PendingSubscription>();
  for (const member of summary.members) {
    const b = member.billing;
    if (b.kind !== 'prepaid') continue;
    if (!b.credits_url || !b.payment_url) continue;
    if (!member.endpoint_owner_username || !member.endpoint_slug) continue;

    const reference: EndpointReference = {
      id: String(member.endpoint_id),
      path: `${member.endpoint_owner_username}/${member.endpoint_slug}`,
      owner: member.endpoint_owner_username,
      slug: member.endpoint_slug,
      name: member.endpoint_name ?? member.endpoint_slug,
      role: 'data_source'
    };

    const existing = byWallet.get(b.credits_url);
    if (existing) {
      existing.endpoints.push(reference);
      continue;
    }
    byWallet.set(b.credits_url, {
      walletKey: b.credits_url,
      endpoints: [reference],
      paymentUrl: b.payment_url,
      creditsUrl: b.credits_url,
      bundles: b.bundles.map((bundle) => ({ name: bundle.name, amount: bundle.amount })),
      currency: b.currency ?? 'IDR',
      pricePerUnit: b.price_per_unit,
      unit: (b.unit === 'document' ? 'document' : 'request') as PolicyUnit,
      balance: 0
    });
  }
  return [...byWallet.values()];
}

export function CollectiveAccountsModal({
  isOpen,
  onClose,
  collectiveSlug,
  sharedSlug,
  title
}: Readonly<CollectiveAccountsModalProps>) {
  const { data: summary, isLoading } = useCollectiveBilling(collectiveSlug, sharedSlug, {
    enabled: isOpen
  });

  const prepaidGroups = useMemo(() => buildPrepaidGroups(summary ?? null), [summary]);

  // ── balances: one entry per credits_url, seeded at 0 ──────────────────────
  const seedBalances = useMemo(() => {
    const map: Record<string, number> = {};
    for (const p of prepaidGroups) map[p.walletKey] = p.balance;
    return map;
  }, [prepaidGroups]);

  // Stable descriptor per wallet — reused for the poll engine and per-row
  // `isWalletActive` lookups so rows don't allocate a fresh descriptor each render.
  const descriptorByKey = useMemo(() => descriptorMapFromPending(prepaidGroups), [prepaidGroups]);
  const wallets = useMemo(() => [...descriptorByKey.values()], [descriptorByKey]);

  // `enabled: isOpen` reproduces both old `if (!isOpen) return` guards (token
  // fetch + poll) through the engine's single switch.
  const registerOnFunding = useRegisterOnFundingDetected();
  const { balances, isWalletActive } = usePrepaidWalletBalances({
    wallets,
    seedBalances,
    enabled: isOpen,
    onWalletFunded: (wallet, balance) => {
      const p = prepaidGroups.find((x) => x.walletKey === wallet.walletKey);
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

  const unsettledCount = prepaidGroups.filter((p) => {
    const descriptor = descriptorByKey.get(p.walletKey);
    return descriptor ? !isWalletActive(descriptor) : true;
  }).length;
  const hasMpp = (summary?.mpp_count ?? 0) > 0;
  const freeCount = summary?.free_count ?? 0;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title='Your accounts with this collective' size='2xl'>
      <div className='space-y-4'>
        <p className='text-muted-foreground text-sm'>
          To query {title ? <code className='text-xs'>{title}</code> : 'this Collective API'} you
          need an active balance with each paid endpoint. Settle any below before querying.
        </p>

        {isLoading ? (
          <div className='text-muted-foreground flex items-center justify-center gap-2 py-8 text-sm'>
            <Loader2 className='h-4 w-4 animate-spin' />
            Checking your accounts…
          </div>
        ) : (
          <>
            {/* Prepaid (per-publisher) accounts */}
            {prepaidGroups.length > 0 && (
              <section className='space-y-1.5'>
                <SectionLabel>
                  Prepaid accounts
                  {unsettledCount > 0 ? (
                    <span className='text-amber-600 dark:text-amber-400'>
                      {' '}
                      · {unsettledCount} need settling
                    </span>
                  ) : (
                    <span className='text-emerald-600 dark:text-emerald-400'> · all settled</span>
                  )}
                </SectionLabel>
                {prepaidGroups.map((p) => {
                  const owner = p.endpoints[0]?.owner ?? 'Publisher';
                  const count = p.endpoints.length;
                  const descriptor = descriptorByKey.get(p.walletKey);
                  return (
                    <PrepaidAccountRow
                      key={p.walletKey}
                      pending={p}
                      liveBalance={balances[p.walletKey] ?? 0}
                      isActive={descriptor ? isWalletActive(descriptor) : false}
                      label={`@${owner}`}
                      sublabel={`${String(count)} ${count === 1 ? 'endpoint' : 'endpoints'}`}
                    />
                  );
                })}
              </section>
            )}

            {/* MPP / Hub wallet — a single wallet settles every MPP member */}
            {hasMpp && (
              <section className='space-y-1.5'>
                <SectionLabel>Hub wallet (MPP)</SectionLabel>
                <MppWalletRow mppCount={summary?.mpp_count ?? 0} onClose={onClose} />
              </section>
            )}

            {/* Free members — no settlement required */}
            {freeCount > 0 && (
              <div className='flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300'>
                <Coins className='h-3.5 w-3.5 shrink-0' />
                {freeCount} {freeCount === 1 ? 'endpoint is' : 'endpoints are'} free — no payment
                required.
              </div>
            )}

            {prepaidGroups.length === 0 && !hasMpp && freeCount === 0 && (
              <p className='text-muted-foreground py-6 text-center text-sm'>
                This Collective API has no active members yet.
              </p>
            )}
          </>
        )}

        <div className='flex justify-end pt-1'>
          <button
            type='button'
            onClick={onClose}
            className='font-inter text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg px-4 py-2 text-sm transition-colors'
          >
            Done
          </button>
        </div>
      </div>
    </Modal>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <p className='font-inter text-muted-foreground text-[10px] font-semibold tracking-wider uppercase'>
      {children}
    </p>
  );
}

/**
 * Single Hub (MPP) wallet row — one per-user pathUSD wallet that settles every
 * MPP member's per-request charge. Mirrors the wallet-panel MPP row; links to
 * wallet settings to set up or top up.
 */
function MppWalletRow({ mppCount, onClose }: Readonly<{ mppCount: number; onClose: () => void }>) {
  const { isConfigured } = useWalletContext();
  const { balance, isLoading } = useWalletBalance();
  const { openSettings } = useSettingsModalStore();

  const handleOpenSettings = () => {
    onClose();
    openSettings('payment');
  };

  const displayBalance = balance?.balance ?? 0;
  const currency = balance?.currency ?? 'USD';
  const memberLabel = `${String(mppCount)} ${mppCount === 1 ? 'endpoint' : 'endpoints'}`;

  return (
    <div
      className={cn(
        'rounded-md border px-3 py-2.5',
        isConfigured
          ? 'border-emerald-200 dark:border-emerald-900/50'
          : 'border-amber-200/60 dark:border-amber-900/40'
      )}
    >
      <div className='flex items-center justify-between gap-3'>
        <div className='flex min-w-0 items-center gap-2.5'>
          <div
            className={cn(
              'flex h-7 w-7 shrink-0 items-center justify-center rounded-md border',
              isConfigured
                ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-400'
                : 'border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-400'
            )}
          >
            <Wallet className='h-3.5 w-3.5' />
          </div>
          <div className='min-w-0'>
            <div className='text-foreground text-sm font-medium'>MPP Wallet</div>
            <div className='text-muted-foreground mt-0.5 text-[11px]'>
              {isConfigured ? (
                <span className='inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400'>
                  <CheckCircle2 className='h-3 w-3' />
                  {isLoading ? (
                    <Loader2 className='h-3 w-3 animate-spin' />
                  ) : (
                    <span className='tabular-nums'>
                      {displayBalance.toLocaleString()} {currency}
                    </span>
                  )}
                  <span className='text-muted-foreground'>· covers {memberLabel}</span>
                </span>
              ) : (
                <span className='inline-flex items-center gap-1 text-amber-700 dark:text-amber-400'>
                  <AlertTriangle className='h-3 w-3' />
                  Not set up · funds {memberLabel}
                </span>
              )}
            </div>
          </div>
        </div>
        <button
          type='button'
          onClick={handleOpenSettings}
          className={cn(
            'inline-flex h-8 shrink-0 items-center justify-center rounded-md border px-3 text-xs font-medium transition-colors',
            'border-violet-300 bg-violet-50 text-violet-700 hover:bg-violet-100',
            'dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300 dark:hover:bg-violet-900/40'
          )}
        >
          {isConfigured ? 'Top up' : 'Set up'}
        </button>
      </div>
    </div>
  );
}
