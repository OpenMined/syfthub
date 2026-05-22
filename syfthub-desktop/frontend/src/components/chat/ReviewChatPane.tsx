// ReviewChatPane renders a sent-review as a chat-shaped transcript with a
// continuation input box at the bottom. The visual goal is that opening a
// review feels like opening any other chat — same message bubbles, same
// transcript flow — rather than an audit log.
//
// Three states drive the rendering:
//
//   - status === 'pending': transcript ends with a "Held for review" notice
//     and the input is disabled. The user is waiting on the host.
//   - status === 'approved': transcript continues with the agent's real
//     response (the answer that was held), and the input is enabled —
//     typing here starts a fresh live session with the prior turns as
//     conversation context (the continuation flow).
//   - status === 'rejected': transcript ends with a "Rejected" notice
//     carrying the reject reason; input disabled.
//
// Continuation is implemented by calling startSessionWithHistory from the
// shared ChatWorkflowProvider — the same workflow the live pane reads from.
// After the call, activeChat is flipped to 'live' so the user transitions
// into AgentChatContent's view with prior context already seeded.

import { useCallback, useMemo, useRef, useState } from 'react';
import { Clock } from 'lucide-react';

import { useAppStore, type SentReviewEntry } from '@/stores/appStore';
import { useChatWorkflow } from './ChatWorkflowProvider';
import {
  AttachToActiveSession,
  BrowseForAttachment,
} from '../../../wailsjs/go/main/App';
import type { AttachmentSummary } from '@/hooks/use-attachments';

import {
  Message,
  MessageContent,
} from '@/components/prompt-kit/message';
import {
  ChatContainerContent,
  ChatContainerRoot,
} from '@/components/prompt-kit/chat-container';
import { MarkdownMessage } from '@/components/chat/markdown-message';
import { PolicyNotice } from '@/components/chat/policy-notice';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { cn, extractErrorMessage, formatFullTimestamp } from '@/lib/utils';
import { ChatInputArea } from '@/components/ChatView';

function inputPlaceholderFor(status: SentReviewEntry['status']): string {
  switch (status) {
    case 'approved':
      return 'Continue this conversation…';
    case 'pending':
      return 'Waiting for the endpoint owner to review this request…';
    default:
      return 'This request was rejected — start a new conversation to try again.';
  }
}

function policyNoticeReason(review: SentReviewEntry): string {
  switch (review.status) {
    case 'pending':
      return 'Held by the endpoint owner for manual review.';
    case 'rejected':
      return review.rejectReason || 'Rejected by the endpoint owner.';
    default:
      return 'Released by the endpoint owner.';
  }
}

// UserBubble / AssistantAvatar are inlined here rather than extracted from
// ChatView — if a third surface needs them, extract to a shared module.

function UserBubble({ id, content, isTurnBoundary }: Readonly<{
  id: string; content: string; isTurnBoundary?: boolean;
}>) {
  return (
    <Message
      key={id}
      role='article'
      aria-label='You said'
      className={cn('justify-end', isTurnBoundary && 'mt-6')}
    >
      <div className='flex max-w-full flex-col items-end'>
        <MessageContent className='font-inter bg-muted text-foreground max-w-2xl rounded-lg rounded-br-sm px-4 py-2.5 text-[15px] leading-relaxed'>
          {content}
        </MessageContent>
      </div>
    </Message>
  );
}

function AssistantAvatar() {
  return (
    <div className='bg-muted mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full'>
      <OpenMinedIcon className='h-5 w-5' />
    </div>
  );
}

function AssistantMessage({ id, content }: Readonly<{ id: string; content: string }>) {
  return (
    <Message
      key={id}
      role='article'
      aria-label='Assistant said'
      className='max-w-3xl items-start'
    >
      <AssistantAvatar />
      <div className='flex min-w-0 flex-1 flex-col'>
        <MarkdownMessage content={content} />
      </div>
    </Message>
  );
}

// Status badge moved to <StatusBadge /> in components/chat/review-status-badge.
// See lib/review-status for the single source of truth on status visuals.

// ── empty state for unknown review (race / typo) ─────────────────
function MissingReview({ reviewId }: Readonly<{ reviewId: string }>) {
  return (
    <div className='flex h-full flex-col items-center justify-center px-6 text-center'>
      <Clock className='mb-3 h-10 w-10 text-muted-foreground opacity-40' strokeWidth={1.2} />
      <h3 className='text-sm font-medium text-foreground'>Review not found</h3>
      <p className='mt-1 max-w-sm text-xs text-muted-foreground'>
        No sent review matches id <code className='font-mono'>{reviewId}</code>. It may
        have been recorded on a different device, or removed manually.
      </p>
    </div>
  );
}

// ── pane ────────────────────────────────────────────────────────
export interface ReviewChatPaneProps {
  reviewId: string;
}

