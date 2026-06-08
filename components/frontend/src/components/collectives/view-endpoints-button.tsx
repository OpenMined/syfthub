/**
 * ViewEndpointsButton
 *
 * Opens a modal listing every member endpoint under a Collective API. Owns its
 * own modal and feeds off the billing summary the parent already fetched, so
 * it can be dropped into any card/row. Renders nothing when the API has no
 * members.
 */
import { useState } from 'react';

import type { CollectiveBillingSummary } from '@/lib/collectives-api';

import Layers from 'lucide-react/dist/esm/icons/layers';

import { cn } from '@/lib/utils';

import { CollectiveEndpointsModal } from './collective-endpoints-modal';

export interface ViewEndpointsButtonProps {
  summary: CollectiveBillingSummary | null | undefined;
  /** Human label for the Collective API (path or name). */
  title?: string;
  /** Extra classes for sizing/layout (e.g. `w-full` in the sidebar card). */
  className?: string;
}

export function ViewEndpointsButton({
  summary,
  title,
  className
}: Readonly<ViewEndpointsButtonProps>) {
  const [open, setOpen] = useState(false);
  const count = summary?.members.length ?? 0;
  if (count === 0) return null;

  return (
    <>
      <button
        type='button'
        onClick={() => {
          setOpen(true);
        }}
        title='View the endpoints this Collective API fans out to'
        className={cn(
          'text-muted-foreground hover:bg-accent hover:text-foreground',
          'inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
          className
        )}
      >
        <Layers className='h-3.5 w-3.5 shrink-0' aria-hidden='true' />
        Endpoints ({count})
      </button>
      <CollectiveEndpointsModal
        isOpen={open}
        onClose={() => {
          setOpen(false);
        }}
        summary={summary}
        title={title}
      />
    </>
  );
}
