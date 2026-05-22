import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import { main } from '../../wailsjs/go/models';
import {
  EvaluatePaymentDecision,
  StopChat,
  StreamChat,
  WalletPayChallenge,
} from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';

import type {
  ChatStreamEvent,
  PipelineStep,
  ProcessingStatus,
  SourceProgressInfo,
  SourcesData,
  WorkflowAction,
  WorkflowState,
} from '@/lib/chat-types';
import { PaymentDecisionAction } from '@/hooks/use-payment-caps';

// Re-export types consumed by status-indicator and other chat components
export type { PipelineStep, ProcessingStatus, SourceProgressInfo } from '@/lib/chat-types';
import type { EndpointInfo } from '@/stores/appStore';

// =============================================================================
// Message Types
// =============================================================================

export interface UserMessage {
  id: string;
  role: 'user';
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: 'assistant';
  content: string;
  sources?: SourcesData;
  /** Position-annotated content from the done event for citation rendering. */
  annotatedResponse?: string;
  isStreaming?: boolean;
}

export type ChatMessage = UserMessage | AssistantMessage;

// =============================================================================
// Reducer
// =============================================================================

// =============================================================================
// Stream event → ProcessingStatus reducer helper
// =============================================================================

function processStreamEvent(
  status: ProcessingStatus | null,
  event: ChatStreamEvent,
): ProcessingStatus | null {
  switch (event.type) {
    case 'retrieval_start': {
      if (event.sourceCount === 0) {
        return {
          phase: 'retrieving',
          message: 'Preparing request…',
          completedSources: [],
          steps: [{ id: 'generation', label: 'Generating response', status: 'pending' }],
        };
      }
      return {
        phase: 'retrieving',
        message: `Searching ${event.sourceCount} ${event.sourceCount === 1 ? 'source' : 'sources'}…`,
        retrieval: { completed: 0, total: event.sourceCount, documentsFound: 0 },
        completedSources: [],
        steps: [
          { id: 'retrieval', label: 'Searching sources', status: 'active' },
          { id: 'generation', label: 'Generating response', status: 'pending' },
        ] satisfies PipelineStep[],
      };
    }

    case 'source_complete': {
      if (!status) return null;
      const newSource: SourceProgressInfo = {
        path: event.path,
        displayName: event.path.split('/').pop() ?? event.path,
        status: event.status,
        documents: event.documentsRetrieved,
      };
      const completedSources = [...status.completedSources, newSource];
      const completed = completedSources.length;
      const total = status.retrieval?.total ?? completed;
      const documentsFound =
        (status.retrieval?.documentsFound ?? 0) +
        (event.status === 'success' ? event.documentsRetrieved : 0);
      return {
        ...status,
        message: `Retrieved from ${completed}/${total} ${total === 1 ? 'source' : 'sources'}…`,
        retrieval: { completed, total, documentsFound },
        completedSources,
      };
    }

    case 'retrieval_complete': {
      if (!status) return null;
      const documentCount = event.totalDocuments;
      const documentLabel = documentCount === 1 ? 'document' : 'documents';
      const message =
        documentCount > 0
          ? `Found ${documentCount} relevant ${documentLabel}`
          : 'No relevant documents found';
      return {
        ...status,
        message,
        timing: { ...status.timing, retrievalMs: event.timeMs },
      };
    }

    case 'generation_start': {
      return {
        phase: 'generating',
        message: 'Generating response…',
        completedSources: status?.completedSources ?? [],
        retrieval: status?.retrieval,
        timing: status?.timing,
        steps: (
          status?.steps ?? [{ id: 'generation', label: 'Generating response', status: 'pending' }]
        ).map((step) =>
          step.id === 'generation'
            ? { ...step, status: 'active' as const }
            : step.status === 'complete'
              ? step
              : { ...step, status: 'complete' as const },
        ),
      };
    }

    case 'generation_heartbeat': {
      if (!status || status.phase !== 'generating') return status;
      const elapsedSec = Math.floor((event.timeMs ?? 0) / 1000);
      return {
        ...status,
        generationElapsedMs: event.timeMs,
        message: `Generating response… ${String(elapsedSec)}s`,
        steps: status.steps.map((step) =>
          step.id === 'generation'
            ? { ...step, description: `${String(elapsedSec)}s elapsed` }
            : step,
        ),
      };
    }

    case 'token': {
      if (!status || status.phase === 'streaming') return status;
      return {
        ...status,
        phase: 'streaming',
        message: 'Writing response…',
        steps: status.steps.map((step) =>
          step.id === 'generation' ? { ...step, status: 'complete' as const } : step,
        ),
      };
    }

    case 'done': {
      return null;
    }

    case 'error': {
      return {
        phase: 'error',
        message: event.message,
        completedSources: status?.completedSources ?? [],
        retrieval: status?.retrieval,
        timing: status?.timing,
        steps: status?.steps ?? [],
      };
    }

    default:
      return status;
  }
}

