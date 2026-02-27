import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import { main } from '../../wailsjs/go/models';
import { StopChat, StreamChat } from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';

import type {
  ChatStreamEvent,
  ProcessingStatus,
  SourceProgressInfo,
  SourcesData,
  WorkflowAction,
  WorkflowState,
} from '@/lib/chat-types';
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
      const { event } = action;
      switch (event.type) {
        case 'retrieval_start': {
          return {
            ...state,
            phase: 'streaming',
            processingStatus: {
              phase: 'retrieving',
              message: `Searching ${event.sourceCount} source${event.sourceCount === 1 ? '' : 's'}…`,
              retrieval: { completed: 0, total: event.sourceCount, documentsFound: 0 },
              completedSources: [],
            },
          };
        }

        case 'source_complete': {
          const prev = state.processingStatus;
          const newSource: SourceProgressInfo = {
            path: event.path,
            displayName: event.path.split('/').pop() ?? event.path,
            status: event.status,
            documents: event.documentsRetrieved,
          };
          const completedSources = [...(prev?.completedSources ?? []), newSource];
          const completed = completedSources.length;
          const total = prev?.retrieval?.total ?? completed;
          const documentsFound =
            (prev?.retrieval?.documentsFound ?? 0) +
            (event.status === 'success' ? event.documentsRetrieved : 0);

          return {
            ...state,
            processingStatus: {
              phase: 'retrieving',
              message: `Searching sources… (${completed}/${total})`,
              retrieval: { completed, total, documentsFound },
              completedSources,
              timing: prev?.timing,
            },
          };
        }

        case 'retrieval_complete': {
          const prev = state.processingStatus;
          return {
            ...state,
            processingStatus: {
              ...(prev as ProcessingStatus),
              timing: { retrievalMs: event.timeMs },
            },
          };
        }

        case 'generation_start': {
          const prev = state.processingStatus;
          return {
            ...state,
            processingStatus: {
              phase: 'generating',
              message: 'Generating response…',
              completedSources: prev?.completedSources ?? [],
              retrieval: prev?.retrieval,
              timing: prev?.timing,
            },
          };
        }

        case 'token': {
          const prev = state.processingStatus;
          return {
            ...state,
            streamedContent: state.streamedContent + event.content,
            processingStatus: prev
              ? { ...prev, phase: 'streaming', message: 'Streaming response…' }
              : { phase: 'streaming', message: 'Streaming response…', completedSources: [] },
          };
        }

        case 'done': {
          return {
            ...state,
            phase: 'complete',
            aggregatorSources: event.sources ?? {},
            processingStatus: null,
          };
        }

        case 'error': {
          return {
            ...state,
            phase: 'error',
            error: event.message,
            processingStatus: state.processingStatus
              ? { ...state.processingStatus, phase: 'error', message: event.message }
              : { phase: 'error', message: event.message, completedSources: [] },
          };
        }

        default:
          return state;
      }
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
          history: historySnapshot,
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
