/**
 * TypeScript type definitions for agent events, session state, and message payloads.
 */

// =============================================================================
// Session State
// =============================================================================

/**
 * Agent session state machine states.
 */
export type AgentSessionState =
  | 'idle'
  | 'connecting'
  | 'running'
  | 'awaiting_input'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'error';

// =============================================================================
// Agent Events (discriminated union)
// =============================================================================

export interface ThinkingEvent {
  type: 'agent.thinking';
  payload: {
    content: string;
    is_streaming: boolean;
  };
}

export interface ToolCallEvent {
  type: 'agent.tool_call';
  payload: {
    tool_call_id: string;
    tool_name: string;
    arguments: Record<string, unknown>;
    requires_confirmation: boolean;
    description?: string;
  };
}

export interface ToolResultEvent {
  type: 'agent.tool_result';
  payload: {
    tool_call_id: string;
    status: 'success' | 'error';
    result?: unknown;
    error?: string;
    duration_ms?: number;
  };
}

export interface AgentMessageEvent {
  type: 'agent.message';
  payload: {
    content: string;
    is_complete: boolean;
  };
}

export interface TokenEvent {
  type: 'agent.token';
  payload: {
    token: string;
  };
}

export interface StatusEvent {
  type: 'agent.status';
  payload: {
    status: string;
    detail: string;
    progress?: number;
  };
}

export interface RequestInputEvent {
  type: 'agent.request_input';
  payload: {
    prompt: string;
  };
}

export interface SessionCreatedEvent {
  type: 'session.created';
  payload: {
    session_id: string;
  };
}

export interface SessionCompletedEvent {
  type: 'session.completed';
  payload: {
    session_id: string;
  };
}

export interface SessionFailedEvent {
  type: 'session.failed';
  payload: {
    error: string;
    reason: string;
  };
}

export interface AgentErrorEvent {
  type: 'agent.error';
  payload: {
    code: string;
    message: string;
    recoverable: boolean;
  };
}

/**
 * Union type of all possible agent events.
 */
export type AgentEvent =
  | ThinkingEvent
  | ToolCallEvent
  | ToolResultEvent
  | AgentMessageEvent
  | TokenEvent
  | StatusEvent
  | RequestInputEvent
  | SessionCreatedEvent
  | SessionCompletedEvent
  | SessionFailedEvent
  | AgentErrorEvent;

// =============================================================================
// Session Options
// =============================================================================

/**
 * Configuration for agent sessions.
 */
export interface AgentConfig {
  maxTokens?: number;
  temperature?: number;
  systemPrompt?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Message in conversation history.
 */
export interface AgentHistoryMessage {
  role: string;
  content: string;
}

/**
 * Options for starting an agent session.
 */
export interface AgentSessionOptions {
  /** The initial prompt */
  prompt: string;

  /** Endpoint in "owner/slug" format or { owner, slug } object */
  endpoint: string | { owner: string; slug: string };

  /** Optional agent configuration */
  config?: AgentConfig;

  /** Optional conversation history */
  messages?: AgentHistoryMessage[];

  /** Optional AbortSignal for cancellation */
  signal?: AbortSignal;
}