export function ReviewChatPane({ reviewId }: Readonly<ReviewChatPaneProps>) {
  // Resolve the thread that contains the activeChat reviewId — the sidebar
  // sets activeChat to the latest review of a clicked thread, but a deep
  // link or a continuation that just landed could point at any member. The
  // pane always renders the thread's latest review (its transcript already
  // contains all prior turns; its status drives the badge + input gate).
  const thread = useAppStore((s) =>
    s.sentReviewThreads.find((t) =>
      t.reviews.some((r) => r.reviewId === reviewId),
    ) ?? null);
  const review = thread?.latestReview ?? null;
  const setActiveChat = useAppStore((s) => s.setActiveChat);
  const setChatSelectedModel = useAppStore((s) => s.setChatSelectedModel);
  const networkAgents = useAppStore((s) => s.networkAgents);

  const { startSessionWithHistory, isRunning } = useChatWorkflow();
  const [inputValue, setInputValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Pending attachments: host paths the user picked before the continuation
  // session starts. AttachToActiveSession requires an active session, so we
  // buffer the paths here keyed by a synthetic file_id (the chip's React
  // key) and flush them after startSessionWithHistory resolves.
  const [pendingIdToPath, setPendingIdToPath] = useState<Record<string, string>>({});
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  // Monotonic counter so synthetic chip ids stay unique even if two picks
  // share a basename.
  const pendingIdRef = useRef(0);

  // Continuation history: prior turns (requestMessages from the review) +
  // the agent's real reply (responseText). Together these are exactly what
  // the agent saw + produced before the hold, so a continuation reply will
  // be coherent with the held thread.
  const continuationHistory = useMemo(() => {
    if (!review) return [];
    const history = (review.requestMessages ?? []).map((m) => ({
      role: (m.role === 'assistant' || m.role === 'system' ? m.role : 'user') as
        'user' | 'assistant' | 'system',
      content: m.content,
    }));
    if (review.status === 'approved' && review.responseText) {
      history.push({ role: 'assistant', content: review.responseText });
    }
    return history;
  }, [review]);

  // Resolve the review's endpoint to a NetworkAgentInfo so the composer's
  // ModelSelector can render the right name in its locked variant. Falls
  // back to a synthetic object when the agent isn't in the network catalog
  // — the selector only needs `name` and `slug`/`ownerUsername` to render.
  const lockedAgent = useMemo(() => {
    if (!review) return null;
    const match = networkAgents.find(
      (a) => `${a.ownerUsername}/${a.slug}` === review.endpointPath,
    );
    if (match) return match;
    const [owner, slug] = (review.endpointPath ?? '').split('/');
    return {
      slug: slug ?? '',
      name: review.endpointName || review.endpointPath || 'Unknown agent',
      description: '',
      ownerUsername: owner ?? '',
      starsCount: 0,
    };
  }, [review, networkAgents]);

  const handlePickAttachment = useCallback(async () => {
    if (!review || review.status !== 'approved') return;
    setAttachmentError(null);
    try {
      const path = await BrowseForAttachment();
      if (!path) return;
      pendingIdRef.current += 1;
      const fileId = `pending:${pendingIdRef.current}`;
      setPendingIdToPath((prev) => ({ ...prev, [fileId]: path }));
    } catch (e) {
      setAttachmentError(extractErrorMessage(e, String(e)));
    }
  }, [review]);

  const handleRemoveAttachment = useCallback((fileId: string) => {
    setPendingIdToPath((prev) => {
      if (!(fileId in prev)) return prev;
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
  }, []);

  // Synthetic chip data for the composer. The live pane's AttachmentChip
  // component reads `file_id`/`name` and tolerates missing size/mime fields,
  // so a minimal shape is enough to render "Foo.txt" while the session
  // hasn't started yet.
  const pendingStaged: AttachmentSummary[] = useMemo(() => {
    return Object.entries(pendingIdToPath).map(([fileId, path]) => ({
      file_id: fileId,
      name: path.split(/[\\/]/).pop() ?? path,
      mime: '',
      size_bytes: 0,
      sha256: '',
    }));
  }, [pendingIdToPath]);

  const handleSubmit = useCallback(async () => {
    if (!review || review.status !== 'approved') return;
    const prompt = inputValue.trim();
    if (!prompt || submitting || isRunning) return;
    setSubmitting(true);
    try {
      // Best-effort: align the global agent dropdown with this review's
      // endpoint so other surfaces that key off chatSelectedModel pick up
      // the same agent. Only do this when the lookup hit the catalog —
      // lockedAgent's synthetic fallback isn't a real catalog entry.
      if (lockedAgent && networkAgents.includes(lockedAgent)) {
        setChatSelectedModel(lockedAgent);
      }
      // Snapshot paths BEFORE the await so concurrent picks during the
      // await aren't lost on the post-start attach.
      const paths = Object.values(pendingIdToPath);
      await startSessionWithHistory(continuationHistory, prompt, {
        endpointPath: review.endpointPath,
        endpointName: review.endpointName || review.endpointPath,
        // Stamp parent so the resulting hold is grouped with this review in
        // the sidebar's thread view.
        originReviewId: review.reviewId,
      });
      // Sequential because AttachToActiveSession is a stateful tunnel send;
      // a per-file error surfaces in attachmentError but does NOT abort the
      // remaining files (best-effort, matches the live pane's drag-drop loop).
      for (const path of paths) {
        try {
          await AttachToActiveSession(path);
        } catch (e) {
          setAttachmentError(extractErrorMessage(e, String(e)));
        }
      }
      setPendingIdToPath({});
      setActiveChat({ kind: 'live' });
      setInputValue('');
    } finally {
      setSubmitting(false);
    }
  }, [
    review, inputValue, submitting, isRunning, continuationHistory,
    networkAgents, lockedAgent, setChatSelectedModel, startSessionWithHistory,
    setActiveChat, pendingIdToPath,
  ]);

  if (!review) {
    return <MissingReview reviewId={reviewId} />;
  }

  const continuable = review.status === 'approved';
  const inputPlaceholder = inputPlaceholderFor(review.status);

  // Render the transcript: prior turns + held-turn notice + (approved
  // response | rejected notice). Each turn boundary inserts an mt-6 spacer
  // via UserBubble's isTurnBoundary.
  const turns = review.requestMessages ?? [];

  return (
    <div className='flex h-full flex-col'>
      {/* Transcript */}
      <div className='relative min-h-0 flex-1'>
        <ChatContainerRoot className='h-full'>
          <ChatContainerContent className='mx-auto w-full max-w-3xl space-y-4 px-6 py-6'>
            {turns.map((m, i) => {
              const id = `review-${review.reviewId}-${i}`;
              if (m.role === 'user') {
                return <UserBubble key={id} id={id} content={m.content} isTurnBoundary={i > 0} />;
              }
              if (m.role === 'assistant') {
                return <AssistantMessage key={id} id={id} content={m.content} />;
              }
              // Skip system messages in the visible transcript — they're
              // configuration, not conversation.
              return null;
            })}

            {/* The held-turn notice — fixed point that explains what happened. */}
            <PolicyNotice
              status={review.status === 'pending' ? 'pending' : 'blocked'}
              phase='post'
              policyName={review.policyName || undefined}
              reason={policyNoticeReason(review)}
              tracked={false}
            />

            {/* Approved response — the real reply the agent produced, now
                surfaced. Visually a normal assistant message; the only
                difference from a live reply is the optional "originally
                held" annotation below. */}
            {review.status === 'approved' && review.responseText && (
              <>
                <AssistantMessage
                  id={`review-${review.reviewId}-response`}
                  content={review.responseText}
                />
                {!continuable ? null : (
                  <p className='ml-10 max-w-2xl text-[11px] italic text-muted-foreground'>
                    Reply originally held by the manual-review policy
                    {review.hostResolvedAt && ` · delivered ${formatFullTimestamp(review.hostResolvedAt)}`}.
                  </p>
                )}
              </>
            )}
          </ChatContainerContent>
        </ChatContainerRoot>
      </div>

      {/* Input — reuses the live pane's composer so the chat UX is unified.
          Continuation is allowed only on approved reviews; submitting hands
          off to startSessionWithHistory which transitions to the live pane
          (so onStop, isActive etc. stay false here — the live session that
          runs from this prompt is owned by the live pane). The ModelSelector
          is hidden because the continuation pins the endpoint to the
          review's original agent. */}
      <ChatInputArea
        isLoading={submitting}
        inputDisabled={!continuable || submitting || isRunning}
        value={inputValue}
        onValueChange={setInputValue}
        onSubmit={handleSubmit}
        onStop={() => { /* no-op — review pane never owns an active session */ }}
        canSubmit={continuable && inputValue.trim().length > 0 && !submitting && !isRunning}
        placeholder={inputPlaceholder}
        stopTooltip='Stop'
        sendTooltip={continuable ? 'Continue' : 'Continuation only available on approved reviews'}
        isActive={false}
        lockedModel={lockedAgent}
        staged={pendingStaged}
        onPickAttachment={handlePickAttachment}
        onRemoveAttachment={handleRemoveAttachment}
        attachmentsBusy={false}
        attachmentError={attachmentError}
        attachmentsDisabled={!continuable || submitting || isRunning}
        footer={isRunning ? (
          <p className='mt-1.5 text-[11px] italic text-muted-foreground'>
            A live session is already running. Stop it before continuing this thread.
          </p>
        ) : undefined}
      />
    </div>
  );
}
