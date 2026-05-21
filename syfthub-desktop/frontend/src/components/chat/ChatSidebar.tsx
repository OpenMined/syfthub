// ChatSidebar is the left rail of the chat surface: a collapsible list of
// conversations. The live session sits at the top (highlighted "Active"
// when a chat is in flight); every entry from the sent-reviews ledger
// follows, ordered newest-first.
//
// Clicking an item switches activeChat in the store; the parent ChatView
// renders the corresponding pane.
//
// The sidebar's collapsed/expanded state persists across launches via
// localStorage (see appStore.persistChatSidebarCollapsed). Collapsed shows
// just icons; expanded shows endpoint name + status + date.

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  Trash2,
  Zap,
  XCircle,
} from 'lucide-react';

import { EventsOn } from '../../../wailsjs/runtime/runtime';

import {
  useAppStore,
  type ActiveChat,
  type SentReviewEntry,
} from '../../stores/appStore';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

// ── visual constants ─────────────────────────────────────────────
// Icons mirror SentReviewsView's STATUS_STYLES so the same status reads
// identically in both surfaces. Active (live) uses brand colour, distinct
// from any sent-review state.
const STATUS_VISUALS = {
  approved: { Icon: CheckCircle2, cls: 'text-chart-2', label: 'Approved' },
  pending: { Icon: Clock, cls: 'text-chart-3', label: 'Pending' },
  rejected: { Icon: XCircle, cls: 'text-destructive', label: 'Rejected' },
} as const;

// ── time formatting ──────────────────────────────────────────────
// Sidebar items show a compact relative time (e.g. "2h ago", "Mar 5") —
// older formats roll over to a date the same way SentReviewsView does so
// the two surfaces stay visually consistent.
function relativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = Date.now();
  const ms = now - d.getTime();
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString('en-US',
    sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' });
}

// ── live session item ────────────────────────────────────────────
// The "Active" item at the top represents the in-memory live agent session.
// We show it always (so the user has a clear way back to live), badging it
// based on whether anything is happening.
function LiveItem({
  active,
  collapsed,
  endpointName,
  isRunning,
  onClick,
}: Readonly<{
  active: boolean;
  collapsed: boolean;
  endpointName: string;
  isRunning: boolean;
  onClick: () => void;
}>) {
  const label = endpointName || 'New chat';
  const subtitle = isRunning ? 'In progress' : 'Idle';

  const inner = (
    <button
      type='button'
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'group flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors',
        active
          ? 'bg-muted text-foreground'
          : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
      )}
    >
      <Zap
        className={cn(
          'h-4 w-4 shrink-0',
          isRunning ? 'text-primary' : 'text-muted-foreground',
          isRunning && 'animate-pulse',
        )}
        aria-hidden='true'
      />
      {!collapsed && (
        <div className='min-w-0 flex-1'>
          <div className='truncate text-sm font-medium'>{label}</div>
          <div className='truncate text-[11px]'>{subtitle}</div>
        </div>
      )}
    </button>
  );

  if (!collapsed) return inner;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{inner}</TooltipTrigger>
      <TooltipContent side='right'>
        <p className='font-medium'>{label}</p>
        <p className='text-xs text-muted-foreground'>{subtitle}</p>
      </TooltipContent>
    </Tooltip>
  );
}

