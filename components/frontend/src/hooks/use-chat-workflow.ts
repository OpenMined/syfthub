/**
 * useChatWorkflow Hook
 *
 * Main workflow state machine for the query execution flow:
 * User Query → Request Preparation → Aggregator Request → Streaming Response
 *
 * The workflow uses pre-selected data sources from the ContextSelectionStore
 * (via the "+" button / AddSourcesModal). If no sources are selected, the query
 * executes with the model only (no data sources).
 */
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import type { ChatStreamEvent as SDKChatStreamEvent } from '@/lib/sdk-client';
import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { triggerBalanceRefresh } from '@/hooks/use-wallet-api';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError,
  syftClient
} from '@/lib/sdk-client';
import { useUserAggregatorsStore } from '@/stores/user-aggregators-store';

// =============================================================================
// Local stream-event extension: payment_required
//
// The aggregator emits `payment_required` SSE events when an endpoint has a
// transaction policy attached. The official SDK union (`SDKChatStreamEvent`)
// does not yet model this event — that addition lives in another batch unit.
// We type it locally and union it in so this hook can dispatch on it.
// =============================================================================

/**
 * Fired by the aggregator when an endpoint requires an on-chain payment to
 * proceed. K events with the same `chatSessionId` may be emitted in parallel
 * for multi-endpoint chats and should be batched into a single approval UI.
 */
export interface PaymentRequiredEvent {
  type: 'payment_required';
  chatSessionId: string;
  endpointSlug: string;
  /** Raw `WWW-Authenticate: Payment ...` header value (parseable via parseChallenge). */
  challenge: string;
  /** Decimal-string amount (e.g. "0.10"). */
  amount: string;
  /** ERC-20 token contract address. */
  currency: `0x${string}`;
  /** Recipient address for the on-chain transfer. */
  recipient: `0x${string}`;
  challengeId: string;
  /** "charge" | "session" | future variants. */
  intent: string;
}

export type ChatStreamEvent = SDKChatStreamEvent | PaymentRequiredEvent;

// =============================================================================
// Types
// =============================================================================

/**
 * Workflow phases representing the state machine states.
 */
export type WorkflowPhase =
  | 'idle' // Ready for user input
  | 'preparing' // Building request (satellite, tokens)
  | 'streaming' // Receiving response from aggregator
  | 'complete' // Workflow completed successfully
  | 'error'; // Workflow failed

/**
 * Status of an individual source during retrieval.
 */
export interface SourceProgressInfo {
  path: string;
  displayName: string;
  status: 'pending' | 'success' | 'error' | 'timeout';
  documents: number;
}

/**
 * Progress tracking for retrieval phase.
 */
export interface RetrievalProgress {
  completed: number;
  total: number;
  documentsFound: number;
}

/**
 * A single step in the chain-of-thought pipeline display.
 */
export interface PipelineStep {
  id: string;
  label: string;
  description?: string;
  status: 'pending' | 'active' | 'complete';
}

/**
 * Processing status during streaming phase.
 */
export interface ProcessingStatus {
  phase: 'retrieving' | 'reranking' | 'generating' | 'streaming' | 'error';
  message: string;
  retrieval?: RetrievalProgress;
  completedSources: SourceProgressInfo[];
  steps: PipelineStep[];
  generationElapsedMs?: number;
  timing?: {
    retrievalMs?: number;
    rerankMs?: number;
  };
}

/**
 * Document source from aggregator response.
 */
export interface DocumentSource {
  slug: string;
  content: string;
}

/**
 * Aggregator sources data (document title → source info).
 */
export type SourcesData = Record<string, DocumentSource>;

/**
 * Complete workflow result after successful completion.
 */
export interface WorkflowResult {
  query: string;
  content: string;
  sources: SourcesData;
  modelPath: string;
  dataSourcePaths: string[];
  /**
   * Position-annotated response from the done event ([cite:N-start:end] format).
   * Present when the aggregator ran reranking + attribution over data sources.
   * Use this to render citation highlights; falls back to content if absent.
   */
  annotatedResponse?: string;
  /** Fractional contribution per source owner/slug (0–1). */
  profitShare?: Record<string, number>;
}

