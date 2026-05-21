// StatusBadge renders the shared review-status visual in two shapes:
//
//   - variant='pill' (default): icon + label inside a coloured pill.
//     The default size is 'sm' which matches the table/inline badge
//     spots that were the original visuals in SentReviewsView /
//     ReviewChatPane.
//   - variant='icon-only': just the icon, coloured. Used in the
//     collapsed sidebar where there is no room for a pill.
//
// Both variants pull from the shared resolveReviewVisual so any status
// reads identically across surfaces. Memoised because the badge appears
// many times in lists where parent re-renders are common.

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { resolveReviewVisual } from '@/lib/review-status';

export interface StatusBadgeProps {
  status: string;
  variant?: 'pill' | 'icon-only';
  size?: 'sm' | 'md';
  /** Override the visual's label (e.g. when the parent wants to show the
   *  raw status string for an unknown value instead of "Unknown"). */
  labelOverride?: string;
  className?: string;
}

function StatusBadgeImpl({
  status,
  variant = 'pill',
  size,
  labelOverride,
  className,
}: StatusBadgeProps) {
  const visual = resolveReviewVisual(status);
  // Icons-only badges read better at md; pills are denser at sm.
  const effectiveSize = size ?? (variant === 'icon-only' ? 'md' : 'sm');
  const iconSize = effectiveSize === 'md' ? 'h-4 w-4' : 'h-3 w-3';
  const label = labelOverride ?? visual.label;

  if (variant === 'icon-only') {
    return (
      <visual.Icon
        className={cn(iconSize, visual.textCls, className)}
        aria-label={label}
      />
    );
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs',
        visual.bgCls,
        visual.textCls,
        className,
      )}
    >
      <visual.Icon className={iconSize} />
      <span>{label}</span>
    </span>
  );
}

export const StatusBadge = memo(StatusBadgeImpl);