// ── review item ──────────────────────────────────────────────────
function ReviewItem({
  review,
  active,
  collapsed,
  onClick,
  onRequestDelete,
}: Readonly<{
  review: SentReviewEntry;
  active: boolean;
  collapsed: boolean;
  onClick: () => void;
  // onRequestDelete is wired only when the sidebar is expanded — collapsed
  // mode has no room for a per-row trash icon and we'd rather not hide a
  // destructive action behind a tooltip.
  onRequestDelete?: (review: SentReviewEntry) => void;
}>) {
  const visual = STATUS_VISUALS[review.status as keyof typeof STATUS_VISUALS] ?? {
    Icon: Clock,
    cls: 'text-muted-foreground',
    label: review.status || 'Unknown',
  };
  const { Icon, cls, label } = visual;

  // The endpoint label prefers the display name; the raw "owner/slug" path
  // is the fallback when an older capture didn't record a name.
  const endpointLabel = review.endpointName || review.endpointPath || 'Unknown endpoint';
  const when = relativeTime(review.submittedAt);

  const inner = (
    <div
      className={cn(
        'group relative flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors',
        active
          ? 'bg-muted text-foreground'
          : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
      )}
    >
      {/* Whole-row click target — left as a button so the row is keyboard-
          accessible and screen readers announce it correctly. The trash
          icon below uses stopPropagation so it doesn't trigger the row. */}
      <button
        type='button'
        onClick={onClick}
        aria-current={active ? 'page' : undefined}
        className='flex min-w-0 flex-1 items-center gap-2.5 bg-transparent text-left focus:outline-none'
      >
        <Icon className={cn('h-4 w-4 shrink-0', cls)} aria-hidden='true' />
        {!collapsed && (
          <div className='min-w-0 flex-1'>
            <div className='truncate text-sm font-medium'>{endpointLabel}</div>
            <div className='flex items-center gap-1.5 text-[11px]'>
              <span className={cls}>{label}</span>
              <span className='text-muted-foreground'>·</span>
              <span className='truncate'>{when}</span>
            </div>
          </div>
        )}
      </button>

      {/* Per-row delete affordance — hidden until row hover (or keyboard
          focus on the trash itself) so the sidebar stays uncluttered. Only
          rendered in expanded mode; collapsed mode would have to fit it in
          a 48-px-wide rail, and a hover-only destructive control there is
          a worse UX than asking the user to expand first. */}
      {!collapsed && onRequestDelete && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type='button'
              onClick={(e) => {
                // Don't let the row click handler fire underneath.
                e.stopPropagation();
                onRequestDelete(review);
              }}
              aria-label={`Delete chat with ${endpointLabel}`}
              className={cn(
                'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md',
                'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
                'opacity-0 transition-opacity focus:opacity-100 focus-visible:ring-2 focus-visible:ring-ring',
                'group-hover:opacity-100',
              )}
            >
              <Trash2 className='h-3.5 w-3.5' aria-hidden='true' />
            </button>
          </TooltipTrigger>
          <TooltipContent side='right'>Delete chat</TooltipContent>
        </Tooltip>
      )}
    </div>
  );

  if (!collapsed) return inner;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{inner}</TooltipTrigger>
      <TooltipContent side='right'>
        <p className='font-medium'>{endpointLabel}</p>
        <p className='text-xs'>
          <span className={cls}>{label}</span>
          <span className='text-muted-foreground'> · {when}</span>
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

// ── sidebar ──────────────────────────────────────────────────────
export interface ChatSidebarProps {
  /** Whether the live session is currently running or awaiting input. The
   *  sidebar shows a pulse on the Active item when true. */
  liveRunning: boolean;
  /** Display name of the model the live session is bound to (if any).
   *  Empty when no model has been chosen yet. */
  liveEndpointName: string;
}

