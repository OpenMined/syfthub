import { Clock, ShieldX } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Structured policy outcome carried on an agent.message event (its `policy`
 * field) — mirrors syfthubapi's policyNotice. Present when the agent's reply
 * was blocked by a policy, or is pending review.
 */
export interface PolicyNoticeData {
  status: 'blocked' | 'pending';
  phase?: 'pre' | 'post';
  policy_name?: string;
  reason?: string;
}

const VARIANTS = {
  // A hard block — the system worked correctly, so amber (warning), not red.
  blocked: {
    icon: ShieldX,
    box: 'border-warning/30 bg-warning/10',
    accent: 'text-warning',
    chip: 'border-warning/25 bg-warning/15 text-warning',
  },
  // An in-progress hold (e.g. manual review) — the brand teal reads as
  // "pending", distinct from a block.
  pending: {
    icon: Clock,
    box: 'border-primary/30 bg-primary/10',
    accent: 'text-primary',
    chip: 'border-primary/25 bg-primary/15 text-primary',
  },
} as const;

function noticeTitle(status: 'blocked' | 'pending', phase?: 'pre' | 'post'): string {
  if (status === 'pending') return 'Pending review';
  return phase === 'post' ? 'Response blocked' : 'Request blocked';
}

/**
 * PolicyNotice renders a policy outcome as a distinct inline callout in the
 * agent transcript — visually separate from a normal agent reply. It follows
 * the app's existing callout pattern (bordered, tinted, rounded-lg, indented
 * to the agent gutter) so it reads as native rather than bolted on.
 */
export function PolicyNotice({
  status,
  phase,
  policyName,
  reason,
}: Readonly<{
  status: 'blocked' | 'pending';
  phase?: 'pre' | 'post';
  policyName?: string;
  reason?: string;
}>) {
  const variant = VARIANTS[status];
  const Icon = variant.icon;
  const title = noticeTitle(status, phase);

  return (
    <div
      role='status'
      aria-label={`Policy notice: ${title}`}
      className={cn('ml-10 max-w-2xl rounded-lg border px-3.5 py-3', variant.box)}
    >
      <div className='flex items-center gap-2'>
        <Icon className={cn('h-4 w-4 shrink-0', variant.accent)} aria-hidden='true' />
        <span className='text-foreground text-[13px] font-semibold'>{title}</span>
        {policyName && (
          <span
            className={cn(
              'ml-auto max-w-[40%] truncate rounded-full border px-2 py-0.5 text-[11px] font-medium',
              variant.chip,
            )}
            title={policyName}
          >
            {policyName}
          </span>
        )}
      </div>
      {reason && (
        <p className='text-muted-foreground mt-1.5 text-[13px] leading-relaxed'>{reason}</p>
      )}
    </div>
  );
}