/**
 * A pending on-chain payment challenge surfaced by a `payment_required`
 * stream event. Modal consumers batch these and present a single approval.
 *
 * Derived from `PaymentRequiredEvent` minus the discriminator + with an
 * optional resolved owner name for display.
 */
export type PaymentChallenge = Omit<PaymentRequiredEvent, 'type'> & {
  /** Optional owner name for `<owner>/<slug>` display. Resolved separately if available. */
  ownerName?: string;
};

/**
 * Internal workflow state managed by the reducer.
 *
 * Note: the `payment_required` debounce buffer lives in a hook-local `useRef`
 * (not in this state) so accumulating in-flight challenges doesn't trigger a
 * consumer re-render — only the flushed `paymentChallenges` array does.
 */
export interface WorkflowState {
  phase: WorkflowPhase;
  query: string | null;
  selectedSources: Set<string>;
  processingStatus: ProcessingStatus | null;
  streamedContent: string;
  aggregatorSources: SourcesData;
  error: string | null;
  /**
   * Challenges currently presented to the user via the modal.
   * Cleared by the consumer (after approval or cancel) via `clearPaymentChallenges`.
   */
  paymentChallenges: PaymentChallenge[];
}

/**
 * Options for the useChatWorkflow hook.
 */
export interface UseChatWorkflowOptions {
  /** Currently selected model */
  model: ChatSource | null;
  /** Available data sources for path lookups */
  dataSources: ChatSource[];
  /** Map of data sources by ID for O(1) lookups */
  dataSourcesById?: Map<string, ChatSource>;
  /** Pre-selected context sources from browse page "Add to context" flow */
  contextSources?: ChatSource[];
  /** Callback when workflow completes successfully */
  onComplete?: (result: WorkflowResult) => void;
  /** Callback when workflow encounters an error */
  onError?: (error: string) => void;
  /** Callback for each streamed token (for real-time UI updates) */
  onStreamToken?: (content: string) => void;
}

/**
 * Return type of useChatWorkflow hook.
 */
/**
 * A prior conversation turn for multi-turn context.
 */
export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface UseChatWorkflowReturn extends WorkflowState {
  /** Submit a query to start the workflow. If preSelectedSourceIds is provided, uses those sources; otherwise executes with model only. */
  submitQuery: (
    query: string,
    preSelectedSourceIds?: Set<string>,
    messages?: ChatHistoryMessage[]
  ) => Promise<void>;
  /** Abort any in-flight request */
  abort: () => void;
  /** Reset the workflow to initial state */
  reset: () => void;
  /** Resolved aggregator URL the active stream is talking to (for follow-up payment POSTs). */
  aggregatorUrl: string | undefined;
  /** Clear the active set of payment challenges (call after approval/cancel). */
  clearPaymentChallenges: () => void;
}

// =============================================================================
// Reducer Actions
// =============================================================================

export type WorkflowAction =
  | { type: 'START_EXECUTING'; query: string; sourceIds: Set<string> }
  | { type: 'START_STREAMING'; status: ProcessingStatus }
  | { type: 'STREAM_EVENT'; event: ChatStreamEvent }
  | { type: 'UPDATE_CONTENT'; content: string }
  | { type: 'COMPLETE'; sources: SourcesData }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET' }
  | { type: 'FLUSH_PAYMENT_CHALLENGES'; challenges: PaymentChallenge[] }
  | { type: 'CLEAR_PAYMENT_CHALLENGES' };

// =============================================================================
// Initial State
// =============================================================================

export const initialState: WorkflowState = {
  phase: 'idle',
  query: null,
  selectedSources: new Set(),
  processingStatus: null,
  streamedContent: '',
  aggregatorSources: {},
  error: null,
  paymentChallenges: []
};

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Extract a display name from an endpoint path.
 */
