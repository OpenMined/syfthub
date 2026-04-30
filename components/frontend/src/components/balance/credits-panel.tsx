/**
 * CreditsPanel
 *
 * Unified panel that lists every credit pool the user holds:
 *   - the MPP/Tempo wallet (one per user, blockchain-backed)
 *   - every Xendit subscription (one per publisher wallet they've funded)
 *
 * Designed to live inside the BalanceIndicator dropdown. Per-row balance
 * polling is tied to `enabled` so the panel goes silent when closed.
 */
import type { XenditSubscription } from '@/lib/types';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import CircleDot from 'lucide-react/dist/esm/icons/circle-dot';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import Wallet from 'lucide-react/dist/esm/icons/wallet';
import { Link } from 'react-router-dom';

import { useWalletContext } from '@/context/wallet-context';
import { useWalletBalance } from '@/hooks/use-wallet-api';
import { useSubscriptionBalance, useXenditSubscriptions } from '@/hooks/use-xendit-subscriptions';
import { cn } from '@/lib/utils';
import { openCheckoutWindow, POLL_INTERVAL_MS } from '@/lib/xendit-client';

import { formatBalance } from './balance-display';

export interface CreditsPanelProperties {
  /** Whether the panel is visible — gates the per-row polling. */
  enabled: boolean;
  /** Open the wallet settings tab (closes the panel). */
  onOpenWalletSettings: () => void;
  /** Open the subscriptions settings tab (closes the panel). */
  onOpenSubscriptionsSettings: () => void;
  /** Close the panel (used after navigation links). */
  onClose: () => void;
}

export function CreditsPanel({
  enabled,
  onOpenWalletSettings,
  onOpenSubscriptionsSettings,
  onClose
}: Readonly<CreditsPanelProperties>) {
  const subscriptionsQuery = useXenditSubscriptions({ enabled });
  const subscriptions = subscriptionsQuery.data ?? [];

  return (
    <div className='divide-border divide-y'>
      <div className='px-4 py-3'>
        <SectionHeader label='MPP Wallet' onRefresh={null} />
        <MppWalletRow onOpenSettings={onOpenWalletSettings} />
      </div>

      <div className='px-4 py-3'>
        <SectionHeader
          label={
            subscriptions.length > 0
              ? `Endpoint subscriptions · ${String(subscriptions.length)}`
              : 'Endpoint subscriptions'
          }
          onRefresh={() => void subscriptionsQuery.refetch()}
          isRefreshing={subscriptionsQuery.isFetching}
        />
        <SubscriptionsBody
          isLoading={subscriptionsQuery.isLoading}
          subscriptions={subscriptions}
          enabled={enabled}
          onNavigate={onClose}
        />
      </div>

      <div className='flex items-center justify-between px-4 py-3'>
        <button
          type='button'
          onClick={onOpenWalletSettings}
          className={cn(
            'font-inter text-muted-foreground hover:text-foreground',
            'text-xs font-medium transition-colors'
          )}
        >
          Wallet settings
        </button>
        <button
          type='button'
          onClick={onOpenSubscriptionsSettings}
          className={cn(
            'font-inter inline-flex items-center gap-1.5',
            'rounded-md px-2 py-1 text-xs font-medium',
            'text-foreground hover:bg-muted transition-colors'
          )}
        >
          Manage all
          <ExternalLink className='h-3 w-3' />
        </button>
      </div>
    </div>
  );
}

// ── Subscriptions body (loading / empty / list) ───────────────────────────

interface SubscriptionsBodyProperties {
  isLoading: boolean;
  subscriptions: XenditSubscription[];
  enabled: boolean;
  onNavigate: () => void;
}

