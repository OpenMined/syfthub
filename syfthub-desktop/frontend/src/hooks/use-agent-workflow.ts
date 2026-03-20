import { useCallback, useEffect, useRef, useState } from 'react';
import { StartAgentSession, SendAgentMessage, StopAgentSession } from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';

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
  kind: 'user' | 'thinking' | 'status' | 'tool_call' | 'tool_result' | 'message' | 'token' | 'request_input' | 'error' | 'completed';
  content: string;
  data?: Record<string, unknown>;
  timestamp: number;
}

// =============================================================================
// Hook
// =============================================================================

interface UseAgentWorkflowProps {
  endpointSlug: string | null;
}

export function useAgentWorkflow({ endpointSlug }: UseAgentWorkflowProps) {
  const [entries, setEntries] = useState<AgentEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [awaitingInput, setAwaitingInput] = useState(false);
  const [inputPrompt, setInputPrompt] = useState('');
  const sessionIdRef = useRef<string | null>(null);
  const entryCounterRef = useRef(0);

  // Streaming message accumulator for token events
  const streamingContentRef = useRef('');
  // Timer handle for batched token flushing (~frame-rate updates)
  const flushTimerRef = useRef<number | null>(null);
  // Track whether we've already created a token entry for the current stream
  const hasTokenEntryRef = useRef(false);

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

        case 'agent.message': {
          // Flush any pending batched tokens before adding the message
          flushTokens();
          streamingContentRef.current = '';
          hasTokenEntryRef.current = false;
          const content = String(data.content ?? '');
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'message',
            content,
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
          // Flush any pending batched tokens before processing input request
          flushTokens();
          streamingContentRef.current = '';
          hasTokenEntryRef.current = false;
          setAwaitingInput(true);
          setInputPrompt(String(data.prompt ?? 'Enter your response:'));
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'request_input',
            content: String(data.prompt ?? ''),
            timestamp: Date.now(),
          }]);
          break;

        case 'session.completed':
          // Flush any pending batched tokens before completing
          flushTokens();
          streamingContentRef.current = '';
          hasTokenEntryRef.current = false;
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'completed',
            content: 'Session completed',
            timestamp: Date.now(),
          }]);
          setIsRunning(false);
          setAwaitingInput(false);
          sessionIdRef.current = null;
          break;

        case 'session.failed':
          // Flush any pending batched tokens before reporting failure
          flushTokens();
          streamingContentRef.current = '';
          hasTokenEntryRef.current = false;
          setEntries(prev => [...prev, {
            id: makeId(),
            kind: 'error',
            content: String(data.error ?? 'Session failed'),
            timestamp: Date.now(),
          }]);
          setIsRunning(false);
          setAwaitingInput(false);
          sessionIdRef.current = null;
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
    if (!endpointSlug || isRunning) return;

    // Reset state
    if (flushTimerRef.current !== null) {
      cancelAnimationFrame(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    streamingContentRef.current = '';
    hasTokenEntryRef.current = false;
    entryCounterRef.current = 0;
    setEntries([{
      id: 'user-0',
      kind: 'user',
      content: prompt,
      timestamp: Date.now(),
    }]);
    setIsRunning(true);
    setAwaitingInput(false);

    try {
      const sessionId = await StartAgentSession(endpointSlug, prompt);
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
  }, [endpointSlug, isRunning]);

  const sendInput = useCallback(async (content: string) => {
    if (!isRunning) return;
    setAwaitingInput(false);

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

  return {
    entries,
    isRunning,
    awaitingInput,
    inputPrompt,
    startSession,
    sendInput,
    stopSession,
    clearEntries,
  };
}
