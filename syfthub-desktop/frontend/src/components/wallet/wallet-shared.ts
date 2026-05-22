// Shared types + helpers for the wallet UI surfaces (header popover + deep
// settings page). Both consume the same Wails bindings; keeping these in
// one place prevents drift on field names and display-formatting rules.

// ─────────────────────────────────────────────────────────────────────────
// Wails binding stubs — mirror the Go types in syfthub-desktop's
// wallet_operations.go and wallet_history.go. The canonical TS definitions
// live in wailsjs/go/main/App.d.ts after a `wails build`; declaring them
// here keeps `npm run build` type-clean even when the bindings file is
// briefly out of sync.
// ─────────────────────────────────────────────────────────────────────────

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

export interface FundResult {
  address: string;
  hashes: string[];
  network: string;
  faucet_url: string;
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

export type DateRange = '24h' | '7d' | '30d' | 'all';

export type StatusFilter =
  | 'all'
  | 'signed'
  | 'broadcast'
  | 'settled'
  | 'failed'
  | 'refunded';

// EXPLORER_TX_PREFIX builds explorer URLs for tx hashes. Empty hashes are
// rendered without a link by the consuming components.
export const EXPLORER_TX_PREFIX = 'https://explore.tempo.xyz/tx/';

// FUND_URL is the human-facing faucet page (programmatic faucet calls go
// through the WalletFund Wails method; this is the fallback link).
export const FUND_URL = 'https://wallet.tempo.xyz/faucet';

// FUND_BALANCE_REFRESH_DELAY_MS waits one Tempo block (~5s) before
// reloading the balance after a successful WalletFund call so the user
// sees the new balance without manually refreshing.
export const FUND_BALANCE_REFRESH_DELAY_MS = 6000;

// PATH_USD_CONTRACT mirrors wallet_operations.go's pathUSDContractAddress.
// Used to render "pathUSD" when the on-chain currency address matches.
const PATH_USD_CONTRACT = '0x20c0000000000000000000000000000000000000';

// callWailsMethod invokes a named Wails binding via the runtime-injected
// window.go.main.App map. Throws when the binding is missing so callers can
// surface a clear error rather than a silent failure.
export async function callWailsMethod<T>(
  name: string,
  ...args: unknown[]
): Promise<T> {
  const w = window as unknown as {
    go?: { main?: { App?: Record<string, (...a: unknown[]) => Promise<T>> } };
  };
  const fn = w.go?.main?.App?.[name];
  if (typeof fn !== 'function') {
    throw new Error(`Wails method ${name} is not bound`);
  }
  return fn(...args);
}

// truncateMiddle keeps the head + tail of a long string (address, tx hash)
// and replaces the middle with an ellipsis. Strings shorter than the
// combined head + tail + 3 are returned unchanged.
export function truncateMiddle(value: string, head = 6, tail = 4): string {
  if (!value) return '';
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

// formatRelative renders a unix timestamp as a coarse relative-time string
// ("12s ago", "3m ago", …). Anything older than 24h falls back to the
// ISO date — long-term browsing happens in the deep settings page, not
// here, so we never need a multi-day relative format.
export function formatRelative(unix: number): string {
  if (!unix) return '';
  const now = Math.floor(Date.now() / 1000);
  const diff = Math.max(0, now - unix);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86_400) return `${Math.floor(diff / 3600)}h ago`;
  const d = new Date(unix * 1000);
  return d.toISOString().slice(0, 10);
}

// formatIso returns a stable, full ISO-8601 timestamp suitable for hover
// tooltips next to the relative-time display.
export function formatIso(unix: number): string {
  if (!unix) return '';
  return new Date(unix * 1000).toISOString();
}

// dateRangeToSince converts the dropdown selection into a unix epoch lower
// bound for TransactionFilter.since_unix. 'all' returns 0 → filter is
// dropped by the Go side.
export function dateRangeToSince(range: DateRange): number {
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

// currencyLabel resolves an on-chain currency address into a display
// label. Recognises pathUSD by exact (case-insensitive) match; everything
// else falls back to a truncated address so an unknown token still reads
// usefully in the UI.
export function currencyLabel(currency: string): string {
  if (!currency) return '';
  if (currency.toLowerCase() === PATH_USD_CONTRACT) return 'pathUSD';
  return truncateMiddle(currency, 6, 4);
}

// statusDotClass picks the dot color for a payment row. We use a dot
// (not a full badge) in the popover so the row stays compact; the deep
// settings page uses the full badge variant.
export function statusDotClass(status: string): string {
  switch (status) {
    case 'settled':
      return 'bg-chart-2';
    case 'broadcast':
    case 'signed':
      return 'bg-chart-3';
    case 'failed':
      return 'bg-destructive';
    case 'refunded':
      return 'bg-muted-foreground/60';
    default:
      return 'bg-muted-foreground/40';
  }
}

// statusBadgeClass picks border + background + text classes for a full
// status badge — used by the deep settings page's transaction table.
export function statusBadgeClass(status: string): string {
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