export function extractSourceDisplayName(path: string): string {
  const parts = path.split('/');
  const name = parts.at(-1) ?? path;
  return name
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Process a stream event to update the processing status.
 */
export function processStreamEventForStatus(
  status: ProcessingStatus | null,
  event: ChatStreamEvent
): ProcessingStatus | null {
  switch (event.type) {
    case 'retrieval_start': {
      if (event.sourceCount === 0) {
        return {
          phase: 'retrieving',
          message: 'Preparing request…',
          completedSources: [],
          steps: [{ id: 'generation', label: 'Generating response', status: 'pending' }]
        };
      }
      return {
        phase: 'retrieving',
        message: `Searching ${String(event.sourceCount)} data ${event.sourceCount === 1 ? 'source' : 'sources'}…`,
        retrieval: {
          completed: 0,
          total: event.sourceCount,
          documentsFound: 0
        },
        completedSources: [],
        steps: [
          { id: 'retrieval', label: 'Searching sources', status: 'active' },
          { id: 'generation', label: 'Generating response', status: 'pending' }
        ]
      };
    }

    case 'source_complete': {
      if (!status) return null;
      const newCompleted = (status.retrieval?.completed ?? 0) + 1;
      const newDocumentsFound = (status.retrieval?.documentsFound ?? 0) + event.documentsRetrieved;
      const total = status.retrieval?.total ?? 1;

      return {
        ...status,
        message: `Retrieved from ${String(newCompleted)}/${String(total)} ${total === 1 ? 'source' : 'sources'}…`,
        retrieval: {
          completed: newCompleted,
          total,
          documentsFound: newDocumentsFound
        },
        completedSources: [
          ...status.completedSources,
          {
            path: event.path,
            displayName: extractSourceDisplayName(event.path),
            status: event.status as 'success' | 'error' | 'timeout',
            documents: event.documentsRetrieved
          }
        ]
      };
    }

    case 'retrieval_complete': {
      if (!status) return null;
      const documentCount = event.totalDocuments;
      const documentLabel = documentCount === 1 ? 'document' : 'documents';
      const message =
        documentCount > 0
          ? `Found ${String(documentCount)} relevant ${documentLabel}`
          : 'No relevant documents found';
      return {
        ...status,
        message,
        timing: {
          ...status.timing,
          retrievalMs: event.timeMs
        }
      };
    }

    case 'reranking_start': {
      if (!status) return null;
      const documentLabel = event.documents === 1 ? 'document' : 'documents';
      return {
        ...status,
        phase: 'reranking',
        message: `Re-ranking ${String(event.documents)} ${documentLabel}…`,
        steps: [
          ...status.steps.map((step) =>
            step.id === 'retrieval'
              ? { ...step, status: 'complete' as const }
              : step.id === 'reranking'
                ? { ...step, status: 'active' as const }
                : step
          ),
          ...(status.steps.some((s) => s.id === 'reranking')
            ? []
            : [{ id: 'reranking', label: 'Re-ranking documents', status: 'active' as const }])
        ].toSorted((a, b) => {
          const order = ['retrieval', 'reranking', 'generation'];
          return order.indexOf(a.id) - order.indexOf(b.id);
        })
      };
    }

    case 'reranking_complete': {
      if (!status) return null;
      return {
        ...status,
        steps: status.steps.map((step) =>
          step.id === 'reranking'
            ? {
                ...step,
                status: 'complete' as const,
                description: `${String(event.documents)} docs · ${(event.timeMs / 1000).toFixed(1)}s`
              }
            : step
        ),
        timing: {
          ...status.timing,
          rerankMs: event.timeMs
        }
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
            ? { ...step, status: 'active' as const, description: undefined }
            : step.status === 'complete'
              ? step
              : { ...step, status: 'complete' as const }
        )
      };
    }

    case 'generation_heartbeat': {
      if (status?.phase !== 'generating') return status;
      const elapsedSec = Math.floor(event.elapsedMs / 1000);
      return {
        ...status,
        generationElapsedMs: event.elapsedMs,
        message: `Generating response… ${String(elapsedSec)}s`,
        steps: status.steps.map((step) =>
          step.id === 'generation'
            ? { ...step, description: `${String(elapsedSec)}s elapsed` }
            : step
        )
      };
    }

    case 'token': {
      if (!status || status.phase === 'streaming') return status;
      return {
        ...status,
        phase: 'streaming',
        message: 'Writing response…',
        steps: status.steps.map((step) =>
          step.id === 'generation' ? { ...step, status: 'complete' as const } : step
        )
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
        steps: status?.steps ?? []
      };
    }

    default: {
      return status;
    }
  }
}