// =============================================================================
// State
// =============================================================================

const initialWorkflowState: WorkflowState = {
  phase: 'idle',
  query: null,
  selectedSources: new Set(),
  processingStatus: null,
  streamedContent: '',
  aggregatorSources: {},
  error: null,
};

function workflowReducer(state: WorkflowState, action: WorkflowAction): WorkflowState {
  switch (action.type) {
    case 'START_EXECUTING': {
      return {
        ...state,
        phase: 'preparing',
        query: action.query,
        selectedSources: action.sourceIds,
        streamedContent: '',
        aggregatorSources: {},
        error: null,
        processingStatus: null,
      };
    }

    case 'STREAM_EVENT': {
      const newStatus = processStreamEvent(state.processingStatus, action.event);
      if (action.event.type === 'done') {
        return {
          ...state,
          phase: 'complete',
          aggregatorSources: action.event.sources ?? {},
          processingStatus: null,
        };
      }
      if (action.event.type === 'error') {
        return {
          ...state,
          phase: 'error',
          error: action.event.message,
          processingStatus: newStatus,
        };
      }
      if (action.event.type === 'token') {
        return {
          ...state,
          streamedContent: state.streamedContent + action.event.content,
          processingStatus: newStatus,
        };
      }
      return { ...state, phase: 'streaming', processingStatus: newStatus };
    }

    case 'ERROR': {
      return { ...state, phase: 'error', error: action.error };
    }

    case 'RESET': {
      return initialWorkflowState;
    }

    default:
      return state;
  }
}

// =============================================================================
// Hook
// =============================================================================

export interface UseChatWorkflowOptions {
  selectedModel: EndpointInfo | null;
  selectedSources: EndpointInfo[];
}

/**
 * Snapshot of an active payment_required prompt awaiting user action.
 *
 * The chat workflow stores this in state when a producer signals payment is
 * required AND EvaluatePaymentDecision returned "prompt" (i.e. either over
 * the hard cap, or in an unfamiliar currency). The UI is expected to render
 * <PaymentRequiredModal> bound to this snapshot. Auto-pay and toast-pay
 * cases never reach this state — they sign-and-retry transparently.
 */
export interface PendingPaymentPrompt {
  endpointSlug: string;
  ownerLabel: string;
  amount: string;
  currency: string;
  recipient: string;
  challengeWire: string;
  challengeId?: string;
  /** Bound callback that the modal invokes with the signed credential. */
  onPaid: (credential: string) => Promise<void>;
  /** Bound callback invoked when the user dismisses without paying. */
  onCancel: () => void;
}

export interface UseChatWorkflowReturn {
  messages: ChatMessage[];
  workflowState: WorkflowState;
  sendMessage: (prompt: string) => Promise<void>;
  stopStream: () => Promise<void>;
  clearMessages: () => void;
  isStreaming: boolean;
  /** Non-null when a payment_required modal should be displayed. */
  pendingPayment: PendingPaymentPrompt | null;
  /** Dismiss the pending payment prompt without paying. */
  dismissPaymentPrompt: () => void;
}

/**
 * Wire-format payload of a `payment_required` chat-stream event.
 *
 * Not yet part of the generated `ChatStreamEvent` discriminated union (added
 * to chat-types.ts by a separate unit), so we narrow at the event-handler
 * level with a lightweight runtime predicate.
 */
