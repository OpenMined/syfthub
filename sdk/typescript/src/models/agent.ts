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
    /** Optional renderer hint — see agenttypes.ToolCall.Display. */
    display?: string;
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
 * Attachment emitted by the agent (host → client). Bytes are either inline
 * (`transport: "inline"`, base64 in `inline_data_b64`) or in JetStream Object
 * Store (`transport: "object_store"`). Object-store payloads carry the
 * `base_nonce`, `wrapped_key`, and `object_bucket`/`object_key` needed to
 * fetch and decrypt the ciphertext.
 */
export interface AgentAttachmentEvent {
  type: 'agent.attachment';
  payload: {
    file_id: string;
    name: string;
    mime: string;
    size_bytes: number;
    plaintext_sha256: string;
    transport: 'inline' | 'object_store';
    // Inline tier:
    inline_data_b64?: string;
    // Object-store tier:
    object_bucket?: string;
    object_key?: string;
    chunk_size?: number;
    /**
     * 8-byte base nonce, base64-encoded. Combined with a 4-byte BE chunk
     * counter to form the 12-byte GCM nonce. Required for object_store.
     */
    base_nonce?: string;
    wrapped_key?: {
      algorithm: string;
      ciphertext: string;
      nonce: string;
      info: string;
    };
  };
}

/**
 * Emitted by the host after it has received and materialized a client-staged
 * attachment. The accept-ack for a prior user attachment — used by the UI to
 * flip the staged chip to ✓ delivered. Only emitted when the runtime actually
 * accepted the file; queue-full drops surface as `agent.error` instead.
 */
export interface UserAttachmentEvent {
  type: 'user.attachment';
  payload: {
    file_id: string;
    size_bytes: number;
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
  | AgentErrorEvent
  | AgentAttachmentEvent
  | UserAttachmentEvent;

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
