// Producer-side receipts table for an X402PayPerRequestPolicy.
//
// Each row is one verified/settled/failed transaction the Python policy
// has written to the endpoint's policy/store.db SQLite ledger; we read
// it through the Go-side GetPolicyReceipts binding.
//
// Pagination here is page-cap based (the Go binding returns the first
// N rows ordered by created_at DESC plus the total count). A 'Show
// more' button bumps the limit until the cap is hit; an explicit
// refresh button is provided in lieu of polling so the producer
// controls when the network is touched.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, ExternalLink, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Tempo testnet explorer — used to build the tx-hash link. Picked
// conservatively (no link if we don't know the chain) so we never
// open a wrong-network page.
const TEMPO_TESTNET_CHAIN_ID = 42431;
const TEMPO_TESTNET_TX_URL = (hash: string) =>
  `https://explore.tempo.xyz/tx/${hash}`;

const PAGE_SIZE = 50;
const MAX_RECEIPTS = 500;

interface Receipt {
  id: string;
  payer: string;
  pay_to: string;
  amount: string;
  currency: string;
  chain_id: number;
  nonce: number;
  challenge_id: string;
  status: string;
  failure_reason?: string;
  tx_hash?: string;
  created_at: string;
  settled_at?: string;
}

interface ReceiptPage {
  records: Receipt[];
  total: number;
}

interface WailsApp {
  GetPolicyReceipts: (
    slug: string,
    policyName: string,
    filter: { status?: string; payer?: string; limit?: number },
  ) => Promise<ReceiptPage>;
}

function wailsApp(): WailsApp {
  return (window as unknown as { go: { main: { App: WailsApp } } }).go.main.App;
}

// formatRelativeTime is intentionally tiny — the cross-file copies
// flagged in MEMORY.md live in the consumer codebase. Keeping a small
// local one avoids importing from there and tangling the build graph.
function formatRelativeTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const diff = Date.now() - ts;
  if (diff < 60_000) return 'just now';
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(ts).toLocaleDateString();
}

function truncate(value: string, head = 6, tail = 4): string {
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

function statusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case 'settled':
      return { label: 'settled', className: 'bg-primary/15 text-primary' };
    case 'failed':
      return { label: 'failed', className: 'bg-destructive/15 text-destructive' };
    case 'verified':
      return { label: 'verified', className: 'bg-chart-3/15 text-chart-3' };
    default:
      return { label: status, className: 'bg-secondary/50 text-muted-foreground' };
  }
}

export interface X402ReceiptsPanelProps {
  endpointSlug: string;
  policyName: string;
}

export function X402ReceiptsPanel({ endpointSlug, policyName }: X402ReceiptsPanelProps) {
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [payerFilter, setPayerFilter] = useState('');
  const [limit, setLimit] = useState<number>(PAGE_SIZE);
  const [page, setPage] = useState<ReceiptPage>({ records: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReceipts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await wailsApp().GetPolicyReceipts(endpointSlug, policyName, {
        status: statusFilter === 'all' ? '' : statusFilter,
        payer: payerFilter.trim(),
        limit,
      });
      // The Go binding always returns a well-formed object, but be
      // defensive against a future shape change.
      setPage({
        records: Array.isArray(result?.records) ? result.records : [],
        total: typeof result?.total === 'number' ? result.total : 0,
      });
    } catch (err) {
      setError(`${err}`);
      setPage({ records: [], total: 0 });
    } finally {
      setLoading(false);
    }
  }, [endpointSlug, policyName, statusFilter, payerFilter, limit]);

  useEffect(() => {
    fetchReceipts();
  }, [fetchReceipts]);

  const visibleCount = page.records.length;
  const canShowMore =
    visibleCount < page.total && limit < MAX_RECEIPTS;

  const handleCopyHash = async (hash: string) => {
    try {
      await navigator.clipboard.writeText(hash);
    } catch {
      // Clipboard can fail in restricted contexts; the user can still
      // open the explorer link as a fallback.
    }
  };

  const totalLabel = useMemo(() => {
    if (page.total === 0) return '0 receipts';
    if (visibleCount === page.total) return `${page.total} receipt${page.total === 1 ? '' : 's'}`;
    return `Showing ${visibleCount} of ${page.total}`;
  }, [page.total, visibleCount]);

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="verified">Verified</SelectItem>
              <SelectItem value="settled">Settled</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Input
          value={payerFilter}
          onChange={(e) => setPayerFilter(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') fetchReceipts();
          }}
          placeholder="Filter payer…"
          className="h-8 w-48 text-xs font-mono"
        />
        <div className="flex-1" />
        <span className="text-xs text-muted-foreground">{totalLabel}</span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setLimit(PAGE_SIZE);
            fetchReceipts();
          }}
          disabled={loading}
          className="h-8 text-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {loading && page.records.length === 0 ? (
        <div className="py-8 text-center text-xs text-muted-foreground">Loading receipts…</div>
      ) : page.records.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-sm text-muted-foreground">No receipts yet</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Payers will appear here when they pay.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-border/40">
                <th className="text-left font-medium py-1.5 pr-3">When</th>
                <th className="text-left font-medium py-1.5 pr-3">Payer</th>
                <th className="text-left font-medium py-1.5 pr-3">Amount</th>
                <th className="text-left font-medium py-1.5 pr-3">Status</th>
                <th className="text-left font-medium py-1.5">Tx hash</th>
              </tr>
            </thead>
            <tbody>
              {page.records.map((r) => {
                const badge = statusBadge(r.status);
                const hasHash = !!r.tx_hash;
                const explorerHref =
                  hasHash && r.chain_id === TEMPO_TESTNET_CHAIN_ID
                    ? TEMPO_TESTNET_TX_URL(r.tx_hash!)
                    : null;
                return (
                  <tr key={r.id} className="border-b border-border/20 hover:bg-card/40">
                    <td
                      className="py-1.5 pr-3 whitespace-nowrap"
                      title={r.created_at}
                    >
                      {formatRelativeTime(r.created_at)}
                    </td>
                    <td className="py-1.5 pr-3 font-mono" title={r.payer}>
                      {truncate(r.payer, 8, 4)}
                    </td>
                    <td className="py-1.5 pr-3 font-mono" title={r.currency}>
                      {r.amount}
                    </td>
                    <td className="py-1.5 pr-3">
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] ${badge.className}`}
                        title={r.failure_reason || ''}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td className="py-1.5">
                      {hasHash ? (
                        <span className="inline-flex items-center gap-1.5 font-mono">
                          <button
                            type="button"
                            onClick={() => handleCopyHash(r.tx_hash!)}
                            className="hover:text-primary"
                            title="Copy hash"
                          >
                            {truncate(r.tx_hash!, 6, 4)}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleCopyHash(r.tx_hash!)}
                            className="text-muted-foreground hover:text-foreground"
                            title="Copy hash"
                            aria-label="Copy transaction hash"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                          {explorerHref && (
                            <a
                              href={explorerHref}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="text-muted-foreground hover:text-foreground"
                              title="Open in Tempo explorer"
                              aria-label="Open in Tempo explorer"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {canShowMore && (
        <div className="flex justify-center pt-2">
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            disabled={loading}
            onClick={() => setLimit(Math.min(limit + PAGE_SIZE, MAX_RECEIPTS))}
          >
            Show more
          </Button>
        </div>
      )}
    </div>
  );
}