interface PaymentRequiredStreamEvent {
  type: 'payment_required';
  /** "owner/slug" pair the producer is requesting payment for. */
  endpointSlug?: string;
  /** Wire-format payment_challenge from the producer. */
  challenge?: string;
  amount?: string;
  currency?: string;
  recipient?: string;
  challengeId?: string;
  /** Hub-side metadata bag for non-agent endpoints (mirrors PaymentMetadataKeys). */
  details?: Record<string, unknown>;
}

function isPaymentRequiredEvent(
  event: ChatStreamEvent | PaymentRequiredStreamEvent,
): event is PaymentRequiredStreamEvent {
  return (event as { type?: string }).type === 'payment_required';
}

/** Pull payment fields from either a flat event payload or its `details` map. */
function extractPaymentFields(event: PaymentRequiredStreamEvent): {
  endpointSlug: string;
  amount: string;
  currency: string;
  recipient: string;
  challengeWire: string;
  challengeId: string;
} {
  const details = (event.details ?? {}) as Record<string, unknown>;
  const pick = (k: string, fallback: string | undefined): string => {
    const v = details[k];
    if (typeof v === 'string' && v.length > 0) return v;
    return fallback ?? '';
  };
  return {
    endpointSlug: event.endpointSlug ?? pick('endpoint_slug', ''),
    amount: event.amount ?? pick('payment_amount', ''),
    currency: event.currency ?? pick('payment_currency', ''),
    recipient: event.recipient ?? pick('payment_recipient', ''),
    challengeWire: event.challenge ?? pick('payment_challenge', ''),
    challengeId: event.challengeId ?? pick('challenge_id', ''),
  };
}

/**
 * ChatRequest is auto-generated from the Go struct and does not yet declare
 * payment_credential. The producer-side decoder accepts it as an additional
 * field, so we attach it via this loose extension at the call site.
 */
interface ChatRequestWithPayment extends main.ChatRequest {
  payment_credential?: string;
  payment_challenge_id?: string;
}

