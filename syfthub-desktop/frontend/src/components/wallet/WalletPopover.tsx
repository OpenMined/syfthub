// WalletPopover — the glanceable wallet surface anchored to a header icon.
//
// Layout (per the ui-ux-expert spec):
//   ┌───────────────────────────────────────┐
//   │ MPP WALLET                ↻           │   wallet name + network + balance
//   │ ┌──┐ MPP Wallet      ◇ 20.00 USD     │
//   │ │$ │ Tempo · pathUSD     0xcB30…2485 │
//   │ └──┘                                  │
//   ├───────────────────────────────────────┤
//   │ TRANSACTION HISTORY                    │
//   │ [30d ▾] [All ▾]            Export ⬇   │
//   │ ┌─ scrollable list (max-h 280) ─┐    │
//   │ │ 2m  claude-agent 15.00 USD ✓ ↗│    │
//   │ │ ...                            │    │
//   │ └────────────────────────────────┘    │
//   ├───────────────────────────────────────┤
//   │ Wallet settings        Manage all ↗  │   navigates mainView='wallet'
//   └───────────────────────────────────────┘
//
// Primitive: shadcn Popover (not Dialog — non-modal; not DropdownMenu —
// wrong semantics for a data panel). Trigger is a 32x32 icon button with
// an optional amber dot indicator for actionable states (no wallet, zero
// balance, unsettled rows, last tx failed).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Wallet as WalletIcon,
} from 'lucide-react';

import { BrowserOpenURL } from '../../../wailsjs/runtime/runtime';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useAppStore } from '@/stores/appStore';

import {
  callWailsMethod,
  currencyLabel,
  dateRangeToSince,
  EXPLORER_TX_PREFIX,
  formatIso,
  formatRelative,
  FUND_BALANCE_REFRESH_DELAY_MS,
  FUND_URL,
  statusDotClass,
  truncateMiddle,
  type DateRange,
  type FundResult,
  type PaymentRecord,
  type StatusFilter,
  type TransactionFilter,
  type TransactionPage,
  type WalletBalance,
  type WalletInfo,
} from './wallet-shared';

// POPOVER_WIDTH — wider than the 380px reference so the filter row fits
// two side-by-side selects + the Export link without wrapping. 440 still
// sits comfortably on a 1024px-wide desktop window.
const POPOVER_WIDTH = 440;

// HISTORY_MAX_HEIGHT_PX — caps the scrollable history list at ~6 rows
// (44px each). Older rows belong in the deep settings page; the popover
// is the glance, not the archive.
const HISTORY_MAX_HEIGHT_PX = 280;

// HISTORY_LIMIT — number of rows we fetch for the popover. The Go side
// returns most-recent-first; anything beyond this is reachable via
// "Manage all".
const HISTORY_LIMIT = 25;

// ─────────────────────────────────────────────────────────────────────────
// WalletPopover — top-level component combining the trigger + panel.
// ─────────────────────────────────────────────────────────────────────────

