import { useEffect, useCallback, useState } from 'react';
import { useAppStore, ManualReviewEntry } from '../../stores/appStore';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Eye,
  Inbox,
  ShieldAlert,
  X,
} from 'lucide-react';
import { formatFullTimestamp } from '@/lib/utils';

// Filter values offered in the header. Kept as a constant so the Select
// options and the "is this a known filter" checks stay in sync.
const FILTERS = ['pending', 'approved', 'rejected', 'all'] as const;

// ── time formatting ─────────────────────────────────────────────
// created_at spans days, not just the current session, so a bare HH:MM:SS
// (as the Logs tab uses) would be ambiguous. Same-day entries show the time;
// older entries collapse to a date. The full timestamp lives in the tooltip.
function formatReviewTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
    : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── status badge ────────────────────────────────────────────────
// Colors mirror the Logs tab so a "pending" review reads the same here as a
// pending policy result there: chart-3 = waiting, chart-2 = approved/ok,
// destructive = rejected/error.
const STATUS_STYLES: Record<
  string,
  { cls: string; Icon: typeof Clock; label: string }
> = {
  pending: { cls: 'bg-chart-3/20 text-chart-3', Icon: Clock, label: 'Pending' },
  approved: { cls: 'bg-chart-2/20 text-chart-2', Icon: CheckCircle2, label: 'Approved' },
  rejected: { cls: 'bg-destructive/20 text-destructive', Icon: XCircle, label: 'Rejected' },
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? {
    cls: 'bg-secondary/50 text-muted-foreground',
    Icon: Clock,
    label: status || 'Unknown',
  };
  const { cls, Icon, label } = style;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

// ── detail modal ────────────────────────────────────────────────
function ReviewDetailPanel({
  review,
  onClose,
}: {
  review: ManualReviewEntry;
  onClose: () => void;
}) {
  const { approveManualReview, rejectManualReview } = useAppStore();

  // Footer state: 'view' shows Approve/Reject; 'reject' reveals the reason
  // field. submitting disables every dismissal path while the DB write runs.
  const [mode, setMode] = useState<'view' | 'reject'>('view');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isPending = review.status === 'pending';

  // Escape backs out of the reason field first, then closes the modal —
  // and does nothing mid-write so a dismissal can't race the resolve.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || submitting) return;
      if (mode === 'reject') {
        setMode('view');
        setReason('');
      } else {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, mode, submitting]);

  const handleApprove = async () => {
    setSubmitting(true);
    try {
      await approveManualReview(review.reviewId);
      onClose();
    } catch {
      // The store surfaced the error; keep the modal open for a retry.
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    setSubmitting(true);
    try {
      await rejectManualReview(review.reviewId, reason.trim());
      onClose();
    } catch {
      // The store surfaced the error; keep the modal open for a retry.
    } finally {
      setSubmitting(false);
    }
  };

  const messages = review.requestMessages ?? [];

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={submitting ? undefined : onClose}
    >
      <div
        className="bg-card rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-lg font-medium text-foreground">Held Request</h3>
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-muted-foreground hover:text-foreground disabled:opacity-40"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {/* Context — what the caller actually saw. */}
            <div className="flex gap-2 rounded bg-chart-3/10 border border-chart-3/20 p-2.5">
              <ShieldAlert className="w-4 h-4 text-chart-3 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-secondary-foreground leading-relaxed">
                This request was held by manual review. The caller received a
                placeholder response — the real content below was never
                delivered.
              </p>
            </div>

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground uppercase">Review ID</label>
                <p className="text-sm text-secondary-foreground font-mono text-xs">
                  {review.reviewId}
                </p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Status</label>
                <p className="text-sm">
                  <StatusBadge status={review.status} />
                </p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">User</label>
                <p className="text-sm text-foreground">{review.userId || 'Unknown'}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Policy</label>
                <p className="text-sm text-foreground">{review.policyName || '—'}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Created</label>
                <p className="text-sm text-foreground">
                  {formatFullTimestamp(review.createdAt)}
                </p>
              </div>
              {review.resolvedAt && (
                <div>
                  <label className="text-xs text-muted-foreground uppercase">Resolved</label>
                  <p className="text-sm text-foreground">
                    {formatFullTimestamp(review.resolvedAt)}
                  </p>
                </div>
              )}
            </div>

            {/* Request */}
            <div>
              <label className="text-xs text-muted-foreground uppercase">
                Request{review.requestType ? ` · ${review.requestType}` : ''}
              </label>
              <div className="mt-1 bg-background rounded p-2">
                {messages.length > 0 ? (
                  <div className="space-y-2">
                    {messages.map((msg, i) => (
                      <div key={i} className="border-l-2 border-border pl-2">
                        <span className="text-xs font-medium text-muted-foreground">
                          {msg.role}
                        </span>
                        <p className="text-sm text-foreground whitespace-pre-wrap break-words">
                          {msg.content}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : review.requestText ? (
                  <pre className="text-sm text-foreground whitespace-pre-wrap break-words font-sans">
                    {review.requestText}
                  </pre>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No request payload recorded.
                  </p>
                )}
              </div>
            </div>

            {/* Held response */}
            <div>
              <label className="text-xs text-muted-foreground uppercase">Held Response</label>
              <div className="mt-1 bg-background rounded p-2">
                {review.responseText ? (
                  <pre className="text-sm text-foreground whitespace-pre-wrap break-words font-sans max-h-80 overflow-y-auto">
                    {review.responseText}
                  </pre>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No response recorded.
                  </p>
                )}
              </div>
            </div>

            {/* Rejection reason — only present on rejected entries */}
            {review.status === 'rejected' && review.rejectReason && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">
                  Rejection Reason
                </label>
                <div className="mt-1 bg-background rounded p-2">
                  <p className="text-sm text-destructive">{review.rejectReason}</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer — resolution actions, only for pending requests. */}
        {isPending && (
          <div className="flex-shrink-0 border-t border-border px-4 py-3">
            {mode === 'view' ? (
              <div className="flex items-center justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={submitting}
                  onClick={() => setMode('reject')}
                  className="text-destructive hover:text-destructive"
                >
                  <XCircle className="w-4 h-4 mr-1" />
                  Reject
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  disabled={submitting}
                  onClick={handleApprove}
                >
                  {submitting ? (
                    <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4 mr-1" />
                  )}
                  Approve
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground uppercase">
                  Rejection Reason
                </label>
                <Textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why is this request being rejected? (optional)"
                  rows={2}
                  autoFocus
                  disabled={submitting}
                  className="text-sm resize-none"
                />
                <div className="flex items-center justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={submitting}
                    onClick={() => {
                      setMode('view');
                      setReason('');
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={submitting}
                    onClick={handleReject}
                  >
                    {submitting ? (
                      <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <XCircle className="w-4 h-4 mr-1" />
                    )}
                    Confirm Rejection
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── empty body ──────────────────────────────────────────────────
// Rendered *inside* the body, below the always-present header — never as a
// full-tab replacement. Replacing the whole tab here is what previously
// dropped the filter Select and trapped the user on an empty filter.
function EmptyBody({
  hasPolicy,
  filterWord,
}: {
  hasPolicy: boolean;
  filterWord: string;
}) {
  const { setActiveTab, setSettingsSection } = useAppStore();

  if (!hasPolicy) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center text-muted-foreground">
        <ShieldAlert className="w-12 h-12 mb-3 opacity-30" strokeWidth={1} />
        <h3 className="text-sm font-medium text-foreground mb-1">
          No manual review policy
        </h3>
        <p className="text-xs mb-4 max-w-xs leading-relaxed">
          Add a Manual Review policy to this endpoint and held requests will
          appear here for inspection.
        </p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setActiveTab('settings');
            setSettingsSection('policies');
          }}
          className="h-7 px-3 text-xs"
        >
          Go to Policies
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center text-muted-foreground">
      <Inbox className="w-12 h-12 mb-3 opacity-30" strokeWidth={1} />
      <h3 className="text-sm font-medium text-foreground mb-1">
        No {filterWord}requests
      </h3>
      <p className="text-xs max-w-xs leading-relaxed">
        Requests held by manual review for this endpoint will appear here.
      </p>
    </div>
  );
}

// ── main component ──────────────────────────────────────────────
export function RequestsTab() {
  const {
    selectedEndpointSlug,
    selectedEndpointDetail,
    manualReviews,
    manualReviewsLoading,
    selectedReview,
    reviewsStatusFilter,
    fetchManualReviews,
    setSelectedReview,
    setReviewsStatusFilter,
  } = useAppStore();

  useEffect(() => {
    if (selectedEndpointSlug) fetchManualReviews();
  }, [selectedEndpointSlug, fetchManualReviews]);

  const handleRefresh = useCallback(() => {
    fetchManualReviews();
  }, [fetchManualReviews]);

  // Policy detection drives only the empty-state copy (the "Go to Policies"
  // hint) — never layout. Normalized so "ManualReviewPolicy", "manual_review",
  // and "ManualReview" all match regardless of how the policy file was authored.
  const hasManualReviewPolicy = (selectedEndpointDetail?.policies ?? []).some(
    (p) => (p.type ?? '').toLowerCase().replace(/policy$/, '').replace(/_/g, '') === 'manualreview',
  );

  // RequestsTab only mounts with an endpoint selected; this is a defensive guard.
  if (!selectedEndpointSlug) return null;

  // Guard the Select value: an unrecognized stored filter would leave the
  // trigger blank. Fall back to "pending" so the control always shows a value.
  const activeFilter = (FILTERS as readonly string[]).includes(reviewsStatusFilter)
    ? reviewsStatusFilter
    : 'pending';
  const filterWord = activeFilter === 'all' ? '' : `${activeFilter} `;
  const countNoun = manualReviews.length === 1 ? 'request' : 'requests';

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header — always rendered so the filter is never unreachable. */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border/50 bg-card/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Select value={activeFilter} onValueChange={setReviewsStatusFilter}>
              <SelectTrigger size="sm" className="w-[130px] h-7 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Filter by</SelectLabel>
                  <SelectItem value="pending" className="text-xs">Pending</SelectItem>
                  <SelectItem value="approved" className="text-xs">Approved</SelectItem>
                  <SelectItem value="rejected" className="text-xs">Rejected</SelectItem>
                  <SelectItem value="all" className="text-xs">All</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground ml-2">
              {manualReviews.length} {filterWord}{countNoun}
            </span>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={manualReviewsLoading}
            className="h-7 px-2 text-xs"
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${manualReviewsLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Body — spinner / empty state / table all live below the header. */}
      <div className="flex-1 overflow-auto">
        {manualReviewsLoading && manualReviews.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center text-muted-foreground">
              <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p className="text-xs">Loading requests...</p>
            </div>
          </div>
        ) : manualReviews.length === 0 ? (
          <EmptyBody hasPolicy={hasManualReviewPolicy} filterWord={filterWord} />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-card/50 sticky top-0">
              <tr className="text-left text-xs text-muted-foreground uppercase">
                <th className="px-4 py-2 font-medium whitespace-nowrap">Time</th>
                <th className="px-4 py-2 font-medium whitespace-nowrap">User</th>
                <th className="px-4 py-2 font-medium">Request</th>
                <th className="px-4 py-2 font-medium whitespace-nowrap">Status</th>
                <th className="px-4 py-2 font-medium w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {manualReviews.map((review) => (
                <tr
                  key={review.reviewId}
                  className="hover:bg-card/30 cursor-pointer"
                  onClick={() => setSelectedReview(review)}
                >
                  <td className="px-4 py-2 text-foreground whitespace-nowrap">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>{formatReviewTime(review.createdAt)}</span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p>{formatFullTimestamp(review.createdAt)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                  <td className="px-4 py-2 text-foreground whitespace-nowrap">
                    {review.userId || 'Unknown'}
                  </td>
                  <td className="px-4 py-2 max-w-0">
                    <span className="block truncate text-muted-foreground">
                      {review.requestText || (
                        <span className="italic">No request text</span>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <StatusBadge status={review.status} />
                  </td>
                  <td className="px-4 py-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          className="text-muted-foreground hover:text-foreground p-1"
                          aria-label="View request details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="left">
                        <p>View details</p>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedReview && (
        <ReviewDetailPanel
          key={selectedReview.reviewId}
          review={selectedReview}
          onClose={() => setSelectedReview(null)}
        />
      )}
    </div>
  );
}
