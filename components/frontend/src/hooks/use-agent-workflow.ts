/**
 * useAgentWorkflow Hook
 *
 * React hook implementing the agent session state machine.
 * Manages WebSocket-based bidirectional communication with agent endpoints.
 */
import { useCallback, useEffect, useReducer, useRef } from 'react';

import type { AgentEvent, AgentSessionClient, AgentSessionState } from '@syfthub/sdk';

import { syftClient } from '@/lib/sdk-client';

// =============================================================================
// Types
// =============================================================================

export interface AgentWorkflowState {
  phase: AgentSessionState;
  events: AgentEvent[];
  streamingContent: string;
  sessionId: string | null;
  error: string | null;
}

type AgentAction =
  | { type: 'SESSION_STARTED' }
  | { type: 'SESSION_CREATED'; sessionId: string }
  | { type: 'AGENT_EVENT'; event: AgentEvent }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET' }
  | { type: 'CANCELLED' };

// =============================================================================
// Reducer
// =============================================================================

const initialState: AgentWorkflowState = {
  phase: 'idle',
  events: [],
  streamingContent: '',
  sessionId: null,
  error: null
};

function agentReducer(state: AgentWorkflowState, action: AgentAction): AgentWorkflowState {
  switch (action.type) {
    case 'SESSION_STARTED': {
      return {
        ...initialState,
        phase: 'connecting'
      };
    }

    case 'SESSION_CREATED': {
      return {
        ...state,
        phase: 'running',
        sessionId: action.sessionId
      };
    }

    case 'AGENT_EVENT': {
      const event = action.event;
      const newEvents = [...state.events, event];

      // Accumulate streaming content from token events
      let streamingContent = state.streamingContent;
      if (event.type === 'agent.token') {
        streamingContent += event.payload.token;
      } else if (event.type === 'agent.message') {
        // Reset streaming content when a complete message arrives
        streamingContent = '';
      }

      // Determine new phase
      let phase: AgentSessionState = state.phase;
      switch (event.type) {
        case 'agent.request_input': {
          phase = 'awaiting_input';
          break;
        }
        case 'session.completed': {
          phase = 'completed';
          break;
        }
        case 'session.failed': {
          phase = 'failed';
          break;
        }
        case 'agent.error': {
          if (!event.payload.recoverable) {
            phase = 'error';
          }
          break;
        }
        default: {
          if (phase === 'awaiting_input') {
            phase = 'running';
          }
        }
      }

      return {
        ...state,
        phase,
        events: newEvents,
        streamingContent
      };
    }

    case 'ERROR': {
      return {
        ...state,
        phase: 'error',
        error: action.error
      };
    }

    case 'CANCELLED': {
      return {
        ...state,
        phase: 'cancelled'
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
// Hook
// =============================================================================

export function useAgentWorkflow() {
  const [state, dispatch] = useReducer(agentReducer, initialState);
  const sessionReference = useRef<AgentSessionClient | null>(null);

  // Clean up session on unmount
  useEffect(() => {
    return () => {
      if (sessionReference.current) {
        sessionReference.current.close();
        sessionReference.current = null;
      }
    };
  }, []);

  const startSession = useCallback(async (prompt: string, endpoint: string) => {
    // Close existing session if any
    if (sessionReference.current) {
      sessionReference.current.close();
      sessionReference.current = null;
    }

    dispatch({ type: 'SESSION_STARTED' });

    try {
      const session = await syftClient.agent.startSession({
        prompt,
        endpoint
      });

      sessionReference.current = session;
      dispatch({ type: 'SESSION_CREATED', sessionId: session.sessionId });

      // Iterate events in background
      void (async () => {
        try {
          for await (const event of session.events()) {
            dispatch({ type: 'AGENT_EVENT', event });
          }
        } catch (error) {
          dispatch({
            type: 'ERROR',
            error: error instanceof Error ? error.message : 'Unknown error'
          });
        }
      })();
    } catch (error) {
      dispatch({
        type: 'ERROR',
        error: error instanceof Error ? error.message : 'Failed to start agent session'
      });
    }
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (sessionReference.current) {
      sessionReference.current.sendMessage(content);
    }
  }, []);

  const confirm = useCallback((toolCallId: string) => {
    if (sessionReference.current) {
      sessionReference.current.confirm(toolCallId);
    }
  }, []);

  const deny = useCallback((toolCallId: string, reason?: string) => {
    if (sessionReference.current) {
      sessionReference.current.deny(toolCallId, reason);
    }
  }, []);

  const cancel = useCallback(() => {
    if (sessionReference.current) {
      sessionReference.current.cancel();
      dispatch({ type: 'CANCELLED' });
    }
  }, []);

  const reset = useCallback(() => {
    if (sessionReference.current) {
      sessionReference.current.close();
      sessionReference.current = null;
    }
    dispatch({ type: 'RESET' });
  }, []);

  return {
    state,
    startSession,
    sendMessage,
    confirm,
    deny,
    cancel,
    reset
  };
}