export function useChatWorkflow({
  selectedModel,
  selectedSources,
}: UseChatWorkflowOptions): UseChatWorkflowReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [workflowState, dispatch] = useReducer(workflowReducer, initialWorkflowState);
  const [pendingPayment, setPendingPayment] = useState<PendingPaymentPrompt | null>(null);

  // Track id of the message being streamed into so token updates hit the right msg
  const streamingIdRef = useRef<string | null>(null);

  // Mirror messages state in a ref so sendMessage can read without re-creating
  const messagesRef = useRef(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // Cache the most recent request payload so a payment_required event can
  // resubmit it verbatim with payment_credential added. Mutated by sendMessage
  // and read by the retry helper.
  const lastRequestRef = useRef<main.ChatRequest | null>(null);
  // Cache the assistant placeholder id so the retry continues streaming
  // into the same bubble (rather than appending a second empty assistant
  // message). Cleared on done/error.
  const placeholderIdRef = useRef<string | null>(null);

  /**
   * Re-issue the most recent request with payment_credential attached.
   *
   * Used by both auto-pay and modal-prompt code paths. Reads lastRequestRef
   * — caller is responsible for ensuring it is set (sendMessage always sets
   * it before issuing StreamChat).
   */
  const retryRequestWithCredential = useCallback(
    async (credential: string, challengeId?: string) => {
      const last = lastRequestRef.current;
      if (!last) {
        dispatch({ type: 'ERROR', error: 'No request to retry after payment' });
        return;
      }
      try {
        const request: ChatRequestWithPayment = main.ChatRequest.createFrom({
          ...last,
        }) as ChatRequestWithPayment;
        request.payment_credential = credential;
        if (challengeId) {
          request.payment_challenge_id = challengeId;
        }
        await StreamChat(request);
      } catch (err) {
        // Clear the cached request so a delayed/duplicate payment_required
        // event cannot silently replay this prompt against a fresh
        // credential — the user did not re-issue the request after the
        // error, so any later retry would charge the wallet without
        // explicit consent.
        lastRequestRef.current = null;
        const id = streamingIdRef.current;
        if (id) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === id && msg.role === 'assistant'
                ? { ...msg, isStreaming: false, content: msg.content || `Error: ${String(err)}` }
                : msg,
            ),
          );
          streamingIdRef.current = null;
        }
        dispatch({ type: 'ERROR', error: String(err) });
      }
    },
    [],
  );

  /**
   * Handle a payment_required event by consulting the per-endpoint cap store
   * and either auto-paying, toast-paying, or surfacing the modal prompt.
   */
  const handlePaymentRequired = useCallback(
    async (event: PaymentRequiredStreamEvent) => {
      const fields = extractPaymentFields(event);
      if (!fields.challengeWire || !fields.endpointSlug) {
        dispatch({
          type: 'ERROR',
          error: 'Payment required but challenge/endpoint metadata is missing',
        });
        return;
      }
      let decision;
      try {
        decision = await EvaluatePaymentDecision(
          fields.endpointSlug,
          fields.amount,
          fields.currency,
        );
      } catch (err) {
        // Fall back to a blocking prompt on evaluator failure — we'd rather
        // ask the user than silently auto-pay against a stale cap.
        decision = main.PaymentDecision.createFrom({
          action: PaymentDecisionAction.Prompt,
          reason: `cap evaluation failed: ${String(err)}`,
        });
      }

      const signAndRetry = async () => {
        try {
          const credential = await WalletPayChallenge(
            fields.challengeWire,
            fields.amount,
            fields.currency,
          );
          await retryRequestWithCredential(credential, fields.challengeId);
        } catch (err) {
          dispatch({ type: 'ERROR', error: `Payment failed: ${String(err)}` });
          const id = streamingIdRef.current;
          if (id) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === id && msg.role === 'assistant'
                  ? {
                      ...msg,
                      isStreaming: false,
                      content: msg.content || `Payment failed: ${String(err)}`,
                    }
                  : msg,
              ),
            );
            streamingIdRef.current = null;
          }
        }
      };

      if (decision.action === PaymentDecisionAction.AutoPay) {
        await signAndRetry();
        return;
      }
      if (decision.action === PaymentDecisionAction.ToastPay) {
        // No global toast library is installed yet; surface the announcement
        // via the workflow status so the existing status-indicator widget
        // renders it. The producer's normal generation_start event will
        // overwrite this once the retry resumes.
        dispatch({
          type: 'STREAM_EVENT',
          event: {
            type: 'generation_heartbeat',
            timeMs: 0,
          } as ChatStreamEvent,
        });
        await signAndRetry();
        return;
      }

      // 'prompt' — stash the snapshot so <PaymentRequiredModal> renders.
      setPendingPayment({
        endpointSlug: fields.endpointSlug,
        ownerLabel: fields.endpointSlug,
        amount: fields.amount,
        currency: fields.currency,
        recipient: fields.recipient,
        challengeWire: fields.challengeWire,
        challengeId: fields.challengeId,
        onPaid: async (credential: string) => {
          setPendingPayment(null);
          await retryRequestWithCredential(credential, fields.challengeId);
        },
        onCancel: () => {
          setPendingPayment(null);
          // Drop the cached request so a duplicate or delayed
          // payment_required event delivered after cancel cannot silently
          // resubmit a paid request the user explicitly declined.
          lastRequestRef.current = null;
          // The producer is still holding the request open; cancel cleanly
          // so the spinner stops and the user can retry later.
          void StopChat().catch(() => {});
          const id = streamingIdRef.current;
          if (id) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === id && msg.role === 'assistant'
                  ? { ...msg, isStreaming: false, content: msg.content || 'Payment declined.' }
                  : msg,
              ),
            );
            streamingIdRef.current = null;
          }
          dispatch({ type: 'RESET' });
        },
      });
    },
    [retryRequestWithCredential],
  );

  // Register Wails event listener once
  useEffect(() => {
    const unsubscribe = EventsOn(
      'chat:stream-event',
      (event: ChatStreamEvent | PaymentRequiredStreamEvent) => {
        // payment_required isn't part of the generated discriminated union;
        // intercept it before the reducer dispatches so the workflow state
        // doesn't see an unknown event type.
        if (isPaymentRequiredEvent(event)) {
          void handlePaymentRequired(event);
          return;
        }

        dispatch({ type: 'STREAM_EVENT', event });

        if (event.type === 'token') {
          const id = streamingIdRef.current;
          if (id) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === id && msg.role === 'assistant'
                  ? { ...msg, content: msg.content + event.content }
                  : msg
              )
            );
          }
        } else if (event.type === 'done') {
          const id = streamingIdRef.current;
          if (id) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === id && msg.role === 'assistant'
                  ? {
                      ...msg,
                      isStreaming: false,
                      annotatedResponse: event.response,
                      sources: event.sources ?? {},
                    }
                  : msg
              )
            );
            streamingIdRef.current = null;
            placeholderIdRef.current = null;
            // Clear the cached request so a future payment_required event
            // doesn't accidentally fire after the original stream completed.
            lastRequestRef.current = null;
          }
        } else if (event.type === 'error') {
          const id = streamingIdRef.current;
          if (id) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === id && msg.role === 'assistant'
                  ? {
                      ...msg,
                      isStreaming: false,
                      content: msg.content || `Something went wrong: ${event.message}`,
                    }
                  : msg
              )
            );
            streamingIdRef.current = null;
            placeholderIdRef.current = null;
            lastRequestRef.current = null;
          }
        }
      },
    );

    return () => {
      unsubscribe();
    };
  }, [handlePaymentRequired]);

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!selectedModel) return;
      if (workflowState.phase === 'preparing' || workflowState.phase === 'streaming') return;

      const userMsgId = `user-${Date.now()}`;
      const assistantMsgId = `asst-${Date.now()}-${Math.random().toString(36).slice(2)}`;

      // Snapshot history before adding new messages (read from ref to avoid stale closure)
      const historySnapshot: { role: string; content: string }[] = messagesRef.current.map((m) => ({
        role: m.role,
        content:
          m.role === 'assistant'
            ? (m as AssistantMessage).annotatedResponse ?? m.content
            : m.content,
      }));

      // Optimistically add user + placeholder assistant messages
      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: 'user', content: prompt } satisfies UserMessage,
        { id: assistantMsgId, role: 'assistant', content: '', isStreaming: true } satisfies AssistantMessage,
      ]);
      streamingIdRef.current = assistantMsgId;

      dispatch({
        type: 'START_EXECUTING',
        query: prompt,
        sourceIds: new Set(selectedSources.map((s) => s.slug)),
      });

      try {
        const request = main.ChatRequest.createFrom({
          prompt,
          model: { slug: selectedModel.slug },
          dataSources: selectedSources.map((s) => ({ slug: s.slug })),
          messages: historySnapshot,
        });

        // Cache for the payment-required retry path (handlePaymentRequired
        // resubmits this exact payload with payment_credential added).
        lastRequestRef.current = request;
        placeholderIdRef.current = assistantMsgId;

        await StreamChat(request);
        // StreamChat returns immediately — events arrive via EventsOn('chat:stream-event')
      } catch (err) {
        dispatch({ type: 'ERROR', error: String(err) });
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId && msg.role === 'assistant'
              ? { ...msg, content: `Error: ${String(err)}`, isStreaming: false }
              : msg
          )
        );
        streamingIdRef.current = null;
      }
    },
    [selectedModel, selectedSources, workflowState.phase]
  );

  const stopStream = useCallback(async () => {
    try {
      await StopChat();
    } catch {
      // Ignore stop errors
    }
    const id = streamingIdRef.current;
    if (id) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === id && msg.role === 'assistant' ? { ...msg, isStreaming: false } : msg
        )
      );
      streamingIdRef.current = null;
    }
    placeholderIdRef.current = null;
    lastRequestRef.current = null;
    setPendingPayment(null);
    dispatch({ type: 'RESET' });
  }, []);

  const clearMessages = useCallback(() => {
    if (streamingIdRef.current) {
      void StopChat().catch(() => {});
      streamingIdRef.current = null;
    }
    placeholderIdRef.current = null;
    lastRequestRef.current = null;
    setPendingPayment(null);
    setMessages([]);
    dispatch({ type: 'RESET' });
  }, []);

  const dismissPaymentPrompt = useCallback(() => {
    const current = pendingPayment;
    if (current) {
      current.onCancel();
    } else {
      setPendingPayment(null);
    }
  }, [pendingPayment]);

  const isStreaming =
    workflowState.phase === 'preparing' || workflowState.phase === 'streaming';

  return {
    messages,
    workflowState,
    pendingPayment,
    dismissPaymentPrompt,
    sendMessage,
    stopStream,
    clearMessages,
    isStreaming,
  };
}
