// Single source of truth for manual-review status visuals. Every surface
// that renders a review's status (sidebar icon, table badge, header pill,
// detail modal) reads its label/colour/icon from here so a "pending" hold
// reads the same on every screen. Colours line up with the host-side
// Requests tab (chart-3 = waiting, chart-2 = approved, destructive =
// rejected) — the two views are the same system seen from opposite ends.

import { Clock, CheckCircle2, XCircle, type LucideIcon } from 'lucide-react';

export type ReviewStatus = 'pending' | 'approved' | 'rejected';

export interface ReviewStatusVisual {
  readonly label: string;
  readonly textCls: string;
  readonly bgCls: string;
  readonly Icon: LucideIcon;
}

export const REVIEW_STATUS_VISUAL: Readonly<Record<ReviewStatus, ReviewStatusVisual>> =
  Object.freeze({
    pending:  Object.freeze({ label: 'Pending',  textCls: 'text-chart-3',     bgCls: 'bg-chart-3/20',     Icon: Clock }),
    approved: Object.freeze({ label: 'Approved', textCls: 'text-chart-2',     bgCls: 'bg-chart-2/20',     Icon: CheckCircle2 }),
    rejected: Object.freeze({ label: 'Rejected', textCls: 'text-destructive', bgCls: 'bg-destructive/20', Icon: XCircle }),
  });

/** Fallback visual for any status outside the canonical three. Surfaces a
 *  neutral "Unknown" rather than crashing or rendering an empty badge. */
export const UNKNOWN_STATUS_VISUAL: ReviewStatusVisual = Object.freeze({
  label: 'Unknown',
  textCls: 'text-muted-foreground',
  bgCls: 'bg-secondary/50',
  Icon: Clock,
});

/** Look up the visual for a status string. Unknown values resolve to
 *  UNKNOWN_STATUS_VISUAL so callers never have to guard the result. */
export function resolveReviewVisual(status: string): ReviewStatusVisual {
  if (status === 'pending' || status === 'approved' || status === 'rejected') {
    return REVIEW_STATUS_VISUAL[status];
  }
  return UNKNOWN_STATUS_VISUAL;
}
