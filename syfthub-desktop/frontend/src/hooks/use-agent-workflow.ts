import { useCallback, useEffect, useRef, useState } from 'react';
import {
  StartAgentSession,
  StartAgentSessionWithHistory,
  SendAgentMessage,
  StopAgentSession,
  RecordSentReview,
} from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';
import { main } from '../../wailsjs/go/models';

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

  // entriesRef mirrors `entries` so the EventsOn handler (which is registered
  // ONCE with empty deps) can read the live value instead of the empty array
  // captured at mount time. Without this, callbacks that capture state by
  // closure (e.g. RecordSentReview's transcript build) see stale data — every
  // manual-review hold would record an empty conversation, which is exactly
  // the regression that produced "the chat got cleaned after approval".
  const entriesRef = useRef<AgentEntry[]>([]);
  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  // Streaming message accumulator for token events
  const streamingContentRef = useRef('');
  // Timer handle for batched token flushing (~frame-rate updates)
  const flushTimerRef = useRef<number | null>(null);
  // Track whether we've already created a token entry for the current stream
  const hasTokenEntryRef = useRef(false);

  // The endpoint a held request is attributed to — captured at session start
  // so it stays stable even if the user later changes the agent dropdown.
  const sessionEndpointRef = useRef<{ path: string; name: string }>({ path: '', name: '' });
  // The prompt of the turn currently in flight — used to record what the user
  // actually asked when a manual-review hold arrives for that turn.
  const lastUserPromptRef = useRef('');

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
    hasTokenEntryRef.current = true;
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
    hasTokenEntryRef.current = false;
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
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: policy ? 'policy' : 'message',
            content,
            data: policy,
            timestamp: Date.now(),
          }]);

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
            policy.review_id
          ) {
            const ep = sessionEndpointRef.current;
            // Capture the FULL conversation up to and including the held user
            // message, not just lastUserPromptRef. A multi-turn chat that gets
            // held on turn N must carry the prior N-1 turns so a later
            // continuation can replay the full thread.
            //
            // entriesRef.current — NOT the closed-over `entries` — because the
            // EventsOn handler is registered once with empty deps and its
            // closure freezes the initial (empty) entries forever. Using the
            // ref gives us the current value at event time.
            const transcript = entriesToTranscript(entriesRef.current);
            // Fall back to lastUserPromptRef when entries are empty
            // (e.g. the policy held on the initial prompt before any state
            // had time to populate). Keeps Phase 1 single-turn capture working.
            const requestMessages = transcript.length > 0
              ? transcript
              : (lastUserPromptRef.current
                  ? [{ role: 'user', content: lastUserPromptRef.current }]
                  : []);
            void RecordSentReview(main.SentReviewInput.createFrom({
              reviewId: policy.review_id,
              endpointPath: ep.path,
              endpointName: ep.name,
              endpointType: 'agent',
              policyName: typeof policy.policy_name === 'string' ? policy.policy_name : '',
              requestMessages,
              // policy.reason carries the placeholder text the caller received;
              // content is the human-readable fallback sentence.
              placeholder: typeof policy.reason === 'string' ? policy.reason : content,
            })).catch(() => {
              /* best-effort — the pending notice still renders if this fails */
            });
          }
          break;
        }

        case 'agent.payment_required': {
          // A transaction-style policy holds the turn until the user settles
          // a charge. Surface it as a pending policy notice. (The full payment
          // flow is not wired up yet — this just stops the turn vanishing
          // silently.)
          resetStreaming();
          const amount = String(data.amount ?? '').trim();
          const currency = String(data.currency ?? '').trim();
          const priced = amount ? `${amount}${currency ? ` ${currency}` : ''}` : '';
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'policy',
            content: '',
            data: {
              status: 'pending',
              reason: priced
                ? `This request requires a payment of ${priced} to continue.`
                : 'This request requires a payment to continue.',
            },
            timestamp: Date.now(),
          }]);
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
    hasTokenEntryRef.current = false;
    entryCounterRef.current = 0;
    // Pin the endpoint + opening prompt for this session so a held request is
    // attributed correctly even if the agent dropdown changes mid-session.
    sessionEndpointRef.current = { path: endpointPath, name: endpointName };
    lastUserPromptRef.current = prompt;
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
    hasTokenEntryRef.current = false;
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
    overrides?: { endpointPath: string; endpointName: string },
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
    hasTokenEntryRef.current = false;
    entryCounterRef.current = 0;

    sessionEndpointRef.current = { path: targetPath, name: targetName };
    lastUserPromptRef.current = prompt;

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

  return {
    entries,
    isRunning,
    awaitingInput,
    startSession,
    startSessionWithHistory,
    sendInput,
    stopSession,
    clearEntries,
  };
}