export function ChatSidebar({ liveRunning, liveEndpointName }: Readonly<ChatSidebarProps>) {
  const sentReviews = useAppStore((s) => s.sentReviews);
  const fetchSentReviews = useAppStore((s) => s.fetchSentReviews);
  const activeChat = useAppStore((s) => s.activeChat);
  const setActiveChat = useAppStore((s) => s.setActiveChat);
  const deleteSentReview = useAppStore((s) => s.deleteSentReview);
  const collapsed = useAppStore((s) => s.chatSidebarCollapsed);
  const setCollapsed = useAppStore((s) => s.setChatSidebarCollapsed);

  // Pending-delete state. We confirm before deleting because the host's
  // resolution may still arrive later (and re-create a row via the synth
  // INSERT path); the user should know what they're undoing.
  const [pendingDelete, setPendingDelete] = useState<SentReviewEntry | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Initial load + on mount. We always fetch 'all' because the sidebar
  // shows every status — filtering by the global sentReviewsFilter (which
  // defaults to 'pending') would hide approved/rejected rows.
  useEffect(() => {
    void fetchSentReviews('all');
  }, [fetchSentReviews]);

  // Live refresh on host-delivered resolutions. The old SentReviewsView
  // used to own this subscription; with the sidebar now being the only
  // place reviews are listed, it has to own it instead — otherwise a
  // resolution that arrives while the user is sitting on the sidebar
  // would never visibly land until they navigate away and back.
  // EventsOn returns a per-listener unsubscribe; return it directly so
  // StrictMode's double-mount doesn't tear down the listener the still-
  // mounted instance owns.
  useEffect(() => {
    const off = EventsOn('manual-review:resolved', () => {
      void fetchSentReviews('all');
    });
    return off;
  }, [fetchSentReviews]);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteSentReview(pendingDelete.reviewId);
      setPendingDelete(null);
    } catch {
      // The store recorded the error; close the dialog so the user can see
      // the toast/banner. A retry is one click away.
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, deleteSentReview]);

  const isLiveActive = activeChat.kind === 'live';
  const activeReviewId = activeChat.kind === 'review' ? activeChat.reviewId : null;

  const pendingLabel = pendingDelete
    ? (pendingDelete.endpointName || pendingDelete.endpointPath || 'this chat')
    : '';

  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-border/50 bg-card/30 transition-[width] duration-150',
        collapsed ? 'w-12' : 'w-64',
      )}
      aria-label='Chats'
    >
      {/* Header: collapse toggle. When expanded, also acts as a thin label. */}
      <div className='flex h-10 shrink-0 items-center justify-between border-b border-border/50 px-2'>
        {!collapsed && (
          <span className='px-1 text-xs font-medium uppercase text-muted-foreground'>
            Chats
          </span>
        )}
        <button
          type='button'
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          className='inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted/50 hover:text-foreground'
        >
          {collapsed
            ? <ChevronRight className='h-4 w-4' aria-hidden='true' />
            : <ChevronLeft className='h-4 w-4' aria-hidden='true' />}
        </button>
      </div>

      {/* Items. Live session pinned at top; reviews below, newest-first. */}
      <div className='flex-1 space-y-0.5 overflow-y-auto px-1.5 py-2'>
        <LiveItem
          active={isLiveActive}
          collapsed={collapsed}
          endpointName={liveEndpointName}
          isRunning={liveRunning}
          onClick={() => setActiveChat({ kind: 'live' })}
        />

        {!collapsed && sentReviews.length > 0 && (
          <div className='px-1 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground'>
            Sent for review
          </div>
        )}

        {sentReviews.map((r) => (
          <ReviewItem
            key={r.reviewId}
            review={r}
            active={r.reviewId === activeReviewId}
            collapsed={collapsed}
            onClick={() => setActiveChat({ kind: 'review', reviewId: r.reviewId })}
            onRequestDelete={setPendingDelete}
          />
        ))}

        {!collapsed && sentReviews.length === 0 && (
          <p className='px-2 py-3 text-[11px] italic leading-relaxed text-muted-foreground'>
            Held requests will appear here once the endpoint owner reviews them.
          </p>
        )}
      </div>

      {/* Delete confirmation. AlertDialog rather than a window.confirm so
          the styling stays consistent with the app's other destructive
          flows (e.g. DeleteEndpointDialog). Wording explains the resolution
          re-creation trade so a user isn't surprised by a row reappearing. */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>
              <span className='block'>
                Removes <span className='font-medium text-foreground'>{pendingLabel}</span> from
                your local Sent for Review history. The chat transcript on this device is lost.
              </span>
              {pendingDelete?.status === 'pending' && (
                <span className='mt-2 block text-xs'>
                  Note: this request is still pending review on the host. If the host approves
                  or rejects it later, the entry will re-appear here (with the resolution applied)
                  the next time delivery lands.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // AlertDialogAction auto-closes; suppress so we can show
                // the in-flight state and only close on success.
                e.preventDefault();
                void handleConfirmDelete();
              }}
              disabled={deleting}
              className='bg-destructive text-destructive-foreground hover:bg-destructive/90'
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
