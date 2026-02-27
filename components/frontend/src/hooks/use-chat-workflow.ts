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

import type { ChatStreamEvent } from '@/lib/sdk-client';
import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { triggerBalanceRefresh } from '@/hooks/use-accounting-api';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError,
  syftClient
} from '@/lib/sdk-client';
import { useUserAggregatorsStore } from '@/stores/user-aggregators-store';

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
 * Processing status during streaming phase.
 */
export interface ProcessingStatus {
  phase: 'retrieving' | 'generating' | 'streaming' | 'error';
  message: string;
  retrieval?: RetrievalProgress;
  completedSources: SourceProgressInfo[];
  timing?: {
    retrievalMs?: number;
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
 * Internal workflow state managed by the reducer.
 */
export interface WorkflowState {
  phase: WorkflowPhase;
  query: string | null;
  selectedSources: Set<string>;
  processingStatus: ProcessingStatus | null;
  streamedContent: string;
  aggregatorSources: SourcesData;
  error: string | null;
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
  | { type: 'RESET' };

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
  error: null
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
          completedSources: []
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
        completedSources: []
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

    case 'generation_start': {
      return {
        phase: 'generating',
        message: 'Generating response…',
        completedSources: status?.completedSources ?? [],
        retrieval: status?.retrieval,
        timing: status?.timing
      };
    }

    case 'token': {
      if (!status || status.phase === 'streaming') return status;
      return {
        ...status,
        phase: 'streaming',
        message: 'Writing response…'
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
        timing: status?.timing
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
        completedSources: []
      };

      dispatch({ type: 'START_STREAMING', status: initialProcessingStatus });

      let accumulatedContent = '';

      try {
        // Execute the stream
        for await (const event of syftClient.chat.stream({
          prompt: query,
          model: modelPath,
          dataSources: allDataSourcePaths.length > 0 ? allDataSourcePaths : undefined,
          aggregatorUrl: aggregatorUrl ?? undefined,
          guestMode: !user,
          signal: abortControllerReference.current.signal,
          messages: history && history.length > 0 ? history : undefined
        })) {
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
    [model, user, aggregatorUrl, sourcesMap, onComplete, onError, onStreamToken]
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
    reset
  };
}
