import { useEffect, useCallback, useState } from 'react';

import { useAppStore, SentReviewEntry } from '../../stores/appStore';
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
  X,
} from 'lucide-react';
import { formatFullTimestamp } from '@/lib/utils';
import { formatShortTime } from '@/lib/date-utils';
import { StatusBadge } from '@/components/chat/review-status-badge';

// Filter values offered in the header. Kept as a constant so the Select
// options and the "is this a known filter" checks stay in sync.
const FILTERS = ['pending', 'approved', 'rejected', 'all'] as const;

// Time formatting and status badge moved to shared modules:
//   - formatShortTime (lib/date-utils) replaces the local same-day/else-date
//     splitter.
//   - StatusBadge (components/chat/review-status-badge) replaces the local
//     STATUS_STYLES table + ad-hoc badge component.
// Other surfaces (ChatSidebar, ReviewChatPane) read from the same modules so a
// "pending" hold renders identically wherever it appears.

// provenanceCaption explains how an entry's status was last set, so a guess is
// never mistaken for a confirmed outcome. "captured" needs no caption — a
// freshly captured entry is simply pending.
function provenanceCaption(status: string, source: string): string {
  if (source === 'manual') return 'Status set by you — not confirmed by the host.';
  if (source === 'queried') return 'Status confirmed by the host.';
  if (status === 'pending') return 'Recorded when the request was held. The host has not been polled.';
  return '';
}

// firstRequestLine returns a one-line preview of what the user asked.
function firstRequestLine(review: SentReviewEntry): string {
  const msg = review.requestMessages?.[0]?.content?.trim();
  return msg || '';
}

