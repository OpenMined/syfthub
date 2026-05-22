import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Wallet as WalletIcon,
} from 'lucide-react';
import { BrowserOpenURL } from '../../../wailsjs/runtime/runtime';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
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
import { PaymentCapsPanel } from './PaymentCapsPanel';

// ─────────────────────────────────────────────────────────────────────────────
// Local TS stubs for the wallet Wails bindings.
//
// These mirror the Go types declared in:
//   syfthub-desktop/wallet_operations.go (WalletInfo, WalletBalance)
//   syfthub-desktop/wallet_history.go    (PaymentRecord, TransactionFilter,
//                                          TransactionPage, PaymentTotals)
//
// The canonical TS definitions live in wailsjs/go/main/App.d.ts after a
// `wails build` regenerates the bindings. We declare them here so a plain
// `npm run build` (no wails step) still type-checks while U8/U11 land.
// ─────────────────────────────────────────────────────────────────────────────

export interface WalletInfo {
  address: string;
  chain_id: number;
  rpc_url: string;
  network: string;
  key_exists: boolean;
}

export interface WalletBalance {
  address: string;
  amount: string;
  currency: string;
  decimals: number;
  as_of_unix: number;
}

export interface PaymentRecord {
  id: string;
  timestamp_unix: number;
  endpoint_owner: string;
  endpoint_slug: string;
  endpoint_label?: string;
  amount: string;
  currency: string;
  chain_id: number;
  challenge_id: string;
  credential_hex: string;
  tx_hash?: string;
  status: string;
  failure_reason?: string;
  request_summary?: string;
  settled_unix?: number;
}

export interface TransactionFilter {
  endpoint_slug?: string;
  status?: string;
  since_unix?: number;
  until_unix?: number;
  limit?: number;
}

export interface PaymentTotals {
  spent_lifetime: string;
  spent_month: string;
  spent_session: string;
}

export interface TransactionPage {
  records: PaymentRecord[];
  total: number;
  totals: PaymentTotals;
}

type DateRange = '24h' | '7d' | '30d' | 'all';
type StatusFilter =
  | 'all'
  | 'signed'
  | 'broadcast'
  | 'settled'
  | 'failed'
  | 'refunded';

// PAGE_SIZE controls both the initial page and each "Show more" increment.
// The backend clamps at maxHistoryLimit=500; we stay well under that.
const PAGE_SIZE = 50;

// FUND_URL is the testnet faucet — opened in the user's default browser via
// the Wails BrowserOpenURL runtime so we don't rely on a real <a target>.
const FUND_URL = 'https://tempo.xyz/fund';

// EXPLORER_TX_PREFIX wraps a tx hash into the testnet block explorer link.
// Empty/missing hashes are rendered without a link.
const EXPLORER_TX_PREFIX = 'https://explorer.testnet.tempo.xyz/tx/';

// callWailsMethod invokes a named Wails binding. Throws when the binding is
// missing so the caller can surface a clear error to the user.
async function callWailsMethod<T>(name: string, ...args: unknown[]): Promise<T> {
  const w = window as unknown as {
    go?: { main?: { App?: Record<string, (...a: unknown[]) => Promise<T>> } };
  };
  const fn = w.go?.main?.App?.[name];
  if (typeof fn !== 'function') {
    throw new Error(`Wails method ${name} is not bound`);
  }
  return fn(...args);
}

// truncateMiddle shortens long strings (addresses, tx hashes) by keeping the
// head and tail and replacing the middle with an ellipsis. Strings shorter
// than head+tail+3 are returned unchanged.
function truncateMiddle(value: string, head = 6, tail = 4): string {
  if (!value) return '';
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

// formatRelative renders a unix timestamp as a coarse relative-time string
// ("12s ago", "3m ago", …). For consistency with the rest of the app we
// stay coarse: anything older than a day reads as the full date.
function formatRelative(unix: number): string {
  if (!unix) return '';
  const now = Math.floor(Date.now() / 1000);
  const diff = Math.max(0, now - unix);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86_400) return `${Math.floor(diff / 3600)}h ago`;
  const d = new Date(unix * 1000);
  return d.toISOString().slice(0, 10);
}