export function WalletPopover() {
  const [open, setOpen] = useState(false);

  // walletInfo + balance live at this level so the trigger can render
  // its indicator dot (no wallet, zero balance, etc.) without opening
  // the popover. We refresh on mount + every popover open + on demand.
  const [walletInfo, setWalletInfo] = useState<WalletInfo | null>(null);
  const [balance, setBalance] = useState<WalletBalance | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [lastTxFailed, setLastTxFailed] = useState(false);

  const refreshWallet = useCallback(async () => {
    setRefreshing(true);
    setWalletError(null);
    try {
      const info = await callWailsMethod<WalletInfo>('WalletShow');
      setWalletInfo(info);
      if (info.key_exists) {
        try {
          const b = await callWailsMethod<WalletBalance>('WalletBalance');
          setBalance(b);
        } catch (err) {
          // Balance failures are non-fatal — wallet card still renders.
          setBalance(null);
          setWalletError(
            err instanceof Error
              ? `Balance unavailable: ${err.message}`
              : 'Balance unavailable'
          );
        }
      } else {
        setBalance(null);
      }
    } catch (err) {
      setWalletError(
        err instanceof Error ? err.message : 'Failed to load wallet'
      );
      setWalletInfo(null);
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Refresh wallet info on first mount and every time the popover opens
  // so a fresh fund tx or a new app session reflects immediately.
  useEffect(() => {
    void refreshWallet();
  }, [refreshWallet]);
  useEffect(() => {
    if (open) void refreshWallet();
  }, [open, refreshWallet]);

  // Indicator: amber for any actionable state, red when last tx failed.
  // Healthy wallets show no dot.
  const indicator: 'none' | 'amber' | 'red' = (() => {
    if (lastTxFailed) return 'red';
    if (!walletInfo) return 'none';
    if (!walletInfo.key_exists) return 'amber';
    if (balance && Number.parseFloat(balance.amount) === 0) return 'amber';
    if (pendingCount > 0) return 'amber';
    return 'none';
  })();

  const tooltipLabel = (() => {
    if (!walletInfo) return 'Wallet';
    if (!walletInfo.key_exists) return 'Wallet — set up';
    if (balance && Number.parseFloat(balance.amount) === 0) {
      return 'Wallet · 0.00 USD — fund';
    }
    if (balance) return `Wallet · ${balance.amount} USD`;
    return 'Wallet';
  })();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label="Open wallet"
              className="
                relative inline-flex h-8 w-8 items-center justify-center rounded-md
                text-muted-foreground hover:text-foreground hover:bg-accent
                transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
                data-[state=open]:bg-accent data-[state=open]:text-foreground
              "
            >
              <WalletIcon className="h-4 w-4" />
              {indicator !== 'none' && (
                <span
                  className={`
                    absolute top-1 right-1 h-1.5 w-1.5 rounded-full
                    ${indicator === 'amber' ? 'bg-amber-500' : 'bg-destructive'}
                  `}
                  aria-hidden="true"
                />
              )}
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        {/* Suppress tooltip while popover is open — no double-overlay. */}
        {!open && (
          <TooltipContent side="bottom" sideOffset={4}>
            <p className="text-xs">{tooltipLabel}</p>
          </TooltipContent>
        )}
      </Tooltip>

      <PopoverContent
        align="end"
        sideOffset={8}
        className="p-0 overflow-hidden"
        style={{ width: POPOVER_WIDTH }}
      >
        <WalletPanel
          walletInfo={walletInfo}
          balance={balance}
          walletError={walletError}
          refreshing={refreshing}
          refreshWallet={refreshWallet}
          closePopover={() => setOpen(false)}
          onPendingCountChange={setPendingCount}
          onLastTxFailedChange={setLastTxFailed}
        />
      </PopoverContent>
    </Popover>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// WalletPanel — the three-section body inside the popover.
// ─────────────────────────────────────────────────────────────────────────

interface WalletPanelProps {
  walletInfo: WalletInfo | null;
  balance: WalletBalance | null;
  walletError: string | null;
  refreshing: boolean;
  refreshWallet: () => Promise<void>;
  closePopover: () => void;
  onPendingCountChange: (count: number) => void;
  onLastTxFailedChange: (failed: boolean) => void;
}

function WalletPanel({
  walletInfo,
  balance,
  walletError,
  refreshing,
  refreshWallet,
  closePopover,
  onPendingCountChange,
  onLastTxFailedChange,
}: WalletPanelProps) {
  const setMainView = useAppStore((s) => s.setMainView);

  // ── Wallet header card ────────────────────────────────────────────────
  const [copied, setCopied] = useState(false);
  const [initRunning, setInitRunning] = useState(false);
  const [fundRunning, setFundRunning] = useState(false);
  const [fundResult, setFundResult] = useState<FundResult | null>(null);
  const [fundError, setFundError] = useState<string | null>(null);

  const copyAddress = useCallback(async () => {
    if (!walletInfo?.address) return;
    try {
      await navigator.clipboard.writeText(walletInfo.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can fail in restricted contexts; nothing actionable.
    }
  }, [walletInfo?.address]);

  const initWallet = useCallback(async () => {
    setInitRunning(true);
    try {
      await callWailsMethod<WalletInfo>('WalletInit');
      await refreshWallet();
    } catch {
      // refreshWallet surfaces errors via walletError; nothing to do here.
    } finally {
      setInitRunning(false);
    }
  }, [refreshWallet]);

  const fundFromFaucet = useCallback(async () => {
    setFundRunning(true);
    setFundError(null);
    setFundResult(null);
    try {
      const result = await callWailsMethod<FundResult>('WalletFund');
      setFundResult(result);
      window.setTimeout(() => {
        void refreshWallet();
      }, FUND_BALANCE_REFRESH_DELAY_MS);
    } catch (err) {
      setFundError(
        err instanceof Error ? err.message : 'Failed to request faucet funds'
      );
    } finally {
      setFundRunning(false);
    }
  }, [refreshWallet]);

  // ── Transaction history ──────────────────────────────────────────────
  const [dateRange, setDateRange] = useState<DateRange>('30d');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState<TransactionPage | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const historyToken = useRef(0);

  const filter: TransactionFilter = useMemo(
    () => ({
      status: statusFilter === 'all' ? undefined : statusFilter,
      since_unix: dateRangeToSince(dateRange) || undefined,
      limit: HISTORY_LIMIT,
    }),
    [statusFilter, dateRange]
  );

  const fetchHistory = useCallback(async () => {
    historyToken.current += 1;
    const token = historyToken.current;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const result = await callWailsMethod<TransactionPage>(
        'TransactionHistory',
        filter
      );
      if (token !== historyToken.current) return;
      setPage({
        records: result?.records ?? [],
        total: result?.total ?? 0,
        totals: result?.totals ?? {
          spent_lifetime: '0',
          spent_month: '0',
          spent_session: '0',
        },
      });
    } catch (err) {
      if (token === historyToken.current) {
        setHistoryError(
          err instanceof Error ? err.message : 'Failed to load history'
        );
      }
    } finally {
      if (token === historyToken.current) setHistoryLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  // Bubble up the indicator-relevant signals to the trigger so the dot
  // reflects unsettled rows / last failure without opening the popover.
  useEffect(() => {
    if (!page) return;
    const records = page.records;
    const pending = records.filter(
      (r) => r.status === 'signed' || r.status === 'broadcast'
    ).length;
    onPendingCountChange(pending);
    const last = records[0];
    onLastTxFailedChange(last?.status === 'failed');
  }, [page, onPendingCountChange, onLastTxFailedChange]);

  const exportCSV = useCallback(async () => {
    setExporting(true);
    try {
      const csv = await callWailsMethod<string>(
        'TransactionHistoryExportCSV',
        filter
      );
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `payments-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Best-effort: log via fund-error slot so the user sees a clear hint.
      setFundError('Export failed');
    } finally {
      setExporting(false);
    }
  }, [filter]);

  const openManageAll = useCallback(() => {
    setMainView('wallet');
    closePopover();
  }, [setMainView, closePopover]);

  const hasWallet = Boolean(walletInfo?.key_exists);

  return (
    <div className="flex flex-col">
      {/* ── MPP WALLET section ────────────────────────────────────────── */}
      <section
        id="wallet-popover-mpp-wallet"
        aria-labelledby="wallet-popover-mpp-wallet-heading"
        className="p-4"
      >
        <div className="flex items-center justify-between">
          <h2
            id="wallet-popover-mpp-wallet-heading"
            className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
          >
            MPP Wallet
          </h2>
          <button
            type="button"
            onClick={() => {
              void refreshWallet();
            }}
            disabled={refreshing}
            className="
              inline-flex h-6 w-6 items-center justify-center rounded
              text-muted-foreground hover:text-foreground hover:bg-accent
              transition-colors disabled:opacity-50
            "
            aria-label="Refresh balance"
          >
            {refreshing ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
          </button>
        </div>

        {hasWallet ? (
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-chart-2/15 text-chart-2 shrink-0">
                <WalletIcon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground truncate">
                  MPP Wallet
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{walletInfo?.network ?? 'tempo-testnet'}</span>
                  <span aria-hidden="true">·</span>
                  <span>pathUSD</span>
                </div>
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-base font-semibold tabular-nums text-foreground">
                {balance?.amount ?? '—'}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  USD
                </span>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={copyAddress}
                    className="
                      mt-0.5 inline-flex items-center gap-1 text-[11px]
                      font-mono text-muted-foreground hover:text-foreground
                      transition-colors
                    "
                  >
                    <span>
                      {walletInfo
                        ? truncateMiddle(walletInfo.address, 6, 4)
                        : ''}
                    </span>
                    {copied ? (
                      <Check className="h-3 w-3 text-chart-2" />
                    ) : (
                      <Copy className="h-3 w-3 opacity-50" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" sideOffset={4}>
                  <p className="font-mono text-xs">{walletInfo?.address}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {copied ? 'Copied' : 'Click to copy'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        ) : (
          <div className="mt-3 rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-3 text-xs">
            <p className="mb-2 text-foreground">No wallet yet.</p>
            <Button
              size="sm"
              onClick={initWallet}
              disabled={initRunning}
              className="h-7 text-xs"
            >
              {initRunning ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Initialising…
                </>
              ) : (
                <>
                  <WalletIcon className="h-3 w-3" />
                  Initialise wallet
                </>
              )}
            </Button>
          </div>
        )}

        {hasWallet && (
          <div className="mt-3 flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={fundFromFaucet}
              disabled={fundRunning}
              className="h-7 text-xs"
              title="Request testnet tokens from the Tempo faucet"
            >
              {fundRunning ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <WalletIcon className="h-3 w-3" />
              )}
              Fund
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => BrowserOpenURL(FUND_URL)}
              className="h-7 px-2 text-xs"
              title="Open Tempo faucet page in browser"
            >
              <ExternalLink className="h-3 w-3" />
            </Button>
            {fundResult && fundResult.hashes.length > 0 && (
              <span className="text-[11px] text-muted-foreground">
                Funded — balance refreshes shortly.
              </span>
            )}
          </div>
        )}

        {walletError && (
          <p className="mt-2 text-[11px] text-destructive">{walletError}</p>
        )}
        {fundError && (
          <p className="mt-2 text-[11px] text-destructive">
            Fund: {fundError}
          </p>
        )}
      </section>

      <div className="h-px bg-border/40" />

      {/* ── TRANSACTION HISTORY section ───────────────────────────────── */}
      <section
        aria-labelledby="wallet-popover-history-heading"
        className="p-4 pt-3"
      >
        <h2
          id="wallet-popover-history-heading"
          className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
        >
          Transaction History
        </h2>

        <div className="mt-2 flex items-center gap-2">
          <Select
            value={dateRange}
            onValueChange={(v) => setDateRange(v as DateRange)}
          >
            <SelectTrigger className="h-7 flex-1 min-w-0 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="24h">Last 24h</SelectItem>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="all">All time</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as StatusFilter)}
          >
            <SelectTrigger className="h-7 flex-1 min-w-0 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="settled">Settled</SelectItem>
              <SelectItem value="signed">Signed</SelectItem>
              <SelectItem value="broadcast">Broadcast</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="refunded">Refunded</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            onClick={exportCSV}
            disabled={exporting || historyLoading}
            className="h-7 px-2 text-xs"
          >
            {exporting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Download className="h-3 w-3" />
            )}
            Export
          </Button>
        </div>

        <div
          className="mt-3 -mx-4 overflow-y-auto"
          style={{ maxHeight: HISTORY_MAX_HEIGHT_PX }}
          role="list"
          aria-label="Recent payments"
        >
          {historyLoading && !page ? (
            <HistorySkeleton />
          ) : historyError ? (
            <div className="px-4 py-6 text-center text-xs text-destructive">
              {historyError}
            </div>
          ) : !page || page.records.length === 0 ? (
            <EmptyHistory />
          ) : (
            <ul className="divide-y divide-border/40">
              {page.records.map((rec) => (
                <li key={rec.id} role="listitem">
                  <HistoryRow record={rec} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <div className="h-px bg-border/40" />

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-xs text-muted-foreground">Wallet settings</span>
        <button
          type="button"
          onClick={openManageAll}
          className="
            inline-flex items-center gap-1 text-xs font-medium text-foreground
            hover:text-primary transition-colors
            focus-visible:outline-none focus-visible:underline
          "
        >
          Manage all
          <ExternalLink className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// HistoryRow — one payment row.
// ─────────────────────────────────────────────────────────────────────────

function HistoryRow({ record }: { record: PaymentRecord }) {
  const handleExplorer = useCallback(() => {
    if (record.tx_hash) {
      BrowserOpenURL(`${EXPLORER_TX_PREFIX}${record.tx_hash}`);
    }
  }, [record.tx_hash]);

  const endpointLabel = record.endpoint_label || record.endpoint_slug;
  const hasHash = Boolean(record.tx_hash);

  return (
    <div className="group flex items-center gap-2 px-4 py-2.5 hover:bg-accent/30">
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-foreground truncate">
          {endpointLabel}
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="text-[11px] text-muted-foreground tabular-nums cursor-default">
              {formatRelative(record.timestamp_unix)}
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom" sideOffset={4}>
            <p className="text-xs font-mono">
              {formatIso(record.timestamp_unix)}
            </p>
          </TooltipContent>
        </Tooltip>
      </div>

      <div className="text-right shrink-0">
        <div className="text-xs tabular-nums text-foreground">
          {record.amount}
          <span className="ml-1 text-muted-foreground">
            {currencyLabel(record.currency)}
          </span>
        </div>
        {record.status === 'failed' && record.failure_reason && (
          <div className="text-[10px] text-destructive truncate max-w-[160px]">
            {record.failure_reason}
          </div>
        )}
      </div>

      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`h-2 w-2 rounded-full shrink-0 ${statusDotClass(record.status)}`}
            aria-label={`Status: ${record.status}`}
          />
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={4}>
          <p className="text-xs capitalize">{record.status}</p>
        </TooltipContent>
      </Tooltip>

      {hasHash ? (
        <button
          type="button"
          onClick={handleExplorer}
          className="
            shrink-0 opacity-0 group-hover:opacity-100 transition-opacity
            text-muted-foreground hover:text-foreground
            focus-visible:outline-none focus-visible:opacity-100
          "
          aria-label="View transaction on Tempo explorer"
        >
          <ExternalLink className="h-3 w-3" />
        </button>
      ) : (
        <span className="h-3 w-3 shrink-0" aria-hidden="true" />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Empty + loading states.
// ─────────────────────────────────────────────────────────────────────────

function EmptyHistory() {
  return (
    <div className="px-4 py-8 text-center">
      <div className="mx-auto mb-2 inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted/40">
        <WalletIcon className="h-4 w-4 text-muted-foreground" />
      </div>
      <p className="text-xs font-medium text-foreground">No payments yet</p>
      <p className="text-[11px] text-muted-foreground">
        x402 transactions will appear here.
      </p>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <ul className="divide-y divide-border/40">
      {[0, 1, 2].map((i) => (
        <li
          key={i}
          className="flex items-center gap-2 px-4 py-2.5"
          aria-hidden="true"
        >
          <div className="flex-1 min-w-0 space-y-1">
            <div className="h-3 w-32 rounded bg-muted/50 animate-pulse" />
            <div className="h-2.5 w-16 rounded bg-muted/30 animate-pulse" />
          </div>
          <div className="h-3 w-14 rounded bg-muted/40 animate-pulse" />
          <span className="h-2 w-2 rounded-full bg-muted/50" />
        </li>
      ))}
    </ul>
  );
}