/**
 * Convert errors to user-friendly messages.
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof AuthenticationError) {
    return 'Authentication required. Please log in again.';
  }
  if (error instanceof AggregatorError) {
    return `Chat service error: ${error.message}`;
  }
  if (error instanceof EndpointResolutionError) {
    return `Could not resolve endpoint: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

// =============================================================================
// Reducer
// =============================================================================

export function workflowReducer(state: WorkflowState, action: WorkflowAction): WorkflowState {
  switch (action.type) {
    case 'START_EXECUTING': {
      return {
        ...initialState,
        phase: 'preparing',
        query: action.query,
        selectedSources: action.sourceIds
      };
    }

    case 'START_STREAMING': {
      return {
        ...state,
        phase: 'streaming',
        processingStatus: action.status
      };
    }

    case 'STREAM_EVENT': {
      const newStatus = processStreamEventForStatus(state.processingStatus, action.event);
      return {
        ...state,
        processingStatus: newStatus
      };
    }

    case 'UPDATE_CONTENT': {
      return {
        ...state,
        streamedContent: action.content
      };
    }

    case 'COMPLETE': {
      return {
        ...state,
        phase: 'complete',
        aggregatorSources: action.sources,
        processingStatus: null
      };
    }

    case 'ERROR': {
      return {
        ...state,
        phase: 'error',
        error: action.error,
        processingStatus: null
      };
    }

    case 'RESET': {
      return initialState;
    }

    case 'FLUSH_PAYMENT_CHALLENGES': {
      if (action.challenges.length === 0) return state;
      // Merge with any already-presented challenges (in case a second batch
      // arrives while the modal is open from a prior batch). Dedupe by id so
      // re-emitted challenges don't double up.
      const seen = new Set(state.paymentChallenges.map((c) => c.challengeId));
      const merged = [...state.paymentChallenges];
      for (const c of action.challenges) {
        if (!seen.has(c.challengeId)) {
          merged.push(c);
          seen.add(c.challengeId);
        }
      }
      if (merged.length === state.paymentChallenges.length) return state;
      return { ...state, paymentChallenges: merged };
    }

    case 'CLEAR_PAYMENT_CHALLENGES': {
      if (state.paymentChallenges.length === 0) return state;
      return { ...state, paymentChallenges: [] };
    }

    default: {
      return state;
    }
  }
}

// =============================================================================
// Hook Implementation
// =============================================================================

/**
 * Main workflow hook for the query execution flow.
 *
 * @example
 * ```tsx
 * const workflow = useChatWorkflow({
 *   model: selectedModel,
 *   dataSources: availableSources,
 *   onComplete: (result) => {
 *     addMessage({ role: 'assistant', content: result.content });
 *   }
 * });
 *
 * // In JSX
 * <QueryInput onSubmit={workflow.submitQuery} disabled={workflow.phase !== 'idle'} />
 * ```
 */
