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

import { useCallback, useMemo, useState } from 'react';
import { Clock, ArrowUp } from 'lucide-react';

import { useAppStore, type SentReviewEntry } from '@/stores/appStore';
import { useChatWorkflow } from './ChatWorkflowProvider';
import { StatusBadge } from '@/components/chat/review-status-badge';

import {
  Message,
  MessageContent,
} from '@/components/prompt-kit/message';
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from '@/components/prompt-kit/prompt-input';
import {
  ChatContainerContent,
  ChatContainerRoot,
} from '@/components/prompt-kit/chat-container';
import { MarkdownMessage } from '@/components/chat/markdown-message';
import { PolicyNotice } from '@/components/chat/policy-notice';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { cn } from '@/lib/utils';
import { formatFullTimestamp } from '@/lib/utils';

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

// ── small repeats from ChatView ──────────────────────────────────
// UserBubble / AssistantAvatar are inlined here rather than extracted from
// ChatView because they are small and changing them in two places is less
// risk than reorganizing ChatView's internals for this refactor. If a third
// surface needs them, extract to a shared module.

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
  const review = useAppStore((s) =>
    s.sentReviews.find((r) => r.reviewId === reviewId) ?? null);
  const setActiveChat = useAppStore((s) => s.setActiveChat);
  const setChatSelectedModel = useAppStore((s) => s.setChatSelectedModel);
  const networkAgents = useAppStore((s) => s.networkAgents);

  const { startSessionWithHistory, isRunning } = useChatWorkflow();
  const [inputValue, setInputValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

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

  const handleSubmit = useCallback(async () => {
    if (!review || review.status !== 'approved') return;
    const prompt = inputValue.trim();
    if (!prompt || submitting || isRunning) return;
    setSubmitting(true);
    try {
      // Best-effort: align the global agent dropdown with this review's
      // endpoint so the UI's other affordances (model name in the live
      // pane's header, etc.) follow. We match by owner/slug — the most
      // stable identity — and fall back to leaving the dropdown alone if
      // the agent isn't in the catalog (continuation still works because
      // we pass overrides to startSessionWithHistory).
      const targetAgent = networkAgents.find(
        (a) => `${a.ownerUsername}/${a.slug}` === review.endpointPath,
      );
      if (targetAgent) {
        setChatSelectedModel(targetAgent);
      }
      await startSessionWithHistory(continuationHistory, prompt, {
        endpointPath: review.endpointPath,
        endpointName: review.endpointName || review.endpointPath,
      });
      // Transition to the live pane so the user sees the running session.
      setActiveChat({ kind: 'live' });
      setInputValue('');
    } finally {
      setSubmitting(false);
    }
  }, [
    review, inputValue, submitting, isRunning, continuationHistory,
    networkAgents, setChatSelectedModel, startSessionWithHistory, setActiveChat,
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
      {/* Header — endpoint + status. Mirrors the live pane's header so the
          two surfaces feel like the same chat product. */}
      <div className='flex shrink-0 items-center justify-between gap-3 border-b border-border/50 px-4 py-3'>
        <div className='min-w-0 flex-1'>
          <div className='truncate text-sm font-medium text-foreground'>
            {review.endpointName || review.endpointPath}
          </div>
          <div className='truncate text-[11px] text-muted-foreground'>
            Sent {formatFullTimestamp(review.submittedAt)}
            {review.hostResolvedAt && ` · Resolved ${formatFullTimestamp(review.hostResolvedAt)}`}
          </div>
        </div>
        <StatusBadge status={review.status} />
      </div>

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

      {/* Input — enabled iff approved. Submitting triggers the continuation
          flow which transitions the user into the live pane. */}
      <div className='shrink-0 border-t border-border/50 bg-card/30 px-4 py-3'>
        <div className='mx-auto w-full max-w-3xl'>
          <PromptInput
            value={inputValue}
            onValueChange={setInputValue}
            onSubmit={handleSubmit}
            isLoading={submitting}
          >
            <PromptInputTextarea
              placeholder={inputPlaceholder}
              disabled={!continuable || submitting || isRunning}
            />
            <PromptInputActions>
              <PromptInputAction tooltip={continuable ? 'Continue' : 'Continuation only available on approved reviews'}>
                <button
                  type='button'
                  onClick={handleSubmit}
                  disabled={!continuable || !inputValue.trim() || submitting || isRunning}
                  aria-label='Send'
                  className={cn(
                    'inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors',
                    continuable && inputValue.trim() && !submitting && !isRunning
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'bg-muted text-muted-foreground opacity-60',
                  )}
                >
                  <ArrowUp className='h-4 w-4' aria-hidden='true' />
                </button>
              </PromptInputAction>
            </PromptInputActions>
          </PromptInput>
          {isRunning && (
            <p className='mt-1.5 text-[11px] italic text-muted-foreground'>
              A live session is already running. Stop it before continuing this thread.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
