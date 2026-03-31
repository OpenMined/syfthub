/**
 * Agent resource for bidirectional agent sessions via WebSocket.
 *
 * @example
 * const session = await client.agent.startSession({
 *   prompt: 'Help me refactor this code',
 *   endpoint: 'alice/code-assistant',
 * });
 *
 * for await (const event of session.events()) {
 *   switch (event.type) {
 *     case 'agent.message':
 *       console.log(event.payload.content);
 *       break;
 *     case 'agent.tool_call':
 *       if (event.payload.requires_confirmation) {
 *         await session.confirm(event.payload.tool_call_id);
 *       }
 *       break;
 *   }
 * }
 */

import { SyftHubError } from '../errors.js';
import type {
  AgentEvent,
  AgentSessionOptions,
  AgentSessionState,
} from '../models/agent.js';
import type { AuthResource } from './auth.js';

/**
 * Error thrown during agent session operations.
 */
export class AgentSessionError extends SyftHubError {
  constructor(
    message: string,
    public readonly code?: string
  ) {
    super(message);
    this.name = 'AgentSessionError';
  }
}

/**
 * AgentResource manages agent session lifecycle.
 */
export class AgentResource {
  constructor(
    private readonly auth: AuthResource,
    private readonly aggregatorUrl: string
  ) {}

  /**
   * Start a new agent session.
   *
   * @param options - Session options including prompt, endpoint, and config
   * @returns An AgentSessionClient for interacting with the session
   */
  async startSession(options: AgentSessionOptions): Promise<AgentSessionClient> {
    // Parse endpoint
    let owner: string;
    let slug: string;
    if (typeof options.endpoint === 'string') {
      const parts = options.endpoint.split('/');
      if (parts.length !== 2) {
        throw new AgentSessionError(
          `Endpoint must be in 'owner/slug' format, got: ${options.endpoint}`
        );
      }
      owner = parts[0]!;
      slug = parts[1]!;
    } else {
      owner = options.endpoint.owner;
      slug = options.endpoint.slug;
    }

    // Fetch satellite token
    const satResponse = await this.auth.getSatelliteToken(owner);

    // Fetch peer token for tunneling
    const peerResponse = await this.auth.getPeerToken([owner]);

    // Build WebSocket URL
    const wsUrl =
      this.aggregatorUrl.replace(/^http/, 'ws') + '/agent/session';

    // Create WebSocket
    const ws = new WebSocket(wsUrl);

    // Wait for connection
    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        ws.removeEventListener('error', onError);
        resolve();
      };
      const onError = (_e: Event) => {
        ws.removeEventListener('open', onOpen);
        reject(new AgentSessionError('Failed to connect to agent WebSocket'));
      };
      ws.addEventListener('open', onOpen, { once: true });
      ws.addEventListener('error', onError, { once: true });

      // Handle abort signal
      if (options.signal) {
        options.signal.addEventListener('abort', () => {
          ws.close();
          reject(new AgentSessionError('Session start aborted'));
        }, { once: true });
      }
    });

    // Send session.start
    const startPayload: Record<string, unknown> = {
      prompt: options.prompt,
      endpoint: { owner, slug },
      satellite_token: satResponse.targetToken,
      peer_token: peerResponse.peerToken,
      peer_channel: peerResponse.peerChannel,
    };
    if (options.config) {
      startPayload.config = options.config;
    }
    if (options.messages) {
      startPayload.messages = options.messages;
    }

    ws.send(JSON.stringify({
      type: 'session.start',
      payload: startPayload,
    }));

    // Wait for session.created response
    const response = await new Promise<{ session_id: string }>((resolve, reject) => {
      const onMessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data.type === 'session.created') {
            ws.removeEventListener('message', onMessage);
            resolve({
              session_id: data.session_id || data.payload?.session_id,
            });
          } else if (data.type === 'agent.error') {
            ws.removeEventListener('message', onMessage);
            reject(new AgentSessionError(
              data.payload?.message || 'Session start failed',
              data.payload?.code
            ));
          }
        } catch {
          reject(new AgentSessionError('Failed to parse session response'));
        }
      };
      ws.addEventListener('message', onMessage);
    });

    return new AgentSessionClient(ws, response.session_id);
  }
}

/**
 * Client for an active agent session.
 * Provides both async iterable and callback-based APIs for receiving events.
 */
