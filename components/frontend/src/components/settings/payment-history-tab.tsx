/**
 * Payment History Settings Tab
 *
 * Renders the user's local on-chain payment history (Tempo via MPP-over-NATS).
 * Entries are written purely client-side by the payment modal (unit 13) into
 * `localStorage["syft_payment_history_v1"]`. This tab never makes a hub call.
 */

import { useCallback, useEffect, useState } from 'react';

import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';

import { Button } from '@/components/ui/button';
import { formatRelativeTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

// =============================================================================
// Constants
// =============================================================================

export const PAYMENT_HISTORY_STORAGE_KEY = 'syft_payment_history_v1';

const TX_EXPLORER_URL = 'https://explorer.tempo.example/tx';

// =============================================================================
// Types
// =============================================================================

export type PaymentHistoryStatus = 'verified' | 'failed' | 'required';

export interface PaymentHistoryEntry {
  timestamp: string;
  endpoint_slug: string;
  amount: string;
  currency: string;
  tx_hash: string;
  status: PaymentHistoryStatus;
}

// =============================================================================
// Helpers
// =============================================================================

function isValidEntry(entry: PaymentHistoryEntry | null | undefined): entry is PaymentHistoryEntry {
  return (
    entry !== null &&
    entry !== undefined &&
    typeof entry.timestamp === 'string' &&
    typeof entry.endpoint_slug === 'string' &&
    typeof entry.tx_hash === 'string'
  );
}

function parseEntries(raw: string | null): PaymentHistoryEntry[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Filter out malformed entries; sort newest first.
    return (parsed as PaymentHistoryEntry[])
      .filter((entry) => isValidEntry(entry))
      .toSorted((a, b) => b.timestamp.localeCompare(a.timestamp));
  } catch (error) {
    console.error('invalid payment history', error);
    return [];
  }
}

function truncate(value: string, head: number, tail = 0): string {
  if (value.length <= head + tail + 1) return value;
  if (tail === 0) return `${value.slice(0, head)}…`;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

// =============================================================================
// Status Badge
// =============================================================================

const STATUS_LABEL: Record<PaymentHistoryStatus, string> = {
  verified: 'Verified',
  failed: 'Failed',
  required: 'Required'
};

const STATUS_CLASS: Record<PaymentHistoryStatus, string> = {
  verified: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-500/15 dark:text-emerald-300',
  failed: 'bg-red-100 text-red-900 dark:bg-red-500/15 dark:text-red-300',
  required: 'bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-300'
};

function StatusBadge({ status }: Readonly<{ status: PaymentHistoryStatus }>) {
  const label = STATUS_LABEL[status];
  const cls = STATUS_CLASS[status];
  return (
    <span
      className={cn('inline-flex rounded-md px-2 py-0.5 text-xs font-semibold', cls)}
      data-testid={`payment-status-${status}`}
    >
      {label}
    </span>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function PaymentHistoryTab() {
  const [entries, setEntries] = useState<PaymentHistoryEntry[]>([]);

  // Initial load
  useEffect(() => {
    setEntries(parseEntries(localStorage.getItem(PAYMENT_HISTORY_STORAGE_KEY)));
  }, []);

  // Cross-tab sync: refresh when another tab writes a payment.
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key !== PAYMENT_HISTORY_STORAGE_KEY) return;
      setEntries(parseEntries(e.newValue));
    };
    globalThis.addEventListener('storage', handler);
    return () => {
      globalThis.removeEventListener('storage', handler);
    };
  }, []);

  const handleClear = useCallback(() => {
    localStorage.removeItem(PAYMENT_HISTORY_STORAGE_KEY);
    setEntries([]);
  }, []);

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-foreground text-lg font-semibold'>Payment History</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          On-chain payments you&apos;ve made for paid endpoints. Stored locally in this browser
          only.
        </p>
      </div>

      {entries.length === 0 ? (
        <div
          className='border-border bg-muted/30 rounded-lg border border-dashed p-8 text-center'
          data-testid='payment-history-empty'
        >
          <p className='text-foreground text-sm font-medium'>No payments yet.</p>
          <p className='text-muted-foreground mt-1 text-sm'>
            When you pay for a paid endpoint, it&apos;ll appear here.
          </p>
        </div>
      ) : (
        <>
          <div className='border-border overflow-hidden rounded-lg border'>
            <table className='w-full text-left text-sm' data-testid='payment-history-table'>
              <thead className='bg-muted text-muted-foreground text-xs uppercase'>
                <tr>
                  <th className='px-3 py-2 font-medium'>Time</th>
                  <th className='px-3 py-2 font-medium'>Endpoint</th>
                  <th className='px-3 py-2 font-medium'>Amount</th>
                  <th className='px-3 py-2 font-medium'>Currency</th>
                  <th className='px-3 py-2 font-medium'>Tx</th>
                  <th className='px-3 py-2 font-medium'>Status</th>
                </tr>
              </thead>
              <tbody className='divide-border divide-y'>
                {entries.map((entry) => (
                  <tr
                    key={`${entry.tx_hash}-${entry.timestamp}`}
                    className='hover:bg-muted/40'
                    data-testid='payment-history-row'
                  >
                    <td
                      className='text-muted-foreground px-3 py-2 whitespace-nowrap'
                      title={entry.timestamp}
                    >
                      {formatRelativeTime(entry.timestamp)}
                    </td>
                    <td className='text-foreground px-3 py-2 font-medium'>{entry.endpoint_slug}</td>
                    <td className='text-foreground px-3 py-2'>{entry.amount}</td>
                    <td
                      className='text-muted-foreground px-3 py-2 font-mono text-xs'
                      title={entry.currency}
                    >
                      {truncate(entry.currency, 8)}
                    </td>
                    <td className='px-3 py-2'>
                      <a
                        href={`${TX_EXPLORER_URL}/${entry.tx_hash}`}
                        target='_blank'
                        rel='noreferrer'
                        className='text-primary hover:text-primary/80 inline-flex items-center gap-1 font-mono text-xs'
                        title={entry.tx_hash}
                      >
                        {truncate(entry.tx_hash, 10)}
                        <ExternalLink className='h-3 w-3' aria-hidden='true' />
                      </a>
                    </td>
                    <td className='px-3 py-2'>
                      <StatusBadge status={entry.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className='flex justify-end'>
            <Button
              variant='outline'
              size='sm'
              onClick={handleClear}
              data-testid='payment-history-clear'
            >
              <Trash2 className='mr-2 h-3.5 w-3.5' aria-hidden='true' />
              Clear history
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
