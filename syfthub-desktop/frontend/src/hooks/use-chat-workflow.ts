import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import { main } from '../../wailsjs/go/models';
import { StopChat, StreamChat } from '../../wailsjs/go/main/App';
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

export interface UseChatWorkflowReturn {
  messages: ChatMessage[];
  workflowState: WorkflowState;
  sendMessage: (prompt: string) => Promise<void>;
  stopStream: () => Promise<void>;
  clearMessages: () => void;
  isStreaming: boolean;
}

export function useChatWorkflow({
  selectedModel,
  selectedSources,
}: UseChatWorkflowOptions): UseChatWorkflowReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [workflowState, dispatch] = useReducer(workflowReducer, initialWorkflowState);

  // Track id of the message being streamed into so token updates hit the right msg
  const streamingIdRef = useRef<string | null>(null);

  // Register Wails event listener once
  useEffect(() => {
    const unsubscribe = EventsOn('chat:stream-event', (event: ChatStreamEvent) => {
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
        }
      } else if (event.type === 'error') {
        const id = streamingIdRef.current;
        if (id) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === id && msg.role === 'assistant'
                ? { ...msg, isStreaming: false }
                : msg
            )
          );
          streamingIdRef.current = null;
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!selectedModel) return;
      if (workflowState.phase === 'preparing' || workflowState.phase === 'streaming') return;

      const userMsgId = `user-${Date.now()}`;
      const assistantMsgId = `asst-${Date.now()}-${Math.random().toString(36).slice(2)}`;

      // Snapshot history before adding new messages
      const historySnapshot: { role: string; content: string }[] = messages.map((m) => ({
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
    [selectedModel, selectedSources, workflowState.phase, messages]
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
    dispatch({ type: 'RESET' });
  }, []);

  const clearMessages = useCallback(() => {
    if (streamingIdRef.current) {
      void StopChat().catch(() => {});
      streamingIdRef.current = null;
    }
    setMessages([]);
    dispatch({ type: 'RESET' });
  }, []);

  const isStreaming =
    workflowState.phase === 'preparing' || workflowState.phase === 'streaming';

  return {
    messages,
    workflowState,
    sendMessage,
    stopStream,
    clearMessages,
    isStreaming,
  };
}
