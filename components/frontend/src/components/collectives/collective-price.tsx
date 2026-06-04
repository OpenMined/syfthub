/**
 * CollectivePrice
 *
 * Compact estimated-price badge for a collective shared endpoint. Every member
 * bills per request, so this sums all participating endpoints' per-request
 * prices grouped per currency (distinct currencies are never converted — they
 * render as a sum list, e.g. `10,000 IDR + 10 USD`). Free members add nothing
 * and surface as a quiet `· N free` suffix.
 *
 * Renders nothing while loading or when there are no participating members, so
 * callers can drop it inline without guarding.
 */
import type { CollectiveBillingSummary, PriceByCurrency } from '@/lib/collectives-api';

import Coins from 'lucide-react/dist/esm/icons/coins';

import { cn } from '@/lib/utils';

/** Format one currency slice as `10,000 IDR` (code as suffix, no FX). */
export function formatPriceSlice(entry: PriceByCurrency): string {
  const amount = new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 2
  }).format(entry.amount);
  return `${amount} ${entry.currency}`;
}

/** Join per-currency slices into `10,000 IDR + 10 EUR`. */
export function formatEstimatedPrice(entries: PriceByCurrency[]): string {
  return entries.map((entry) => formatPriceSlice(entry)).join(' + ');
}

export interface CollectivePriceProps {
  summary: CollectiveBillingSummary | null | undefined;
  isLoading?: boolean;
  className?: string;
  /** Show the quiet `· N free` suffix. Disabled on the default API to keep it simple. */
  showFreeCount?: boolean;
}

export function CollectivePrice({
  summary,
  isLoading = false,
  className,
  showFreeCount = true
}: Readonly<CollectivePriceProps>) {
  if (isLoading || !summary) return null;

  const totalMembers = summary.free_count + summary.prepaid_count + summary.mpp_count;
  if (totalMembers === 0) return null;

  const allFree = summary.estimated_price.length === 0;

  // Quiet suffix for members that don't add to the per-request price.
  const extras: string[] = [];
  if (showFreeCount && summary.free_count > 0 && !allFree) {
    extras.push(`${String(summary.free_count)} free`);
  }

  const entries = summary.estimated_price;
  const multiCurrency = entries.length > 1;
  const [firstEntry] = entries;
  const tooltip = allFree
    ? 'No payment required'
    : multiCurrency
      ? 'Each endpoint is billed in its own currency — amounts are not converted.'
      : 'Estimated cost to query this Collective API';

  return (
    <span
      className={cn(
        'font-inter inline-flex flex-wrap items-center gap-1.5 text-xs font-medium',
        allFree ? 'text-emerald-600 dark:text-emerald-400' : 'text-foreground',
        className
      )}
      title={tooltip}
    >
      <Coins className='text-muted-foreground h-3 w-3 shrink-0' aria-hidden='true' />
      {allFree ? (
        <span>Free</span>
      ) : multiCurrency ? (
        <>
          {entries.map((entry) => (
            <span
              key={entry.currency}
              className='bg-muted text-foreground rounded px-1.5 py-0.5 tabular-nums'
            >
              {formatPriceSlice(entry)}
            </span>
          ))}
          <span className='text-muted-foreground font-normal'>per request</span>
        </>
      ) : firstEntry ? (
        <span className='tabular-nums'>~{formatPriceSlice(firstEntry)} / request</span>
      ) : null}
      {extras.length > 0 && (
        <span className='text-muted-foreground font-normal'>· {extras.join(' · ')}</span>
      )}
    </span>
  );
}