export class AgentSessionClient {
  private _state: AgentSessionState = 'running';
  private _sequenceCounter = 0;
  private _messageQueue: AgentEvent[] = [];
  private _messageResolvers: Array<(value: AgentEvent | null) => void> = [];
  private _closed = false;

  constructor(
    private readonly ws: WebSocket,
    public readonly sessionId: string
  ) {
    this.ws.addEventListener('message', (event: MessageEvent) => {
      this._handleMessage(event);
    });
    this.ws.addEventListener('close', () => {
      this._handleClose();
    });
    this.ws.addEventListener('error', () => {
      this._state = 'error';
      this._handleClose();
    });
  }

  /** Current session state */
  get state(): AgentSessionState {
    return this._state;
  }

  /**
   * Async generator yielding agent events.
   *
   * @example
   * for await (const event of session.events()) {
   *   console.log(event.type, event.payload);
   * }
   */
  async *events(): AsyncGenerator<AgentEvent> {
    while (!this._closed) {
      const event = await this._nextEvent();
      if (event === null) break;
      yield event;
    }
  }

  /**
   * Register an event handler.
   *
   * @param eventType - The event type to listen for, or '*' for all events
   * @param handler - Callback function
   */
  on(eventType: string, handler: (event: AgentEvent) => void): void {
    this.ws.addEventListener('message', (msgEvent: MessageEvent) => {
      try {
        const data = JSON.parse(msgEvent.data as string) as AgentEvent;
        if (eventType === '*' || data.type === eventType) {
          handler(data);
        }
      } catch {
        // Ignore parse errors
      }
    });
  }

  /** Send a user message to the agent */
  sendMessage(content: string): void {
    this._send({
      type: 'user.message',
      payload: { content },
    });
  }

  /** Confirm a tool call */
  confirm(toolCallId: string): void {
    this._send({
      type: 'user.confirm',
      payload: { tool_call_id: toolCallId },
    });
  }

  /** Deny a tool call */
  deny(toolCallId: string, reason?: string): void {
    this._send({
      type: 'user.deny',
      payload: { tool_call_id: toolCallId, reason },
    });
  }

  /** Cancel the session */
  cancel(): void {
    this._state = 'cancelled';
    this._send({ type: 'user.cancel' });
  }

  /** Close the session and WebSocket */
  close(): void {
    if (this._closed) return;
    this._send({ type: 'session.close' });
    this.ws.close();
    this._handleClose();
  }

  // ---- Internal ----

  private _send(msg: Record<string, unknown>): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private _handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data as string) as AgentEvent & {
        session_id?: string;
        sequence?: number;
      };
      this._sequenceCounter++;

      // Update state based on event type
      switch (data.type) {
        case 'agent.request_input':
          this._state = 'awaiting_input';
          break;
        case 'session.completed':
          this._state = 'completed';
          break;
        case 'session.failed':
          this._state = 'failed';
          break;
        case 'agent.error':
          if (!(data as { payload: { recoverable: boolean } }).payload.recoverable) {
            this._state = 'error';
          }
          break;
        default:
          if (this._state === 'awaiting_input' || this._state === 'connecting') {
            this._state = 'running';
          }
      }

      // Deliver to async generator or queue
      if (this._messageResolvers.length > 0) {
        const resolve = this._messageResolvers.shift()!;
        resolve(data);
      } else {
        this._messageQueue.push(data);
      }

      // Handle terminal states
      if (data.type === 'session.completed' || data.type === 'session.failed') {
        this._handleClose();
      }
    } catch {
      // Ignore parse errors
    }
  }

  private _handleClose(): void {
    if (this._closed) return;
    this._closed = true;

    // Resolve all pending waiters with null
    for (const resolve of this._messageResolvers) {
      resolve(null);
    }
    this._messageResolvers = [];
  }

  private _nextEvent(): Promise<AgentEvent | null> {
    // Return queued event if available
    if (this._messageQueue.length > 0) {
      return Promise.resolve(this._messageQueue.shift()!);
    }

    // If closed, return null
    if (this._closed) {
      return Promise.resolve(null);
    }

    // Wait for next event
    return new Promise<AgentEvent | null>((resolve) => {
      this._messageResolvers.push(resolve);
    });
  }
}