export function useChatWorkflow(options: UseChatWorkflowOptions): UseChatWorkflowReturn {
  const {
    model,
    dataSources,
    dataSourcesById,
    contextSources,
    onComplete,
    onError,
    onStreamToken
  } = options;

  const { user } = useAuth();

  // Read default aggregator from the Zustand store (source of truth for aggregator selection).
  // Falls back to user.aggregator_url from auth context for backward compatibility.
  const { aggregators, defaultAggregatorId, hasFetched, fetchAggregators } =
    useUserAggregatorsStore();

  // Auto-hydrate the aggregators store when an authenticated user is present.
  // Without this, the store is only populated when the user visits the settings tab,
  // causing custom aggregator URLs to be lost after page refresh.
  useEffect(() => {
    if (user && !hasFetched) {
      void fetchAggregators();
    }
  }, [user, hasFetched, fetchAggregators]);

  const aggregatorUrl = useMemo(() => {
    if (defaultAggregatorId) {
      const defaultAgg = aggregators.find((a) => a.id === defaultAggregatorId);
      if (defaultAgg?.url) return defaultAgg.url;
    }
    return user?.aggregator_url;
  }, [aggregators, defaultAggregatorId, user?.aggregator_url]);

  const [state, dispatch] = useReducer(workflowReducer, initialState);
  const abortControllerReference = useRef<AbortController | null>(null);

  // Debounce buffer for `payment_required` events that arrive in close
  // succession (multi-endpoint chats). Held in refs because in-flight
  // accumulation must not trigger consumer re-renders — only the flushed
  // batch (via dispatch) does. 200ms window per the spec.
  const paymentBufferReference = useRef<PaymentChallenge[]>([]);
  const paymentFlushTimerReference = useRef<ReturnType<typeof setTimeout> | null>(null);
  const PAYMENT_FLUSH_DEBOUNCE_MS = 200;

  const bufferPaymentChallenge = useCallback((challenge: PaymentChallenge) => {
    // Dedupe by id so the aggregator re-emitting the same challenge doesn't
    // produce two cards in the modal.
    if (paymentBufferReference.current.some((c) => c.challengeId === challenge.challengeId)) {
      return;
    }
    paymentBufferReference.current.push(challenge);
    if (paymentFlushTimerReference.current) {
      clearTimeout(paymentFlushTimerReference.current);
    }
    paymentFlushTimerReference.current = setTimeout(() => {
      paymentFlushTimerReference.current = null;
      const flushed = paymentBufferReference.current;
      paymentBufferReference.current = [];
      dispatch({ type: 'FLUSH_PAYMENT_CHALLENGES', challenges: flushed });
    }, PAYMENT_FLUSH_DEBOUNCE_MS);
  }, []);

  // Cancel pending flush timer on unmount.
  useEffect(() => {
    return () => {
      if (paymentFlushTimerReference.current) {
        clearTimeout(paymentFlushTimerReference.current);
        paymentFlushTimerReference.current = null;
      }
    };
  }, []);

  const clearPaymentChallenges = useCallback(() => {
    if (paymentFlushTimerReference.current) {
      clearTimeout(paymentFlushTimerReference.current);
      paymentFlushTimerReference.current = null;
    }
    paymentBufferReference.current = [];
    dispatch({ type: 'CLEAR_PAYMENT_CHALLENGES' });
  }, []);

  // Build a sources map for O(1) lookups, including context sources if provided
  const sourcesMap = useMemo(() => {
    const base = dataSourcesById ?? new Map(dataSources.map((source) => [source.id, source]));
    if (!contextSources || contextSources.length === 0) return base;
    // Merge context sources into the map (they may not be in dataSources)
    const merged = new Map(base);
    for (const source of contextSources) {
      if (!merged.has(source.id)) {
        merged.set(source.id, source);
      }
    }
    return merged;
  }, [dataSourcesById, dataSources, contextSources]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  /**
   * Execute the streaming request with the given query and source IDs.
   */
  const executeWithSources = useCallback(
    async (query: string, sourceIds: Set<string>, history?: ChatHistoryMessage[]) => {
      // Build endpoint paths
      const modelPath = model?.full_path;
      if (!modelPath) {
        dispatch({
          type: 'ERROR',
          error: 'Error: Selected model does not have a valid path configured.'
        });
        onError?.('Error: Selected model does not have a valid path configured.');
        return;
      }

      // Build data source paths from selected sources
      const selectedSourcePaths = [...sourceIds]
        .map((id) => sourcesMap.get(id)?.full_path)
        .filter((path): path is string => path !== undefined);

      // Deduplicate paths
      const allDataSourcePaths = [...new Set(selectedSourcePaths)];

      // Create abort controller for cancellation
      abortControllerReference.current = new AbortController();

      // Calculate total source count for status
      const totalSourceCount = allDataSourcePaths.length;

      // Initialize processing status
      const initialProcessingStatus: ProcessingStatus = {
        phase: 'retrieving',
        message: totalSourceCount > 0 ? 'Starting...' : 'Preparing request...',
        completedSources: [],
        steps: []
      };

      dispatch({ type: 'START_STREAMING', status: initialProcessingStatus });

      let accumulatedContent = '';

      try {
        // Execute the stream
        for await (const sdkEvent of syftClient.chat.stream({
          prompt: query,
          model: modelPath,
          dataSources: allDataSourcePaths.length > 0 ? allDataSourcePaths : undefined,
          aggregatorUrl: aggregatorUrl ?? undefined,
          guestMode: !user,
          signal: abortControllerReference.current.signal,
          messages: history && history.length > 0 ? history : undefined
        })) {
          // The SDK union does not yet include `payment_required` (added by a
          // separate unit). Until then, the SDK may surface it via its own
          // forward-compat path. We treat the value as the extended union so
          // downstream branches can match on it.
          const event = sdkEvent as ChatStreamEvent;

          // Buffer payment_required events for batched approval. Multiple
          // endpoints in a single chat can each emit one within ~ms of each
          // other; the debounce window ensures the modal sees them as one.
          if (event.type === 'payment_required') {
            bufferPaymentChallenge({
              chatSessionId: event.chatSessionId,
              endpointSlug: event.endpointSlug,
              challenge: event.challenge,
              amount: event.amount,
              currency: event.currency,
              recipient: event.recipient,
              challengeId: event.challengeId,
              intent: event.intent
            });
            continue;
          }

          // Update processing status
          dispatch({ type: 'STREAM_EVENT', event });

          // Handle token content
          if (event.type === 'token') {
            accumulatedContent += event.content;
            dispatch({ type: 'UPDATE_CONTENT', content: accumulatedContent });
            onStreamToken?.(accumulatedContent);
          }

          // Handle completion
          if (event.type === 'done') {
            const result: WorkflowResult = {
              query,
              content: accumulatedContent,
              sources: event.sources,
              modelPath,
              dataSourcePaths: allDataSourcePaths,
              annotatedResponse: event.response,
              profitShare: event.profitShare
            };

            dispatch({ type: 'COMPLETE', sources: event.sources });
            onComplete?.(result);

            // Refresh balance after successful completion (only for authenticated users)
            if (user) {
              triggerBalanceRefresh();
            }
          }

          // Handle errors
          if (event.type === 'error') {
            throw new Error(event.message);
          }
        }
      } catch (error) {
        // Don't show error if aborted
        if (error instanceof Error && error.name === 'AbortError') {
          dispatch({ type: 'RESET' });
          return;
        }

        const errorMessage = getErrorMessage(error);
        dispatch({ type: 'ERROR', error: errorMessage });
        onError?.(errorMessage);
      } finally {
        abortControllerReference.current = null;
      }
    },
    [
      model,
      user,
      aggregatorUrl,
      sourcesMap,
      onComplete,
      onError,
      onStreamToken,
      bufferPaymentChallenge
    ]
  );

  /**
   * Submit a query to start the workflow.
   *
   * Uses the provided preSelectedSourceIds if available, falls back to
   * contextSources from the browse page, or executes with model only.
   */
  const submitQuery = useCallback(
    async (query: string, preSelectedSourceIds?: Set<string>, history?: ChatHistoryMessage[]) => {
      // Validation
      if (!query.trim()) {
        return;
      }

      if (!model) {
        dispatch({ type: 'ERROR', error: 'Please select a model before sending a message.' });
        onError?.('Please select a model before sending a message.');
        return;
      }

      // Determine source IDs to use
      let sourceIds: Set<string>;

      if (preSelectedSourceIds && preSelectedSourceIds.size > 0) {
        // Sources from the chat input "+" button
        sourceIds = preSelectedSourceIds;
      } else if (contextSources && contextSources.length > 0) {
        // Sources from browse page "Add to context" flow
        sourceIds = new Set(contextSources.map((s) => s.id));
      } else {
        // No sources selected — model-only execution
        sourceIds = new Set();
      }

      // Execute directly
      dispatch({
        type: 'START_EXECUTING',
        query: query.trim(),
        sourceIds
      });
      await executeWithSources(query.trim(), sourceIds, history);
    },
    [model, contextSources, onError, executeWithSources]
  );

  /**
   * Abort any in-flight request.
   */
  const abort = useCallback(() => {
    abortControllerReference.current?.abort();
  }, []);

  /**
   * Reset the workflow to initial state.
   */
  const reset = useCallback(() => {
    abortControllerReference.current?.abort();
    dispatch({ type: 'RESET' });
  }, []);

  return {
    ...state,
    submitQuery,
    abort,
    reset,
    aggregatorUrl,
    clearPaymentChallenges
  };
}
