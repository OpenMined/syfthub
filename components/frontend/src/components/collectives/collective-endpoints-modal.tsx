/**
 * CollectiveEndpointsModal
 *
 * Lists every member endpoint a Collective API fans out to, with each
 * endpoint's owner, type, per-request price, and how it settles (prepaid
 * publisher wallet / Hub wallet / free). Data comes straight from the billing
 * summary the parent already fetched — no extra request.
 */
import type { CollectiveBillingSummary, CollectiveMemberBilling } from '@/lib/collectives-api';
import type { EndpointType } from '@/lib/types';

import Database from 'lucide-react/dist/esm/icons/database';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { getEndpointTypeLabel } from '@/lib/endpoint-utils';
import { cn } from '@/lib/utils';

export interface CollectiveEndpointsModalProps {
  isOpen: boolean;
  onClose: () => void;
  summary: CollectiveBillingSummary | null | undefined;
  /** Human label for the Collective API (path or name). */
  title?: string;
}

/** `2,500 IDR / request` or `Free`. */
function memberPriceLabel(member: CollectiveMemberBilling): string {
  const b = member.billing;
  if (b.price_per_unit == null || !b.currency) return 'Free';
  const amount = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(
    b.price_per_unit
  );
  return `${amount} ${b.currency} / request`;
}

const KIND_LABEL: Record<string, string> = {
  prepaid: 'Prepaid',
  mpp: 'Hub wallet',
  free: 'Free'
};

const KIND_TONE: Record<string, string> = {
  prepaid:
    'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/50 dark:bg-violet-950/20 dark:text-violet-300',
  mpp: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/50 dark:bg-sky-950/20 dark:text-sky-300',
  free: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300'
};

function MemberRow({ member }: Readonly<{ member: CollectiveMemberBilling }>) {
  const owner = member.endpoint_owner_username;
  const slug = member.endpoint_slug;
  const path = owner && slug ? `${owner}/${slug}` : null;
  const kind = member.billing.kind;

  return (
    <div className='border-border bg-card flex items-center justify-between gap-3 rounded-lg border p-3'>
      <div className='flex min-w-0 items-center gap-2.5'>
        <div className='bg-muted text-muted-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-lg'>
          <Database className='h-4 w-4' />
        </div>
        <div className='min-w-0'>
          <div className='flex items-center gap-1.5'>
            <span className='text-foreground truncate text-sm font-medium'>
              {member.endpoint_name ?? `Endpoint #${String(member.endpoint_id)}`}
            </span>
            {member.endpoint_type && (
              <Badge variant='outline' className='shrink-0 text-[10px]'>
                {getEndpointTypeLabel(member.endpoint_type as EndpointType)}
              </Badge>
            )}
          </div>
          {path && <span className='text-muted-foreground block truncate text-xs'>{path}</span>}
        </div>
      </div>

      <div className='flex shrink-0 items-center gap-2'>
        <span className='text-foreground hidden text-xs tabular-nums sm:inline'>
          {memberPriceLabel(member)}
        </span>
        <span
          className={cn(
            'rounded-md border px-1.5 py-0.5 text-[10px] font-medium',
            KIND_TONE[kind] ?? KIND_TONE.free
          )}
        >
          {KIND_LABEL[kind] ?? kind}
        </span>
        {path && (
          <Link
            to={`/${path}`}
            target='_blank'
            rel='noopener noreferrer'
            className='text-muted-foreground hover:text-foreground transition-colors'
            aria-label={`View ${member.endpoint_name ?? path} details`}
          >
            <ExternalLink className='h-4 w-4' />
          </Link>
        )}
      </div>
    </div>
  );
}

export function CollectiveEndpointsModal({
  isOpen,
  onClose,
  summary,
  title
}: Readonly<CollectiveEndpointsModalProps>) {
  const members = summary?.members ?? [];

  return (
    <Modal isOpen={isOpen} onClose={onClose} title='Endpoints in this Collective API' size='2xl'>
      <div className='space-y-3'>
        <p className='text-muted-foreground text-sm'>
          A single query to {title ? <code className='text-xs'>{title}</code> : 'this Collective API'}{' '}
          runs against all {members.length} {members.length === 1 ? 'endpoint' : 'endpoints'} below
          at once and combines their results.
        </p>

        {members.length > 0 ? (
          <div className='max-h-[60vh] space-y-2 overflow-y-auto pr-1'>
            {members.map((member) => (
              <MemberRow key={member.endpoint_id} member={member} />
            ))}
          </div>
        ) : (
          <p className='text-muted-foreground py-6 text-center text-sm'>
            This Collective API has no active members yet.
          </p>
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