function SubscriptionsBody({
  isLoading,
  subscriptions,
  enabled,
  onNavigate
}: Readonly<SubscriptionsBodyProperties>) {
  if (isLoading) return <SubscriptionsSkeleton />;
  if (subscriptions.length === 0) return <SubscriptionsEmpty />;
  return (
    <div className='space-y-1.5'>
      {subscriptions.map((sub) => (
        <SubscriptionRow
          key={sub.id}
          subscription={sub}
          enabled={enabled}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  );
}

// ── Section header ─────────────────────────────────────────────────────────

interface SectionHeaderProperties {
  label: string;
  onRefresh: (() => void) | null;
  isRefreshing?: boolean;
}

function SectionHeader({
  label,
  onRefresh,
  isRefreshing = false
}: Readonly<SectionHeaderProperties>) {
  return (
    <div className='mb-2 flex items-center justify-between'>
      <span className='font-inter text-muted-foreground text-[10px] font-semibold tracking-wider uppercase'>
        {label}
      </span>
      {onRefresh && (
        <button
          type='button'
          onClick={onRefresh}
          disabled={isRefreshing}
          className={cn(
            'text-muted-foreground rounded p-1 transition-colors',
            'hover:bg-muted hover:text-foreground',
            'disabled:cursor-not-allowed disabled:opacity-50'
          )}
          aria-label='Refresh'
        >
          <RefreshCw className={cn('h-3 w-3', isRefreshing && 'animate-spin')} />
        </button>
      )}
    </div>
  );
}

// ── MPP wallet row ─────────────────────────────────────────────────────────

interface MppWalletRowProperties {
  onOpenSettings: () => void;
}

function MppWalletRow({ onOpenSettings }: Readonly<MppWalletRowProperties>) {
  const { isConfigured } = useWalletContext();
  const { balance, isLoading, error, refetch } = useWalletBalance();

  if (!isConfigured) {
    return (
      <button
        type='button'
        onClick={onOpenSettings}
        className={cn(
          'group flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
          'border-amber-200 bg-amber-50/60 hover:bg-amber-50',
          'dark:border-amber-900/50 dark:bg-amber-950/15 dark:hover:bg-amber-950/30'
        )}
      >
        <div className='flex min-w-0 items-center gap-2.5'>
          <WalletChip className='border-amber-200 bg-amber-100 text-amber-700 dark:border-amber-900/60 dark:bg-amber-900/30 dark:text-amber-400'>
            <Wallet className='h-3.5 w-3.5' />
          </WalletChip>
          <div className='min-w-0'>
            <div className='font-inter text-foreground truncate text-sm font-medium'>
              MPP Wallet
            </div>
            <div className='font-inter text-muted-foreground text-[11px]'>
              Set up your wallet to pay endpoints
            </div>
          </div>
        </div>
        <span className='font-inter shrink-0 text-[11px] font-medium text-amber-700 group-hover:underline dark:text-amber-400'>
          Set up
        </span>
      </button>
    );
  }

  const displayBalance = balance?.balance ?? 0;
  const currency = balance?.currency ?? 'USD';
  const status = balanceStatus(displayBalance, 0);

  return (
    <div className={cn('rounded-lg border px-3 py-2.5', 'border-border bg-background/40')}>
      <div className='flex items-center justify-between gap-3'>
        <div className='flex min-w-0 items-center gap-2.5'>
          <WalletChip className='border-emerald-200 bg-emerald-100 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-900/30 dark:text-emerald-400'>
            <Wallet className='h-3.5 w-3.5' />
          </WalletChip>
          <div className='min-w-0'>
            <div className='font-inter text-foreground truncate text-sm font-medium'>
              MPP Wallet
            </div>
            <div className='font-inter text-muted-foreground text-[11px]'>Tempo · pathUSD</div>
          </div>
        </div>
        <BalanceCell
          isLoading={isLoading}
          error={error}
          balance={displayBalance}
          currency={currency}
          status={status}
          onRefresh={() => void refetch()}
        />
      </div>
    </div>
  );
}

// ── Subscription row ───────────────────────────────────────────────────────

interface SubscriptionRowProperties {
  subscription: XenditSubscription;
  enabled: boolean;
  onNavigate: () => void;
}

function SubscriptionRow({
  subscription,
  enabled,
  onNavigate
}: Readonly<SubscriptionRowProperties>) {
  const { balance, isLoading, error, refetch } = useSubscriptionBalance(subscription, {
    enabled,
    pollIntervalMs: enabled ? POLL_INTERVAL_MS : undefined
  });

  const liveBalance = balance ?? subscription.last_known_balance ?? 0;
  const status = balanceStatus(liveBalance, 0);
  const label = subscription.endpoint_slug
    ? `${subscription.endpoint_owner}/${subscription.endpoint_slug}`
    : subscription.endpoint_owner;
  const targetPath = subscription.endpoint_slug
    ? `/${subscription.endpoint_owner}/${subscription.endpoint_slug}`
    : `/${subscription.endpoint_owner}`;

  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2.5 transition-colors',
        'border-border bg-background/40 hover:bg-muted/30'
      )}
    >
      <div className='flex items-center justify-between gap-3'>
        <Link
          to={targetPath}
          onClick={onNavigate}
          className='flex min-w-0 flex-1 items-center gap-2.5'
        >
          <WalletChip className='border-violet-200 bg-violet-100 text-violet-700 dark:border-violet-900/60 dark:bg-violet-900/30 dark:text-violet-400'>
            <CreditCard className='h-3.5 w-3.5' />
          </WalletChip>
          <div className='min-w-0'>
            <div className='font-inter text-foreground truncate text-sm font-medium'>{label}</div>
            <div className='font-inter text-muted-foreground text-[11px]'>
              Xendit · {subscription.currency}
            </div>
          </div>
        </Link>
        <BalanceCell
          isLoading={isLoading && balance === null}
          error={error?.message ?? null}
          balance={liveBalance}
          currency={subscription.currency}
          status={status}
          onRefresh={() => void refetch()}
          /* Top-up CTA only meaningful for depleted Xendit pools. */
          onTopUp={
            status === 'empty'
              ? () => {
                  openCheckoutWindow(subscription.payment_url);
                }
              : null
          }
        />
      </div>
    </div>
  );
}