// formatIso returns a stable, full ISO-8601 timestamp suitable for the
// timestamp column's hover tooltip.
function formatIso(unix: number): string {
  if (!unix) return '';
  return new Date(unix * 1000).toISOString();
}

// dateRangeToSince converts the dropdown selection into a unix epoch lower
// bound for TransactionFilter.since_unix. 'all' returns 0 → filter is dropped.
function dateRangeToSince(range: DateRange): number {
  const now = Math.floor(Date.now() / 1000);
  switch (range) {
    case '24h':
      return now - 86_400;
    case '7d':
      return now - 7 * 86_400;
    case '30d':
      return now - 30 * 86_400;
    case 'all':
    default:
      return 0;
  }
}

// statusVariant picks a badge variant based on the payment status. Settled
// gets the default-secondary lookalike (chart-2), broadcast a pending hue,
// failed/refunded reuse destructive/muted.
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'settled':
      return 'border-chart-2/40 bg-chart-2/15 text-chart-2';
    case 'broadcast':
      return 'border-chart-3/40 bg-chart-3/15 text-chart-3';
    case 'signed':
      return 'border-primary/30 bg-primary/10 text-primary';
    case 'failed':
      return 'border-destructive/40 bg-destructive/15 text-destructive';
    case 'refunded':
      return 'border-muted-foreground/30 bg-muted/30 text-muted-foreground';
    default:
      return 'border-border bg-secondary/40 text-foreground';
  }
}

// pathUSDLabel resolves the on-chain currency address to a display label.
// The empty-string branch keeps the column readable while a row is still
// settling and has no currency stamped on it yet.
function currencyLabel(currency: string): string {
  if (!currency) return '';
  return 'pathUSD';
}

