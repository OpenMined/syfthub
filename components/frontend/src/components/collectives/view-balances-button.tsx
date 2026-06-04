/**
 * ViewBalancesButton
 *
 * Opens the "your accounts" modal for a Collective API and colours itself by
 * whether the user can currently query that API:
 *   - green  → settled with every paid member (ready to query)
 *   - red    → at least one paid account needs funding (blocked)
 *   - neutral → still checking / nothing to check
 *
 * Renders nothing when the Collective API has no paid members (free APIs need
 * no settlement). Owns its own modal so it can be dropped into any card/row.
 */
import { useState } from 'react';

import type { CollectiveBillingSummary } from '@/lib/collectives-api';

import Wallet from 'lucide-react/dist/esm/icons/wallet';

import { useCollectiveQueryReadiness } from '@/hooks/use-collective-query-readiness';
import { cn } from '@/lib/utils';

import { CollectiveAccountsModal } from './collective-accounts-modal';

export interface ViewBalancesButtonProps {
  collectiveSlug: string;
  /** Omit for the default `collective/<slug>` Collective API (all members). */
  sharedSlug?: string;
  /** Human label for the Collective API (path or name) shown in the modal. */
  title?: string;
  summary: CollectiveBillingSummary | null | undefined;
  /** Extra classes for sizing/layout (e.g. `w-full` in the sidebar card). */
  className?: string;
}

export function ViewBalancesButton({
  collectiveSlug,
  sharedSlug,
  title,
  summary,
  className
}: Readonly<ViewBalancesButtonProps>) {
  const [open, setOpen] = useState(false);
  const hasPaidMembers = summary != null && (summary.prepaid_count > 0 || summary.mpp_count > 0);
  const status = useCollectiveQueryReadiness(summary, hasPaidMembers);

  if (!hasPaidMembers) return null;

  const tone =
    status === 'ready'
      ? 'border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/30'
      : status === 'blocked'
        ? 'border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/30'
        : 'border-border text-muted-foreground hover:bg-accent';

  const hint =
    status === 'ready'
      ? 'You can query this Collective API'
      : status === 'blocked'
        ? 'Settlement required before you can query this Collective API'
        : 'Checking your accounts…';

  return (
    <>
      <button
        type='button'
        onClick={() => {
          setOpen(true);
        }}
        title={hint}
        aria-label={hint}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
          tone,
          className
        )}
      >
        <Wallet className='h-3.5 w-3.5 shrink-0' aria-hidden='true' />
        Balances
      </button>
      <CollectiveAccountsModal
        isOpen={open}
        onClose={() => {
          setOpen(false);
        }}
        collectiveSlug={collectiveSlug}
        sharedSlug={sharedSlug}
        title={title}
      />
    </>
  );
}