// ── detail modal ────────────────────────────────────────────────
function SentReviewDetailPanel({
  review,
  onClose,
}: {
  review: SentReviewEntry;
  onClose: () => void;
}) {
  const markSentReviewStatus = useAppStore((s) => s.markSentReviewStatus);
  const saveSentReviewNote = useAppStore((s) => s.saveSentReviewNote);

  // Footer state: 'view' shows the override buttons; 'reject' reveals the
  // reason field. submitting disables every dismissal path while a write runs.
  const [mode, setMode] = useState<'view' | 'reject'>('view');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [note, setNote] = useState(review.userNote ?? '');
  const [savingNote, setSavingNote] = useState(false);
  const isPending = review.status === 'pending';
  const noteDirty = note.trim() !== (review.userNote ?? '').trim();

  // Escape backs out of the reason field first, then closes the modal —
  // and does nothing mid-write so a dismissal can't race the resolve.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || submitting || savingNote) return;
      if (mode === 'reject') {
        setMode('view');
        setReason('');
      } else {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, mode, submitting, savingNote]);

  const handleMark = async (status: 'approved' | 'rejected', why: string) => {
    setSubmitting(true);
    try {
      await markSentReviewStatus(review.reviewId, status, why);
      onClose();
    } catch {
      // The store surfaced the error; keep the modal open for a retry.
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveNote = async () => {
    setSavingNote(true);
    try {
      await saveSentReviewNote(review.reviewId, note.trim());
    } catch {
      // The store surfaced the error; leave the field as-is for a retry.
    } finally {
      setSavingNote(false);
    }
  };

  const messages = review.requestMessages ?? [];
  const caption = provenanceCaption(review.status, review.statusSource);

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={submitting || savingNote ? undefined : onClose}
    >
      <div
        className="bg-card rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-lg font-medium text-foreground">Request you sent for review</h3>
          <button
            onClick={onClose}
            disabled={submitting || savingNote}
            className="text-muted-foreground hover:text-foreground disabled:opacity-40"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {/* Context — what this record is and is not. */}
            <div className="flex gap-2 rounded bg-chart-3/10 border border-chart-3/20 p-2.5">
              <Clock className="w-4 h-4 text-chart-3 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-secondary-foreground leading-relaxed">
                This request was held for manual review by the endpoint owner.
                You received a placeholder instead of the real answer. This is
                your own local record of it.
              </p>
            </div>

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground uppercase">Endpoint</label>
                <p className="text-sm text-foreground">
                  {review.endpointName || review.endpointPath}
                </p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Status</label>
                <div className="text-sm">
                  <StatusBadge status={review.status} />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Review ID</label>
                <p className="text-sm text-secondary-foreground font-mono text-xs">
                  {review.reviewId}
                </p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Policy</label>
                <p className="text-sm text-foreground">{review.policyName || '—'}</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase">Submitted</label>
                <p className="text-sm text-foreground">
                  {formatFullTimestamp(review.submittedAt)}
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

            {caption && (
              <p className="text-xs text-muted-foreground italic">{caption}</p>
            )}

            {/* Request — what the user actually sent. */}
            <div>
              <label className="text-xs text-muted-foreground uppercase">
                What you sent
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
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No request payload recorded.
                  </p>
                )}
              </div>
            </div>

            {/* Agent response — the real answer the agent produced for this
                request, surfaced once the owner approved. This is what the
                chat would have shown if no manual-review policy were in the
                way. Empty until a host-confirmed approval lands; never shown
                for rejected entries (no response is delivered on rejection
                by design). */}
            {review.status === 'approved' && review.responseText && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">
                  Agent response
                </label>
                <div className="mt-1 bg-chart-2/10 border border-chart-2/20 rounded p-2">
                  <pre className="text-sm text-foreground whitespace-pre-wrap break-words font-sans">
                    {review.responseText}
                  </pre>
                </div>
              </div>
            )}

            {/* Placeholder — what the caller received instead of the answer
                while the request was held. Kept visible after approval so
                the user can see what they originally got vs the real answer
                above. Demoted to "muted" treatment once the real response
                is in. */}
            {review.placeholder && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">
                  {review.status === 'approved' && review.responseText
                    ? 'Placeholder shown while held'
                    : 'Placeholder you received'}
                </label>
                <div className="mt-1 bg-background rounded p-2">
                  <pre className="text-sm text-muted-foreground whitespace-pre-wrap break-words font-sans">
                    {review.placeholder}
                  </pre>
                </div>
              </div>
            )}

            {/* Rejection reason — only present on rejected entries. */}
            {review.status === 'rejected' && review.rejectReason && (
              <div>
                <label className="text-xs text-muted-foreground uppercase">
                  Rejection reason
                </label>
                <div className="mt-1 bg-background rounded p-2">
                  <p className="text-sm text-destructive">{review.rejectReason}</p>
                </div>
              </div>
            )}

            {/* Note — the requester's own free-text annotation. */}
            <div>
              <label className="text-xs text-muted-foreground uppercase">Your note</label>
              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add a private note — e.g. who you chased, or the outcome you were told."
                rows={2}
                disabled={savingNote}
                className="mt-1 text-sm resize-none"
              />
              {noteDirty && (
                <div className="mt-1 flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={savingNote}
                    onClick={handleSaveNote}
                    className="h-7 px-3 text-xs"
                  >
                    {savingNote ? (
                      <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                    ) : null}
                    Save note
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer — manual override, only for entries still pending. Phase 1
            has no channel to the host, so the user records an outcome they
            were told out of band; such entries are clearly marked as manual. */}
        {isPending && (
          <div className="flex-shrink-0 border-t border-border px-4 py-3">
            {mode === 'view' ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  Heard back out of band? Record the outcome:
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={submitting}
                    onClick={() => setMode('reject')}
                    className="text-destructive hover:text-destructive"
                  >
                    <XCircle className="w-4 h-4 mr-1" />
                    Mark rejected
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    disabled={submitting}
                    onClick={() => handleMark('approved', '')}
                  >
                    {submitting ? (
                      <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 mr-1" />
                    )}
                    Mark approved
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground uppercase">
                  Rejection reason
                </label>
                <Textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="What were you told? (optional)"
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
                    onClick={() => handleMark('rejected', reason.trim())}
                  >
                    {submitting ? (
                      <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <XCircle className="w-4 h-4 mr-1" />
                    )}
                    Confirm rejection
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
function EmptyBody({ filterWord }: { filterWord: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center text-muted-foreground">
      <Inbox className="w-12 h-12 mb-3 opacity-30" strokeWidth={1} />
      <h3 className="text-sm font-medium text-foreground mb-1">
        No {filterWord}requests
      </h3>
      <p className="text-xs max-w-sm leading-relaxed">
        When an agent holds one of your requests for manual review, it is
        recorded here so you have a durable record after the chat is gone.
      </p>
    </div>
  );
}

// ── main component ──────────────────────────────────────────────
export function SentReviewsView() {
  const sentReviews = useAppStore((s) => s.sentReviews);
  const sentReviewsLoading = useAppStore((s) => s.sentReviewsLoading);
  const selectedSentReview = useAppStore((s) => s.selectedSentReview);
  const sentReviewsFilter = useAppStore((s) => s.sentReviewsFilter);
  const fetchSentReviews = useAppStore((s) => s.fetchSentReviews);
  const setSelectedSentReview = useAppStore((s) => s.setSelectedSentReview);
  const setSentReviewsFilter = useAppStore((s) => s.setSentReviewsFilter);

  // Initial load + the manual-review:resolved subscription both live in the
  // store's initialize() now (design #3 — centralised event routing). This
  // view only owns the explicit Refresh button and the filter Select; both
  // of those still flow through the store. Removing the per-mount fetch
  // also fixes the StrictMode double-fetch on first render.

  const handleRefresh = useCallback(() => {
    fetchSentReviews();
  }, [fetchSentReviews]);

  // Guard the Select value: an unrecognized stored filter would leave the
  // trigger blank. Fall back to "pending" so the control always shows a value.
  const activeFilter = (FILTERS as readonly string[]).includes(sentReviewsFilter)
    ? sentReviewsFilter
    : 'pending';
  const filterWord = activeFilter === 'all' ? '' : `${activeFilter} `;
  // Client-side filter. The store holds every status (the sidebar's thread
  // view requires that), so this view applies its dropdown locally rather
  // than refetching with a status filter.
  const visibleReviews = activeFilter === 'all'
    ? sentReviews
    : sentReviews.filter((r) => r.status === activeFilter);
  const countNoun = visibleReviews.length === 1 ? 'request' : 'requests';

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header — always rendered so the filter is never unreachable. */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-border/50 bg-card/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Select value={activeFilter} onValueChange={setSentReviewsFilter}>
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
              {visibleReviews.length} {filterWord}{countNoun}
            </span>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            disabled={sentReviewsLoading}
            className="h-7 px-2 text-xs"
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${sentReviewsLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
        {/* Honest framing: Phase 1 is a "what I submitted" log, not a live
            tracker — the status is only as current as what the user confirmed. */}
        <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
          A durable record of requests held for manual review. Statuses do not
          update on their own yet — mark an outcome once the endpoint owner
          tells you.
        </p>
      </div>

      {/* Body — spinner / empty state / table. */}
      <div className="flex-1 overflow-auto">
        {sentReviewsLoading && visibleReviews.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-center text-muted-foreground">
              <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p className="text-xs">Loading requests...</p>
            </div>
          </div>
        ) : visibleReviews.length === 0 ? (
          <EmptyBody filterWord={filterWord} />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-card/50 sticky top-0">
              <tr className="text-left text-xs text-muted-foreground uppercase">
                <th className="px-4 py-2 font-medium whitespace-nowrap">Endpoint</th>
                <th className="px-4 py-2 font-medium whitespace-nowrap">Submitted</th>
                <th className="px-4 py-2 font-medium">Request</th>
                <th className="px-4 py-2 font-medium whitespace-nowrap">Status</th>
                <th className="px-4 py-2 font-medium w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {visibleReviews.map((review) => (
                <tr
                  key={review.reviewId}
                  className="hover:bg-card/30 cursor-pointer"
                  onClick={() => setSelectedSentReview(review)}
                >
                  <td className="px-4 py-2 text-foreground whitespace-nowrap max-w-[12rem]">
                    <span className="block truncate">
                      {review.endpointName || review.endpointPath}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-foreground whitespace-nowrap">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>{formatShortTime(review.submittedAt, { fallback: review.submittedAt })}</span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p>{formatFullTimestamp(review.submittedAt)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                  <td className="px-4 py-2 max-w-0">
                    <span className="block truncate text-muted-foreground">
                      {firstRequestLine(review) || (
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

      {selectedSentReview && (
        <SentReviewDetailPanel
          key={selectedSentReview.reviewId}
          review={selectedSentReview}
          onClose={() => setSelectedSentReview(null)}
        />
      )}
    </div>
  );
}
