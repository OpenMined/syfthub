import { useCallback, useEffect, useRef, useState } from 'react';
import {
  StartAgentSession,
  StartAgentSessionWithHistory,
  StartAgentSessionWithCredential,
  SendAgentMessage,
  StopAgentSession,
  RecordSentReview,
  EvaluatePaymentDecision,
  WalletPayChallenge,
} from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';
import { main } from '../../wailsjs/go/models';
import { useAppStore } from '../stores/appStore';

// =============================================================================
// Agent Event Types
// =============================================================================

export interface AgentStreamEvent {
  type: string;
  sessionId: string;
  data?: Record<string, unknown>;
}

// Each entry in the agent conversation
export interface AgentEntry {
  id: string;
  kind: 'user' | 'thinking' | 'status' | 'tool_call' | 'tool_result' | 'message' | 'token' | 'request_input' | 'error' | 'completed' | 'cancelled' | 'attachment' | 'policy';
  content: string;
  data?: Record<string, unknown>;
  timestamp: number;
}

// AttachmentMeta is the shape pushed into AgentEntry.data for attachment
// entries — both inbound (agent.attachment events) and staged outbound
// uploads (user attachments). See docs/architecture/attachments.md.
export interface AttachmentMeta {
  file_id: string;
  name: string;
  mime: string;
  size_bytes: number;
  plaintext_sha256: string;
  // Set on outbound (user-staged) attachments to indicate they are local.
  staged?: boolean;
  // Inline payload (base64) when the agent emitted it under the inline tier.
  inline_data_b64?: string;
  // Optional attachment:// URI form for use in markdown.
  uri?: string;
}

// =============================================================================
// Transcript helpers
// =============================================================================

/** One turn in a conversation transcript — the shape the agent host expects
 *  as prior-message context on session start. Roles are restricted to the
 *  three the agent runtime understands. */
export interface TranscriptMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

/** PendingPayment is the snapshot the chat UI needs to render an x402
 *  PaymentRequiredModal: the wallet-bound challenge plus a human-readable
 *  price summary. onPaid is invoked with the wire-format mppx credential the
 *  modal produced (via WalletPayChallenge); onCancel dismisses without
 *  signing. The hook stashes this when a turn hits the x402 hard cap and
 *  clears it after either onPaid or onCancel runs. */
export interface PendingPayment {
  endpointSlug: string;
  ownerLabel: string;
  amount: string;
  currency: string;
  recipient: string;
  challengeWire: string;
  challengeId: string;
  prompt: string;
  onPaid: (credential: string) => Promise<void> | void;
  onCancel: () => void;
}

/** entriesToTranscript distills the rich AgentEntry[] (which mixes user
 *  messages, agent messages, tool calls, policy notices, etc.) down to the
 *  pure conversation transcript an agent needs as history. Only `user` and
 *  `message` (assistant) entries become turns; everything else — thinking,
 *  tool calls, policy notices, attachments, status — is by design omitted
 *  because they are derivable from the model context, not a part of it.
 *
 *  Used at hold time (so RecordSentReview captures the full thread) and at
 *  continuation time (so StartAgentSessionWithHistory replays it). The
 *  consistency between the two captures matters: a thread that goes user1 →
 *  assistant1 → user2 → assistant2(held) must continue with that same
 *  history minus the held turn (which is added back by the caller via
 *  responseText). */
export function entriesToTranscript(entries: AgentEntry[]): TranscriptMessage[] {
  const out: TranscriptMessage[] = [];
  for (const e of entries) {
    if (e.kind === 'user') {
      out.push({ role: 'user', content: e.content });
    } else if (e.kind === 'message') {
      out.push({ role: 'assistant', content: e.content });
    }
  }
  return out;
}

// =============================================================================
// Hook
// =============================================================================

interface UseAgentWorkflowProps {
  endpointPath: string | null;
  endpointName: string;
}