// useDebouncedValue returns a value that updates only after `delay` ms of
// stability on the input. Used to keep the filter inputs from issuing a
// Wails round-trip on every keystroke.
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function WalletTab() {
  // ── State ────────────────────────────────────────────────────────────────
  const [walletInfo, setWalletInfo] = useState<WalletInfo | null>(null);
  const [balance, setBalance] = useState<WalletBalance | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [initRunning, setInitRunning] = useState(false);
  const [copiedAddress, setCopiedAddress] = useState(false);

  // Filter inputs (raw user values).
  const [dateRange, setDateRange] = useState<DateRange>('30d');
  const [endpointFilter, setEndpointFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [limit, setLimit] = useState<number>(PAGE_SIZE);

  // Debounce the free-form endpoint filter only; the date/status dropdowns
  // change rarely and re-query immediately.
  const debouncedEndpointFilter = useDebouncedValue(endpointFilter, 300);

  // History query result + loading state.
  const [page, setPage] = useState<TransactionPage | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [exportRunning, setExportRunning] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [capsOpen, setCapsOpen] = useState(false);

  // historyAbort is bumped on each new query to invalidate stale completions.
  // We compare the captured token in the async block; mismatch → drop result.
  const historyToken = useRef(0);

  // Derived: the canonical TransactionFilter shipped to the backend.
  const filter: TransactionFilter = useMemo(
    () => ({
      endpoint_slug: debouncedEndpointFilter.trim() || undefined,
      status: statusFilter === 'all' ? undefined : statusFilter,
      since_unix: dateRangeToSince(dateRange) || undefined,
      limit,
    }),
    [debouncedEndpointFilter, statusFilter, dateRange, limit]
  );

  // ── Wallet info / balance ────────────────────────────────────────────────

  const refreshWallet = useCallback(async () => {
    setWalletLoading(true);
    setWalletError(null);
    try {
      const info = await callWailsMethod<WalletInfo>('WalletShow');
      setWalletInfo(info);
      if (info.key_exists) {
        try {
          const b = await callWailsMethod<WalletBalance>('WalletBalance');
          setBalance(b);
        } catch (err) {
          // Balance failures are non-fatal — the wallet card still renders.
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
      setWalletLoading(false);
    }
  }, []);

  const initWallet = useCallback(async () => {
    setInitRunning(true);
    setWalletError(null);
    try {
      await callWailsMethod<WalletInfo>('WalletInit');
      await refreshWallet();
    } catch (err) {
      setWalletError(
        err instanceof Error ? err.message : 'Failed to initialize wallet'
      );
    } finally {
      setInitRunning(false);
    }
  }, [refreshWallet]);

  useEffect(() => {
    void refreshWallet();
  }, [refreshWallet]);

  const copyAddress = useCallback(async () => {
    if (!walletInfo?.address) return;
    try {
      await navigator.clipboard.writeText(walletInfo.address);
      setCopiedAddress(true);
      setTimeout(() => setCopiedAddress(false), 1500);
    } catch {
      // Clipboard can fail in restricted contexts; nothing actionable.
    }
  }, [walletInfo?.address]);

  const openFundUrl = useCallback(() => {
    BrowserOpenURL(FUND_URL);
  }, []);

  // ── Transaction history ──────────────────────────────────────────────────

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
      // Backend may return `null` for an empty result depending on Go marshal —
      // normalise to an empty array so the render code can iterate freely.
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
      if (token !== historyToken.current) return;
      setHistoryError(
        err instanceof Error ? err.message : 'Failed to load history'
      );
      setPage(null);
    } finally {
      if (token === historyToken.current) {
        setHistoryLoading(false);
      }
    }
  }, [filter]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  // Reset the limit (and therefore drop pagination back to one page) when any
  // filter besides limit itself changes. Without this, narrowing a filter
  // would still ask for the previously-grown limit.
  useEffect(() => {
    setLimit(PAGE_SIZE);
  }, [debouncedEndpointFilter, statusFilter, dateRange]);

  const onShowMore = () => {
    setLimit((prev) => prev + PAGE_SIZE);
  };

  const onExportCsv = async () => {
    setExportRunning(true);
    setExportError(null);
    try {
      // Export ignores the limit field — the backend exports every matching
      // row. We strip limit defensively to keep the request shape minimal.
      const exportFilter: TransactionFilter = { ...filter };
      delete exportFilter.limit;
      const csv = await callWailsMethod<string>(
        'TransactionHistoryExportCSV',
        exportFilter
      );
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `syfthub-wallet-${new Date()
        .toISOString()
        .replace(/[:.]/g, '-')}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Defer revoke so the browser has time to start the download — Chrome
      // sometimes drops the blob if revoked synchronously.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : 'Failed to export CSV'
      );
    } finally {
      setExportRunning(false);
    }
  };

  const records = page?.records ?? [];
  const totals = page?.totals;
  const showingMore = limit > PAGE_SIZE;
  // canLoadMore — there's more rows available than we currently have.
  // page.total is the count matching the filter ignoring the limit.
  const canLoadMore = (page?.total ?? 0) > records.length;

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        {/* Header card */}
        <WalletHeaderCard
          info={walletInfo}
          balance={balance}
          loading={walletLoading}
          error={walletError}
          initRunning={initRunning}
          copied={copiedAddress}
          onRefresh={refreshWallet}
          onCopyAddress={copyAddress}
          onFund={openFundUrl}
          onInit={initWallet}
        />

        {/* Filters */}
        <section className="rounded-xl border border-border bg-card/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-foreground">
            Filter transactions
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label
                htmlFor="wallet-date-range"
                className="mb-1 block text-xs font-medium text-muted-foreground"
              >
                Date range
              </label>
              <Select
                value={dateRange}
                onValueChange={(v) => setDateRange(v as DateRange)}
              >
                <SelectTrigger
                  id="wallet-date-range"
                  className="h-9 w-full"
                >
                  <SelectValue placeholder="Date range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24h">Last 24h</SelectItem>
                  <SelectItem value="7d">Last 7 days</SelectItem>
                  <SelectItem value="30d">Last 30 days</SelectItem>
                  <SelectItem value="all">All time</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label
                htmlFor="wallet-endpoint-filter"
                className="mb-1 block text-xs font-medium text-muted-foreground"
              >
                Endpoint slug
              </label>
              <Input
                id="wallet-endpoint-filter"
                type="text"
                value={endpointFilter}
                onChange={(e) => setEndpointFilter(e.target.value)}
                placeholder="endpoint-slug"
              />
            </div>
            <div>
              <label
                htmlFor="wallet-status-filter"
                className="mb-1 block text-xs font-medium text-muted-foreground"
              >
                Status
              </label>
              <Select
                value={statusFilter}
                onValueChange={(v) => setStatusFilter(v as StatusFilter)}
              >
                <SelectTrigger
                  id="wallet-status-filter"
                  className="h-9 w-full"
                >
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="signed">Signed</SelectItem>
                  <SelectItem value="broadcast">Broadcast</SelectItem>
                  <SelectItem value="settled">Settled</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="refunded">Refunded</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </section>

        {/* Transaction history */}
        <section className="rounded-xl border border-border bg-card/40">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">
              Transaction history
            </h2>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {historyLoading && <Loader2 className="h-3 w-3 animate-spin" />}
              {page && (
                <span>
                  Showing {records.length} of {page.total}
                </span>
              )}
            </div>
          </div>

          {historyError ? (
            <div className="px-4 py-6 text-sm text-destructive">
              {historyError}
            </div>
          ) : historyLoading && records.length === 0 ? (
            <HistorySkeleton />
          ) : records.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No payments yet.
            </div>
          ) : (
            <HistoryTable records={records} />
          )}

          {canLoadMore && !historyLoading && (
            <div className="border-t border-border px-4 py-3 text-center">
              <Button variant="secondary" size="sm" onClick={onShowMore}>
                Show more
              </Button>
            </div>
          )}
          {showingMore && !canLoadMore && records.length > 0 && (
            <div className="border-t border-border px-4 py-2 text-center text-xs text-muted-foreground">
              End of history.
            </div>
          )}

          {/* Totals footer */}
          <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-muted-foreground">
              {totals ? (
                <span>
                  Session: <span className="text-foreground">{totals.spent_session} pathUSD</span> ·
                  {' '}
                  Month: <span className="text-foreground">{totals.spent_month} pathUSD</span> ·
                  {' '}
                  Lifetime: <span className="text-foreground">{totals.spent_lifetime} pathUSD</span>
                </span>
              ) : (
                <span>Totals unavailable</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {exportError && (
                <span className="text-xs text-destructive">{exportError}</span>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={onExportCsv}
                disabled={exportRunning}
              >
                {exportRunning ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Download className="h-3 w-3" />
                )}
                Export CSV
              </Button>
            </div>
          </div>
        </section>

        {/* Caps subsection (collapsible, default collapsed) */}
        <section className="rounded-xl border border-border bg-card/40">
          <button
            type="button"
            onClick={() => setCapsOpen((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-foreground"
            aria-expanded={capsOpen}
            aria-controls="wallet-caps-content"
          >
            <span className="flex items-center gap-2">
              {capsOpen ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              Per-endpoint payment caps
            </span>
            <span className="text-xs text-muted-foreground">
              {capsOpen ? 'Hide' : 'Show'}
            </span>
          </button>
          {capsOpen && (
            <div id="wallet-caps-content" className="border-t border-border p-4">
              <PaymentCapsPanel recentRecords={records} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────

interface WalletHeaderCardProps {
  info: WalletInfo | null;
  balance: WalletBalance | null;
  loading: boolean;
  error: string | null;
  initRunning: boolean;
  copied: boolean;
  onRefresh: () => void;
  onCopyAddress: () => void;
  onFund: () => void;
  onInit: () => void;
}

function WalletHeaderCard({
  info,
  balance,
  loading,
  error,
  initRunning,
  copied,
  onRefresh,
  onCopyAddress,
  onFund,
  onInit,
}: WalletHeaderCardProps) {
  const hasWallet = Boolean(info?.key_exists);

  return (
    <section className="rounded-xl border border-border bg-card/40 p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <WalletIcon className="h-4 w-4 text-muted-foreground" />
            <h1 className="text-base font-semibold text-foreground">Wallet</h1>
            <Badge variant="secondary" className="text-[10px] uppercase">
              {info?.network ?? 'tempo-testnet'}
            </Badge>
          </div>

          {loading && !info ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading wallet…
            </div>
          ) : hasWallet ? (
            <div className="space-y-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onCopyAddress}
                    className="group flex items-center gap-2 rounded-md text-left font-mono text-xs text-muted-foreground hover:text-foreground"
                  >
                    <span className="select-all">
                      {truncateMiddle(info!.address, 10, 8)}
                    </span>
                    {copied ? (
                      <Check className="h-3 w-3 text-chart-2" />
                    ) : (
                      <Copy className="h-3 w-3 opacity-50 group-hover:opacity-100" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p className="font-mono text-xs">{info!.address}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {copied ? 'Copied' : 'Click to copy'}
                  </p>
                </TooltipContent>
              </Tooltip>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-semibold text-foreground">
                  {balance?.amount ?? '—'}
                </span>
                <span className="text-sm text-muted-foreground">pathUSD</span>
              </div>
              {balance?.as_of_unix ? (
                <p className="text-[10px] text-muted-foreground">
                  As of {formatRelative(balance.as_of_unix)}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                No wallet found. Initialize one to start signing payments.
              </p>
            </div>
          )}

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {hasWallet ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={onRefresh}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="h-3 w-3" />
                )}
                Refresh
              </Button>
              <Button variant="secondary" size="sm" onClick={onFund}>
                <ExternalLink className="h-3 w-3" />
                Fund
              </Button>
            </>
          ) : (
            <Button
              variant="default"
              size="sm"
              onClick={onInit}
              disabled={initRunning}
            >
              {initRunning ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <WalletIcon className="h-3 w-3" />
              )}
              Initialize wallet
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-2 px-4 py-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="h-10 animate-pulse rounded-md bg-secondary/30"
        />
      ))}
    </div>
  );
}

interface HistoryTableProps {
  records: PaymentRecord[];
}

function HistoryTable({ records }: HistoryTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-secondary/30 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Timestamp</th>
            <th className="px-3 py-2 text-left font-medium">Endpoint</th>
            <th className="px-3 py-2 text-right font-medium">Amount</th>
            <th className="px-3 py-2 text-left font-medium">Status</th>
            <th className="px-3 py-2 text-left font-medium">Tx</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id} className="border-t border-border/60 hover:bg-secondary/20">
              <td className="px-3 py-2 align-top">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-default text-foreground">
                      {formatRelative(r.timestamp_unix)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p className="font-mono text-xs">
                      {formatIso(r.timestamp_unix)}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </td>
              <td className="px-3 py-2 align-top">
                <div className="font-medium text-foreground">
                  {r.endpoint_label || r.endpoint_slug || '—'}
                </div>
                <div className="text-xs text-muted-foreground">
                  {r.endpoint_owner ? `${r.endpoint_owner}/` : ''}
                  {r.endpoint_slug}
                </div>
              </td>
              <td className="px-3 py-2 text-right align-top">
                <div className="text-foreground">{r.amount || '—'}</div>
                <div className="text-xs text-muted-foreground">
                  {currencyLabel(r.currency)}
                </div>
              </td>
              <td className="px-3 py-2 align-top">
                <Badge
                  variant="outline"
                  className={`text-[10px] uppercase ${statusBadgeClass(r.status)}`}
                >
                  {r.status || 'unknown'}
                </Badge>
                {r.failure_reason && (
                  <div className="mt-1 text-xs text-destructive">
                    {r.failure_reason}
                  </div>
                )}
              </td>
              <td className="px-3 py-2 align-top">
                {r.tx_hash ? (
                  <button
                    type="button"
                    onClick={() =>
                      BrowserOpenURL(`${EXPLORER_TX_PREFIX}${r.tx_hash}`)
                    }
                    className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
                  >
                    {truncateMiddle(r.tx_hash, 6, 4)}
                    <ExternalLink className="h-3 w-3" />
                  </button>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default WalletTab;
