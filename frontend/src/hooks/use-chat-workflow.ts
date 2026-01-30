/**
 * useChatWorkflow Hook
 *
 * Main workflow state machine for the query execution flow:
 * User Query → Semantic Search → Endpoints Selection → Request Preparation → Aggregator Request
 *
 * This hook centralizes all workflow logic that was previously scattered across
 * Hero and ChatView components.
 */
import { useCallback, useReducer, useRef } from 'react';

import type { ChatStreamEvent } from '@/lib/sdk-client';
import type { SearchableChatSource } from '@/lib/search-service';
import type { ChatSource } from '@/lib/types';

import { useAuth } from '@/context/auth-context';
import { triggerBalanceRefresh } from '@/hooks/use-accounting-api';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError,
  syftClient
} from '@/lib/sdk-client';
import { categorizeResults, MIN_QUERY_LENGTH, searchDataSources } from '@/lib/search-service';

// =============================================================================
// Types
// =============================================================================

/**
 * Workflow phases representing the state machine states.
 */
export type WorkflowPhase =
  | 'idle' // Ready for user input
  | 'searching' // Running semantic search for endpoints
  | 'selecting' // User selecting/confirming endpoints
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
}

/**
 * Internal workflow state managed by the reducer.
 */
export interface WorkflowState {
  phase: WorkflowPhase;
  query: string | null;
  suggestedEndpoints: SearchableChatSource[];
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
  /** Available data sources for selection and path lookups */
  dataSources: ChatSource[];
  /** Map of data sources by ID for O(1) lookups */
  dataSourcesById?: Map<string, ChatSource>;
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
export interface UseChatWorkflowReturn extends WorkflowState {
  /** Submit a query to start the workflow */
  submitQuery: (query: string) => Promise<void>;
  /** Toggle a source selection */
  toggleSource: (id: string) => void;
  /** Confirm endpoint selection and proceed to execution */
  confirmSelection: () => Promise<void>;
  /** Cancel the current workflow and reset to idle */
  cancelSelection: () => void;
  /** Abort any in-flight request */
  abort: () => void;
  /** Reset the workflow to initial state */
  reset: () => void;
}

// =============================================================================
// Reducer Actions
// =============================================================================

type WorkflowAction =
  | { type: 'START_SEARCH'; query: string }
  | { type: 'SEARCH_COMPLETE'; endpoints: SearchableChatSource[] }
  | { type: 'TOGGLE_SOURCE'; id: string }
  | { type: 'START_PREPARING' }
  | { type: 'START_STREAMING'; status: ProcessingStatus }
  | { type: 'STREAM_EVENT'; event: ChatStreamEvent }
  | { type: 'UPDATE_CONTENT'; content: string }
  | { type: 'COMPLETE'; sources: SourcesData }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET' };

// =============================================================================
// Initial State
// =============================================================================

const initialState: WorkflowState = {
  phase: 'idle',
  query: null,
  suggestedEndpoints: [],
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
function extractSourceDisplayName(path: string): string {
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
function processStreamEventForStatus(
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
function getErrorMessage(error: unknown): string {
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

function workflowReducer(state: WorkflowState, action: WorkflowAction): WorkflowState {
  switch (action.type) {
    case 'START_SEARCH': {
      return {
        ...initialState,
        phase: 'searching',
        query: action.query
      };
    }

    case 'SEARCH_COMPLETE': {
      return {
        ...state,
        phase: 'selecting',
        suggestedEndpoints: action.endpoints
      };
    }

    case 'TOGGLE_SOURCE': {
      const next = new Set(state.selectedSources);
      if (next.has(action.id)) {
        next.delete(action.id);
      } else {
        next.add(action.id);
      }
      return { ...state, selectedSources: next };
    }

    case 'START_PREPARING': {
      return { ...state, phase: 'preparing' };
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
 *     // Handle completed query
 *     addMessage({ role: 'assistant', content: result.content });
 *   }
 * });
 *
 * // In JSX
 * <QueryInput onSubmit={workflow.submitQuery} disabled={workflow.phase !== 'idle'} />
 * {workflow.phase === 'selecting' && (
 *   <EndpointConfirmation
 *     suggestedEndpoints={workflow.suggestedEndpoints}
 *     selectedSources={workflow.selectedSources}
 *     onToggleSource={workflow.toggleSource}
 *     onConfirm={workflow.confirmSelection}
 *     onCancel={workflow.cancelSelection}
 *   />
 * )}
 * ```
 */
export function useChatWorkflow(options: UseChatWorkflowOptions): UseChatWorkflowReturn {
  const { model, dataSources, dataSourcesById, onComplete, onError, onStreamToken } = options;

  const { user } = useAuth();

  const [state, dispatch] = useReducer(workflowReducer, initialState);
  const abortControllerReference = useRef<AbortController | null>(null);

  // Build a sources map for O(1) lookups if not provided
  const sourcesMap = dataSourcesById ?? new Map(dataSources.map((source) => [source.id, source]));

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  /**
   * Submit a query to start the workflow.
   * This triggers semantic search and transitions to the selecting phase.
   */
  const submitQuery = useCallback(
    async (query: string) => {
      // Validation
      if (!query.trim()) {
        return;
      }

      if (!model) {
        dispatch({ type: 'ERROR', error: 'Please select a model before sending a message.' });
        onError?.('Please select a model before sending a message.');
        return;
      }

      // Start the workflow
      dispatch({ type: 'START_SEARCH', query: query.trim() });

      try {
        // Perform semantic search for relevant endpoints
        if (query.length >= MIN_QUERY_LENGTH) {
          const results = await searchDataSources(query, { top_k: 10 });
          const { highRelevance } = categorizeResults(results);
          dispatch({ type: 'SEARCH_COMPLETE', endpoints: highRelevance });
        } else {
          // Query too short for semantic search - proceed with empty suggestions
          dispatch({ type: 'SEARCH_COMPLETE', endpoints: [] });
        }
      } catch (error) {
        console.error('Failed to search endpoints:', error);
        // Still proceed to selection phase even if search fails
        dispatch({ type: 'SEARCH_COMPLETE', endpoints: [] });
      }
    },
    [model, onError]
  );

  /**
   * Toggle a source selection.
   */
  const toggleSource = useCallback((id: string) => {
    dispatch({ type: 'TOGGLE_SOURCE', id });
  }, []);

  /**
   * Confirm endpoint selection and proceed to execution.
   */
  const confirmSelection = useCallback(async () => {
    if (!state.query || !model) {
      return;
    }

    // Transition to preparing phase
    dispatch({ type: 'START_PREPARING' });

    // Build endpoint paths
    const modelPath = model.full_path;
    if (!modelPath) {
      dispatch({
        type: 'ERROR',
        error: 'Error: Selected model does not have a valid path configured.'
      });
      onError?.('Error: Selected model does not have a valid path configured.');
      return;
    }

    // Build data source paths from selected sources
    const selectedSourcePaths = [...state.selectedSources]
      .map((id) => sourcesMap.get(id)?.full_path)
      .filter((path): path is string => path !== undefined);

    // Deduplicate paths
    const allDataSourcePaths = [...new Set(selectedSourcePaths)];

    // TODO: Phase: Request Preparation
    // - Handle satellite connection if required
    // - Handle transaction token if required (accounting flow)

    // Create abort controller for cancellation
    abortControllerReference.current = new AbortController();

    // Calculate total source count for status
    const totalSourceCount = allDataSourcePaths.length;

    // Initialize processing status
    const initialStatus: ProcessingStatus = {
      phase: 'retrieving',
      message: totalSourceCount > 0 ? 'Starting...' : 'Preparing request...',
      completedSources: []
    };

    dispatch({ type: 'START_STREAMING', status: initialStatus });

    let accumulatedContent = '';

    try {
      // Execute the stream
      for await (const event of syftClient.chat.stream({
        prompt: state.query,
        model: modelPath,
        dataSources: allDataSourcePaths.length > 0 ? allDataSourcePaths : undefined,
        aggregatorUrl: user?.aggregator_url ?? undefined,
        guestMode: !user,
        signal: abortControllerReference.current.signal
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
            query: state.query,
            content: accumulatedContent,
            sources: event.sources,
            modelPath,
            dataSourcePaths: allDataSourcePaths
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
  }, [
    state.query,
    state.selectedSources,
    model,
    user,
    sourcesMap,
    onComplete,
    onError,
    onStreamToken
  ]);

  /**
   * Cancel the current workflow and reset to idle.
   */
  const cancelSelection = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

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
    toggleSource,
    confirmSelection,
    cancelSelection,
    abort,
    reset
  };
}