export function useAgentWorkflow({ endpointPath, endpointName }: UseAgentWorkflowProps) {
  const [entries, setEntries] = useState<AgentEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [awaitingInput, setAwaitingInput] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const entryCounterRef = useRef(0);

  // pendingPayment is non-null when the active turn hit an x402 policy whose
  // price exceeded the user's auto-pay cap. The chat UI renders
  // <PaymentRequiredModal> off this value; the modal's onPaid callback signs
  // a credential and restarts the session with it attached.
  const [pendingPayment, setPendingPayment] = useState<PendingPayment | null>(null);

  // Dedupe RecordSentReview calls by review_id so StrictMode double-invokes or
  // any event replay never write the same hold twice.
  const recordedReviewIdsRef = useRef<Set<string>>(new Set());

  // Streaming message accumulator for token events
  const streamingContentRef = useRef('');
  // Timer handle for batched token flushing (~frame-rate updates)
  const flushTimerRef = useRef<number | null>(null);

  // The endpoint a held request is attributed to — captured at session start
  // so it stays stable even if the user later changes the agent dropdown.
  const sessionEndpointRef = useRef<{ path: string; name: string }>({ path: '', name: '' });
  // The prompt of the turn currently in flight — used to record what the user
  // actually asked when a manual-review hold arrives for that turn.
  const lastUserPromptRef = useRef('');

  // originReviewIdRef carries the reviewId the current session is continuing
  // from, so a hold captured in this session can stamp parent_review_id and
  // the store can group both rows under one thread. Set by ReviewChatPane via
  // startSessionWithHistory(..., { originReviewId }); cleared on startSession
  // (fresh chat). After a hold is captured the ref bumps to the new reviewId
  // so a subsequent continuation in the same session chains correctly.
  const originReviewIdRef = useRef<string | null>(null);

  const makeId = () => {
    entryCounterRef.current += 1;
    return `agent-${entryCounterRef.current}`;
  };

  // Flush accumulated tokens from streamingContentRef into React state.
  // Called on a timer (batched) or synchronously before terminal events.
  const flushTokens = () => {
    // Cancel any pending scheduled flush
    if (flushTimerRef.current !== null) {
      cancelAnimationFrame(flushTimerRef.current);
      flushTimerRef.current = null;
    }

    const content = streamingContentRef.current;
    if (!content) return;

    setEntries(prev => {
      const last = prev[prev.length - 1];
      if (last?.kind === 'token') {
        // Update existing token entry in-place (single new array)
        const updated = prev.slice();
        updated[updated.length - 1] = { ...last, content };
        return updated;
      }
      // First token flush — create the entry
      return [...prev, {
        id: makeId(),
        kind: 'token' as const,
        content,
        timestamp: Date.now(),
      }];
    });
  };

  // Schedule a batched flush at the next animation frame if not already scheduled
  const scheduleFlush = () => {
    if (flushTimerRef.current !== null) return;
    flushTimerRef.current = requestAnimationFrame(flushTokens);
  };

  // Flush any pending batched tokens, then clear the streaming accumulator so
  // the next token stream starts fresh. Called before appending any non-token
  // entry (a message, policy notice, input request, or terminal entry).
  const resetStreaming = () => {
    flushTokens();
    streamingContentRef.current = '';
  };

  // Append a terminal entry, flush any pending tokens, and mark the session done.
  // Used for session.completed / session.cancelled / session.failed.
  const finalizeSession = (kind: AgentEntry['kind'], content: string) => {
    resetStreaming();
    setEntries(prev => [...prev, {
      id: makeId(),
      kind,
      content,
      timestamp: Date.now(),
    }]);
    setIsRunning(false);
    setAwaitingInput(false);
    sessionIdRef.current = null;
  };

  // Listen for agent events
  useEffect(() => {
    const unsubscribe = EventsOn('agent:event', (event: AgentStreamEvent) => {
      if (sessionIdRef.current && event.sessionId !== sessionIdRef.current) return;

      const data = event.data ?? {};

      switch (event.type) {
        case 'session.started':
          setIsRunning(true);
          break;

        case 'agent.thinking':
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'thinking',
            content: String(data.content ?? ''),
            timestamp: Date.now(),
          }]);
          break;

        case 'agent.status':
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'status',
            content: `${data.status ?? ''}${data.detail ? `: ${data.detail}` : ''}`,
            data,
            timestamp: Date.now(),
          }]);
          break;

        case 'agent.tool_call':
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'tool_call',
            content: String(data.tool_name ?? 'tool'),
            data,
            timestamp: Date.now(),
          }]);
          break;

        case 'agent.tool_result':
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'tool_result',
            content: String(data.result ?? ''),
            data,
            timestamp: Date.now(),
          }]);
          break;

        case 'agent.attachment': {
          // Inbound attachment from the agent. Surface as an attachment
          // timeline entry; the UI renders inline image previews when
          // inline_data_b64 is present, otherwise a download chip.
          const fileId = String(data.file_id ?? '');
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'attachment',
            content: String(data.name ?? fileId),
            data: { ...data, uri: fileId ? `attachment://${fileId}` : undefined },
            timestamp: Date.now(),
          }]);
          break;
        }

        case 'agent.message': {
          resetStreaming();
          const content = String(data.content ?? '');
          // A `policy` object marks this message as a policy notice (the reply
          // was blocked, or is pending review) — render it as a distinct card
          // rather than a normal agent reply.
          const policy = data.policy as Record<string, unknown> | undefined;
          const newEntry: AgentEntry = {
            id: makeId(),
            kind: policy ? 'policy' : 'message',
            content,
            data: policy,
            timestamp: Date.now(),
          };
          // Side effect lives inside setEntries so prev provides the fresh transcript; without this the closure captures the initial empty array.
          setEntries(prev => {
            const next = [...prev, newEntry];
            // A manual-review hold (a pending policy notice carrying a review_id)
            // is durably recorded so the user can track it in "Sent for Review" —
            // the chat transcript itself is in-memory and lost on restart. The
            // review_id discriminates a manual-review hold from a payment hold
            // (which arrives as agent.payment_required) or any other pending
            // notice. Capture is idempotent on review_id and fire-and-forget so
            // a ledger write never blocks or breaks the transcript.
            if (
              policy &&
              policy.status === 'pending' &&
              typeof policy.review_id === 'string' &&
              policy.review_id &&
              !recordedReviewIdsRef.current.has(policy.review_id)
            ) {
              const reviewId = policy.review_id;
              recordedReviewIdsRef.current.add(reviewId);
              const ep = sessionEndpointRef.current;
              // Capture the FULL conversation up to and including the held user
              // message — derive from `prev` (the policy entry itself is not
              // part of the transcript). A multi-turn chat held on turn N must
              // carry the prior N-1 turns so a later continuation can replay
              // the full thread.
              const transcript = entriesToTranscript(prev);
              // Fall back to lastUserPromptRef when entries are empty
              // (e.g. the policy held on the initial prompt before any state
              // had time to populate). Keeps Phase 1 single-turn capture working.
              const requestMessages = transcript.length > 0
                ? transcript
                : (lastUserPromptRef.current
                    ? [{ role: 'user', content: lastUserPromptRef.current }]
                    : []);
              const originReviewId = originReviewIdRef.current ?? '';
              // Fire the write, then refetch so the sidebar's thread list
              // picks up the new row. Cheap if duplicated — the store
              // dedupes via sentReviewsEqual.
              void RecordSentReview(main.SentReviewInput.createFrom({
                reviewId,
                endpointPath: ep.path,
                endpointName: ep.name,
                endpointType: 'agent',
                policyName: typeof policy.policy_name === 'string' ? policy.policy_name : '',
                requestMessages,
                // policy.reason carries the placeholder text the caller received;
                // content is the human-readable fallback sentence.
                placeholder: typeof policy.reason === 'string' ? policy.reason : content,
                originReviewId,
              }))
                .then(() => useAppStore.getState().fetchSentReviews())
                .catch(() => {
                  /* best-effort — the pending notice still renders if this fails */
                });
              // Subsequent holds in this same session (rare — typically the
              // session is cancelled when policy holds, but a chain is
              // possible) link to the freshly-captured review, not to the
              // session's original origin.
              originReviewIdRef.current = reviewId;
            }
            return next;
          });
          break;
        }

        case 'agent.payment_required': {
          // x402_pay_per_request policy held the turn until the caller settles
          // a charge. The producer cancels its session immediately after this
          // event (see [AGENT] Session ended logs), so the "retry" path is
          // really "start a fresh session with the signed credential
          // attached" — that's what StartAgentSessionWithCredential does.
          resetStreaming();
          const details = (data.details ?? {}) as Record<string, unknown>;
          const pick = (k: string): string => {
            const v = details[k];
            return typeof v === 'string' && v ? v : '';
          };
          const challengeWire =
            (typeof data.challenge === 'string' && data.challenge) ||
            pick('payment_challenge');
          const amount = pick('payment_amount');
          const currency = pick('payment_currency');
          const recipient = pick('payment_recipient');
          const challengeId = pick('challenge_id');
          const ep = sessionEndpointRef.current;
          const endpointSlug = ep.path;
          const prompt = lastUserPromptRef.current;
          if (!challengeWire || !endpointSlug || !prompt) {
            // Missing fields means we cannot retry; surface a policy notice
            // so the user sees that the turn was held but no action is
            // possible from the UI. (Producer-side bug — log loudly.)
            setEntries(prev => [...prev, {
              id: makeId(),
              kind: 'policy',
              content: '',
              data: {
                status: 'pending',
                reason: 'Payment required, but the producer did not include a usable challenge.',
              },
              timestamp: Date.now(),
            }]);
            break;
          }

          const signAndRestart = async (cred: string) => {
            try {
              const sessionId = await StartAgentSessionWithCredential(
                endpointSlug, prompt, cred,
              );
              sessionIdRef.current = sessionId;
            } catch (err) {
              setEntries(prev => [...prev, {
                id: makeId(),
                kind: 'error',
                content: `Payment retry failed: ${err}`,
                timestamp: Date.now(),
              }]);
              setIsRunning(false);
            }
          };

          const signAndRetry = async () => {
            try {
              const credential = await WalletPayChallenge(challengeWire);
              await signAndRestart(credential);
            } catch (err) {
              setEntries(prev => [...prev, {
                id: makeId(),
                kind: 'error',
                content: `Payment failed: ${err}`,
                timestamp: Date.now(),
              }]);
              setIsRunning(false);
            }
          };

          (async () => {
            let decision;
            try {
              decision = await EvaluatePaymentDecision(endpointSlug, amount, currency);
            } catch (err) {
              // Cap evaluator broken → fall back to a blocking prompt.
              decision = main.PaymentDecision.createFrom({
                action: 'prompt',
                reason: `cap evaluation failed: ${String(err)}`,
              });
            }
            if (decision.action === 'auto_pay' || decision.action === 'toast_pay') {
              await signAndRetry();
              return;
            }
            // 'prompt' — render the modal; resolves via onPaid/onCancel.
            setPendingPayment({
              endpointSlug,
              ownerLabel: endpointSlug,
              amount,
              currency,
              recipient,
              challengeWire,
              challengeId,
              prompt,
              onPaid: async (credential: string) => {
                setPendingPayment(null);
                await signAndRestart(credential);
              },
              onCancel: () => {
                setPendingPayment(null);
                setEntries(prev => [...prev, {
                  id: makeId(),
                  kind: 'cancelled',
                  content: 'Payment declined — turn cancelled.',
                  timestamp: Date.now(),
                }]);
                setIsRunning(false);
              },
            });
          })().catch(() => { /* errors surfaced above */ });
          break;
        }

        case 'agent.token': {
          const token = String(data.token ?? '');
          streamingContentRef.current += token;
          // Batch token updates — schedule a flush at the next animation frame
          scheduleFlush();
          break;
        }

        case 'agent.request_input':
          resetStreaming();
          setAwaitingInput(true);
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'request_input',
            content: String(data.prompt ?? ''),
            timestamp: Date.now(),
          }]);
          break;

        case 'session.completed':
          finalizeSession('completed', 'Session completed');
          break;

        case 'session.cancelled':
          // Backend rewrites a user-initiated stop's misleading subprocess
          // "signal: killed" failure into this event so the UI treats it as
          // a graceful termination rather than an error.
          finalizeSession('cancelled', 'Session stopped');
          break;

        case 'session.failed':
          finalizeSession('error', String(data.error ?? 'Session failed'));
          break;
      }
    });

    return () => {
      unsubscribe();
      // Cancel any pending token flush
      if (flushTimerRef.current !== null) {
        cancelAnimationFrame(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      // Stop any running session when the component unmounts
      if (sessionIdRef.current) {
        StopAgentSession().catch(() => {});
        sessionIdRef.current = null;
      }
    };
  }, []);

  const startSession = useCallback(async (prompt: string) => {
    if (!endpointPath || isRunning) return;

    // Reset state
    if (flushTimerRef.current !== null) {
      cancelAnimationFrame(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    streamingContentRef.current = '';
    entryCounterRef.current = 0;
    // Pin the endpoint + opening prompt for this session so a held request is
    // attributed correctly even if the agent dropdown changes mid-session.
    sessionEndpointRef.current = { path: endpointPath, name: endpointName };
    lastUserPromptRef.current = prompt;
    // Fresh chat — no continuation parent.
    originReviewIdRef.current = null;
    setEntries([{
      id: 'user-0',
      kind: 'user',
      content: prompt,
      timestamp: Date.now(),
    }]);
    setIsRunning(true);
    setAwaitingInput(false);

    try {
      const sessionId = await StartAgentSession(endpointPath, prompt);
      sessionIdRef.current = sessionId;
    } catch (err) {
      setEntries(prev => [...prev, {
        id: makeId(),
        kind: 'error',
        content: `Failed to start session: ${err}`,
        timestamp: Date.now(),
      }]);
      setIsRunning(false);
    }
  }, [endpointPath, endpointName, isRunning]);

  const sendInput = useCallback(async (content: string) => {
    if (!isRunning) return;
    setAwaitingInput(false);

    // Track the in-flight turn's prompt so a manual-review hold on the reply
    // records what the user actually asked.
    lastUserPromptRef.current = content;

    // Add user message to entries
    setEntries(prev => [...prev, {
      id: makeId(),
      kind: 'user',
      content,
      timestamp: Date.now(),
    }]);

    try {
      await SendAgentMessage(content);
    } catch (err) {
      setEntries(prev => [...prev, {
        id: makeId(),
        kind: 'error',
        content: `Failed to send message: ${err}`,
        timestamp: Date.now(),
      }]);
    }
  }, [isRunning]);

  const stopSession = useCallback(async () => {
    try {
      await StopAgentSession();
    } catch {
      // ignore
    }
    setIsRunning(false);
    setAwaitingInput(false);
    sessionIdRef.current = null;
  }, []);

  const clearEntries = useCallback(() => {
    if (flushTimerRef.current !== null) {
      cancelAnimationFrame(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setEntries([]);
    setIsRunning(false);
    setAwaitingInput(false);
    sessionIdRef.current = null;
    streamingContentRef.current = '';
  }, []);

  // startSessionWithHistory is the continuation variant of startSession used
  // when the user types a follow-up in a recovered-from-review chat: the prior
  // turns are seeded into entries[] AND sent to the host as conversation
  // history. The agent sees the full thread (so its reply is coherent with
  // the held turn) and the transcript visually picks up where the review left
  // off rather than starting blank.
  //
  // overrideEndpointPath / overrideEndpointName let the caller pin a specific
  // endpoint even when the global chatSelectedModel has not yet been switched
  // (the chat UI changes the agent dropdown asynchronously after this call,
  // so we can't rely on the closed-over endpointPath/endpointName).
  const startSessionWithHistory = useCallback(async (
    history: TranscriptMessage[],
    prompt: string,
    overrides?: { endpointPath: string; endpointName: string; originReviewId?: string },
  ) => {
    const targetPath = overrides?.endpointPath ?? endpointPath;
    const targetName = overrides?.endpointName ?? endpointName;
    if (!targetPath || isRunning) return;

    // Reset transient streaming state.
    if (flushTimerRef.current !== null) {
      cancelAnimationFrame(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    streamingContentRef.current = '';
    entryCounterRef.current = 0;

    sessionEndpointRef.current = { path: targetPath, name: targetName };
    lastUserPromptRef.current = prompt;
    // Stamp the parent so any hold captured in this continuation session links
    // back to the review the user was viewing. Empty string is treated as "no
    // parent" by the IPC (matches the omitempty JSON tag).
    originReviewIdRef.current = overrides?.originReviewId || null;

    // Seed entries with the prior history so the transcript reads continuously,
    // then append the new user prompt. The renderer treats these like any
    // freshly-arrived user/message entries.
    const seeded: AgentEntry[] = history.map((m, i) => ({
      id: `seed-${i}`,
      kind: m.role === 'user' ? 'user' as const : 'message' as const,
      content: m.content,
      timestamp: Date.now() - (history.length - i),
    }));
    seeded.push({
      id: 'user-0',
      kind: 'user',
      content: prompt,
      timestamp: Date.now(),
    });
    setEntries(seeded);
    setIsRunning(true);
    setAwaitingInput(false);

    try {
      const sessionId = await StartAgentSessionWithHistory(
        targetPath,
        prompt,
        JSON.stringify(history),
      );
      sessionIdRef.current = sessionId;
    } catch (err) {
      setEntries(prev => [...prev, {
        id: makeId(),
        kind: 'error',
        content: `Failed to continue session: ${err}`,
        timestamp: Date.now(),
      }]);
      setIsRunning(false);
    }
  }, [endpointPath, endpointName, isRunning]);

  const dismissPayment = useCallback(() => {
    setPendingPayment((prev) => {
      if (prev) prev.onCancel();
      return null;
    });
  }, []);

  return {
    entries,
    isRunning,
    awaitingInput,
    startSession,
    startSessionWithHistory,
    sendInput,
    stopSession,
    clearEntries,
    pendingPayment,
    dismissPayment,
  };
}