// ── Balance cell ───────────────────────────────────────────────────────────

interface BalanceCellProperties {
  isLoading: boolean;
  error: string | null;
  balance: number;
  currency: string;
  status: BalanceStatus;
  onRefresh: () => void;
  onTopUp?: (() => void) | null;
}

function BalanceCell({
  isLoading,
  error,
  balance,
  currency,
  status,
  onRefresh,
  onTopUp = null
}: Readonly<BalanceCellProperties>) {
  if (isLoading) {
    return (
      <span className='text-muted-foreground inline-flex items-center gap-1.5 text-xs'>
        <Loader2 className='h-3 w-3 animate-spin' />
      </span>
    );
  }
  if (error) {
    return (
      <button
        type='button'
        onClick={onRefresh}
        className='inline-flex items-center gap-1 text-[11px] text-red-600 hover:underline dark:text-red-400'
      >
        <AlertCircle className='h-3 w-3' />
        Retry
      </button>
    );
  }
  return (
    <div className='flex shrink-0 items-center gap-1.5'>
      <StatusChip status={status} />
      <span className={cn('font-inter text-foreground text-sm font-semibold tabular-nums')}>
        {formatBalance(balance)}
      </span>
      <span className='text-muted-foreground text-[10px]'>{currency}</span>
      {onTopUp && (
        <button
          type='button'
          onClick={onTopUp}
          className={cn(
            'ml-1 inline-flex items-center gap-0.5 rounded px-1.5 py-0.5',
            'text-[10px] font-medium',
            'border border-violet-300 bg-violet-50 text-violet-700',
            'hover:bg-violet-100',
            'dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
            'dark:hover:bg-violet-900/40'
          )}
        >
          Top up
        </button>
      )}
    </div>
  );
}

// ── Status chip ────────────────────────────────────────────────────────────

type BalanceStatus = 'healthy' | 'low' | 'empty';

function balanceStatus(balance: number, threshold: number): BalanceStatus {
  if (balance <= threshold) return 'empty';
  if (balance < (threshold > 0 ? threshold * 10 : 100)) return 'low';
  return 'healthy';
}

function StatusChip({ status }: Readonly<{ status: BalanceStatus }>) {
  if (status === 'healthy') {
    return (
      <CheckCircle2
        aria-label='Healthy balance'
        className='h-3 w-3 text-emerald-500 dark:text-emerald-400'
      />
    );
  }
  if (status === 'low') {
    return (
      <CircleDot aria-label='Low balance' className='h-3 w-3 text-amber-500 dark:text-amber-400' />
    );
  }
  return (
    <AlertCircle aria-label='Empty balance' className='h-3 w-3 text-red-500 dark:text-red-400' />
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function WalletChip({
  className,
  children
}: Readonly<{ className?: string; children: React.ReactNode }>) {
  return (
    <div
      className={cn(
        'flex h-7 w-7 shrink-0 items-center justify-center rounded-md border',
        className
      )}
    >
      {children}
    </div>
  );
}

function SubscriptionsSkeleton() {
  return (
    <div className='space-y-1.5'>
      {[0, 1].map((index) => (
        <div
          key={index}
          className='border-border bg-background/40 flex animate-pulse items-center gap-3 rounded-lg border px-3 py-2.5'
        >
          <div className='bg-muted h-7 w-7 rounded-md' />
          <div className='flex-1 space-y-1'>
            <div className='bg-muted h-3 w-32 rounded' />
            <div className='bg-muted h-2 w-20 rounded' />
          </div>
          <div className='bg-muted h-3 w-12 rounded' />
        </div>
      ))}
    </div>
  );
}

function SubscriptionsEmpty() {
  return (
    <div className='border-border text-muted-foreground rounded-lg border border-dashed bg-transparent px-3 py-3 text-center text-[11px]'>
      No endpoint subscriptions yet.
      <br />
      Pay for a Xendit endpoint to see it here.
    </div>
  );
}
