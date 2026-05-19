/**
 * Agent resource — direct peer-to-peer agent sessions over NATS (protocol v2).
 *
 * The browser dials an agent host directly: it connects to NATS with a
 * short-lived peer token, publishes an end-to-end-encrypted agent_session_start
 * to the host's space subject, and receives encrypted agent events on its
 * private peer channel. The aggregator is no longer in the agent path.
 *
 * This mirrors the Go `transport.AgentDialer` / `AgentClientSession` in
 * `sdk/golang/syfthubapi/transport/agent_dial.go`. See
 * syfthub-desktop/docs/p2p-agent-direct-nats-design.md.
 *
 * @example
 * const session = await client.agent.startSession({
 *   prompt: 'Help me refactor this code',
 *   endpoint: 'alice/code-assistant',
 * });
 *
 * for await (const event of session.events()) {
 *   if (event.type === 'agent.message') {
 *     console.log(event.payload.content);
 *   }
 * }
 */
import { connect } from 'nats.ws';
import type { NatsConnection, Subscription } from 'nats.ws';

import { SessionCipher, b64urlEncode, generateIdentityKeyPair } from '../crypto.js';
import { SyftHubError } from '../errors.js';
import type { AgentEvent, AgentSessionOptions, AgentSessionState } from '../models/agent.js';
import type { AuthResource } from './auth.js';

/** Protocol tag carried by every v2 NATS message (see Go `AgentProtocolV2`). */
const PROTOCOL_V2 = 'syfthub-agent/v2';

/** NATS subject prefixes — client→host on spaces, host→client on peer. */
const SPACE_SUBJECT_PREFIX = 'syfthub.spaces.';
const PEER_SUBJECT_PREFIX = 'syfthub.peer.';

/** v2 envelope message types (see Go `MsgType*`). */
const MSG_SESSION_START = 'agent_session_start';
const MSG_USER_MESSAGE = 'agent_user_message';
const MSG_SESSION_CANCEL = 'agent_session_cancel';
const MSG_AGENT_EVENT = 'agent_event';

/** agent_user_message sub-types (see Go `UserMessageType*`). */
const USER_MSG_MESSAGE = 'user_message';
const USER_MSG_CONFIRM = 'user_confirm';
const USER_MSG_DENY = 'user_deny';

const encoder = new TextEncoder();
const decoder = new TextDecoder();

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
 * The plaintext v2 NATS message wrapper (see Go `AgentEnvelope` in
 * `sdk/golang/syfthubapi/agentwire.go`). The wrapper fields are plaintext so
 * the recipient can derive the session key; `encrypted_payload` is the
 * AES-256-GCM ciphertext of the message-type-specific payload.
 */
interface AgentEnvelope {
  protocol: string;
  type: string;
  correlation_id: string;
  session_id: string;
  reply_to?: string;
  satellite_token?: string;
  sender_public_key: string;
  nonce: string;
  encrypted_payload: string;
}

/** Decrypted payload of an agent_event message (see Go `AgentEventPayload`). */
interface AgentEventPayload {
  session_id: string;
  event_type: string;
  sequence: number;
  data: unknown;
}

/**
 * AgentResource opens direct peer-to-peer agent sessions.
 */
export class AgentResource {
  constructor(private readonly auth: AuthResource) {}

  /**
   * Start a new agent session against a remote host.
   *
   * @param options - Session options including prompt, endpoint, and config
   * @returns An AgentSessionClient for interacting with the session
   */
  async startSession(options: AgentSessionOptions): Promise<AgentSessionClient> {
    const { owner, slug } = parseEndpoint(options.endpoint);

    // The browser holds no long-term key — it uses a per-session ephemeral
    // identity keypair. The host derives the session cipher from the public
    // half carried in every envelope.
    const identity = generateIdentityKeyPair();
    const sessionId = crypto.randomUUID();

    // Resolve the host's identity key, a satellite token (proof of identity),
    // and a peer channel + NATS credential — in parallel.
    const [satellite, peer, hostKey] = await Promise.all([
      this.auth.getSatelliteToken(owner),
      this.auth.getPeerToken([owner]),
      this.auth.getEncryptionPublicKey(owner),
    ]);

    if (!hostKey.encryptionPublicKey) {
      throw new AgentSessionError(
        `Host "${owner}" has not registered an encryption key; cannot open an agent session.`
      );
    }

    const cipher = new SessionCipher(
      identity.privateKey,
      hostKey.encryptionPublicKey,
      sessionId
    );

    // Connect to NATS with the short-lived peer token. The auth-callout service
    // resolves the token and scopes the connection to this peer channel plus
    // the target space subject.
    let nc: NatsConnection;
    try {
      nc = await connect({
        servers: peer.natsUrl,
        token: peer.peerToken,
        name: `syfthub-web-agent-${sessionId}`,
      });
    } catch (error) {
      throw new AgentSessionError(
        `Failed to connect to NATS: ${error instanceof Error ? error.message : String(error)}`
      );
    }

    // Subscribe to the reply channel before publishing so no early event is
    // missed.
    const subscription = nc.subscribe(PEER_SUBJECT_PREFIX + peer.peerChannel);

    const session = new AgentSessionClient(
      nc,
      subscription,
      cipher,
      sessionId,
      SPACE_SUBJECT_PREFIX + owner,
      b64urlEncode(identity.publicKey)
    );

    // Publish the encrypted agent_session_start.
    const startPayload: Record<string, unknown> = {
      session_id: sessionId,
      prompt: options.prompt,
      endpoint_slug: slug,
      config: options.config ? toWireConfig(options.config) : {},
    };
    if (options.messages) {
      startPayload.messages = options.messages;
    }

    try {
      session.publishRequest(
        MSG_SESSION_START,
        startPayload,
        satellite.targetToken,
        peer.peerChannel
      );
    } catch (error) {
      await session.close();
      throw error;
    }

    if (options.signal) {
      options.signal.addEventListener('abort', () => void session.close(), { once: true });
    }

    return session;
  }
}

/**
 * Client for an active peer-to-peer agent session.
 */
export class AgentSessionClient {
  private _state: AgentSessionState = 'running';
  private _closed = false;
  private readonly _queue: AgentEvent[] = [];
  private readonly _resolvers: Array<(value: AgentEvent | null) => void> = [];

  constructor(
    private readonly nc: NatsConnection,
    private readonly subscription: Subscription,
    private readonly cipher: SessionCipher,
    public readonly sessionId: string,
    private readonly targetSubject: string,
    private readonly senderPublicKey: string
  ) {
    void this._readLoop();
  }

  /** Current session state. */
  get state(): AgentSessionState {
    return this._state;
  }

  /**
   * Async generator yielding agent events until the session ends.
   *
   * @example
   * for await (const event of session.events()) {
   *   console.log(event.type, event.payload);
   * }
   */
  async *events(): AsyncGenerator<AgentEvent> {
    while (!this._closed || this._queue.length > 0) {
      const event = await this._next();
      if (event === null) break;
      yield event;
    }
  }

  /** Send a follow-up user message to the agent. */
  sendMessage(content: string): void {
    this.publishRequest(MSG_USER_MESSAGE, {
      session_id: this.sessionId,
      message: { type: USER_MSG_MESSAGE, content },
    });
  }

  /** Confirm a tool call awaiting confirmation. */
  confirm(toolCallId: string): void {
    this.publishRequest(MSG_USER_MESSAGE, {
      session_id: this.sessionId,
      message: { type: USER_MSG_CONFIRM, tool_call_id: toolCallId },
    });
  }

  /** Deny a tool call awaiting confirmation. */
  deny(toolCallId: string, reason?: string): void {
    this.publishRequest(MSG_USER_MESSAGE, {
      session_id: this.sessionId,
      message: { type: USER_MSG_DENY, tool_call_id: toolCallId, reason: reason ?? '' },
    });
  }

  /** Ask the host to end the session, then close locally. */
  cancel(): void {
    this._state = 'cancelled';
    try {
      this.publishRequest(MSG_SESSION_CANCEL, { session_id: this.sessionId });
    } catch {
      // Best-effort — the host may already be gone.
    }
    void this.close();
  }

  /** Close the session: unsubscribe and drop the NATS connection. */
  async close(): Promise<void> {
    if (this._closed) {
      return;
    }
    this._closed = true;
    try {
      this.subscription.unsubscribe();
    } catch {
      // ignore
    }
    try {
      await this.nc.close();
    } catch {
      // ignore
    }
    for (const resolve of this._resolvers.splice(0)) {
      resolve(null);
    }
  }

  /**
   * Encrypt `payload` for the request direction and publish it as a v2
   * envelope to the host's space subject. Public so AgentResource can send the
   * initial agent_session_start.
   */
  publishRequest(
    msgType: string,
    payload: unknown,
    satelliteToken?: string,
    replyTo?: string
  ): void {
    if (this._closed && msgType !== MSG_SESSION_CANCEL) {
      throw new AgentSessionError(`agent session ${this.sessionId} is closed`);
    }
    const correlationId = crypto.randomUUID();
    const plaintext = encoder.encode(JSON.stringify(payload));
    const { nonce, ciphertext } = this.cipher.encryptRequest(plaintext, correlationId);

    const envelope: AgentEnvelope = {
      protocol: PROTOCOL_V2,
      type: msgType,
      correlation_id: correlationId,
      session_id: this.sessionId,
      sender_public_key: this.senderPublicKey,
      nonce,
      encrypted_payload: ciphertext,
    };
    if (replyTo) {
      envelope.reply_to = replyTo;
    }
    if (satelliteToken) {
      envelope.satellite_token = satelliteToken;
    }
    this.nc.publish(this.targetSubject, encoder.encode(JSON.stringify(envelope)));
  }

  // ---- Internal ----

  /** Drains the subscription, decrypting and delivering events. */
  private async _readLoop(): Promise<void> {
    try {
      for await (const msg of this.subscription) {
        const event = this._decodeEvent(msg.data);
        if (event === null) {
          continue;
        }
        this._applyState(event);
        this._deliver(event);
        if (event.type === 'session.completed' || event.type === 'session.failed') {
          break;
        }
      }
    } catch {
      // Subscription closed or errored — fall through to close().
    } finally {
      await this.close();
    }
  }

  /** Decode one NATS message into a typed event, or null to skip it. */
  private _decodeEvent(raw: Uint8Array): AgentEvent | null {
    let envelope: AgentEnvelope;
    try {
      envelope = JSON.parse(decoder.decode(raw)) as AgentEnvelope;
    } catch {
      return null;
    }
    if (envelope.type !== MSG_AGENT_EVENT) {
      return null;
    }
    try {
      const plaintext = this.cipher.decryptResponse(
        envelope.nonce,
        envelope.encrypted_payload,
        envelope.correlation_id
      );
      const payload = JSON.parse(decoder.decode(plaintext)) as AgentEventPayload;
      return { type: payload.event_type, payload: payload.data } as AgentEvent;
    } catch {
      // Drop malformed / undecryptable events rather than tearing down.
      return null;
    }
  }

  private _applyState(event: AgentEvent): void {
    switch (event.type) {
      case 'agent.request_input': {
        this._state = 'awaiting_input';
        break;
      }
      case 'session.completed': {
        this._state = 'completed';
        break;
      }
      case 'session.failed': {
        this._state = 'failed';
        break;
      }
      case 'agent.error': {
        if (!event.payload.recoverable) {
          this._state = 'error';
        }
        break;
      }
      default: {
        if (this._state === 'awaiting_input') {
          this._state = 'running';
        }
      }
    }
  }

  private _deliver(event: AgentEvent): void {
    const resolve = this._resolvers.shift();
    if (resolve) {
      resolve(event);
    } else {
      this._queue.push(event);
    }
  }

  private _next(): Promise<AgentEvent | null> {
    if (this._queue.length > 0) {
      return Promise.resolve(this._queue.shift()!);
    }
    if (this._closed) {
      return Promise.resolve(null);
    }
    return new Promise<AgentEvent | null>((resolve) => {
      this._resolvers.push(resolve);
    });
  }
}

/** Parse an endpoint given as "owner/slug" or { owner, slug }. */
function parseEndpoint(
  endpoint: AgentSessionOptions['endpoint']
): { owner: string; slug: string } {
  if (typeof endpoint === 'string') {
    const parts = endpoint.split('/');
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new AgentSessionError(
        `Endpoint must be in 'owner/slug' format, got: ${endpoint}`
      );
    }
    return { owner: parts[0], slug: parts[1] };
  }
  return { owner: endpoint.owner, slug: endpoint.slug };
}

/** Map the camelCase SDK AgentConfig to the snake_case wire shape. */
function toWireConfig(
  config: NonNullable<AgentSessionOptions['config']>
): Record<string, unknown> {
  const wire: Record<string, unknown> = {};
  if (config.maxTokens !== undefined) {
    wire.max_tokens = config.maxTokens;
  }
  if (config.temperature !== undefined) {
    wire.temperature = config.temperature;
  }
  if (config.systemPrompt !== undefined) {
    wire.system_prompt = config.systemPrompt;
  }
  if (config.metadata !== undefined) {
    wire.metadata = config.metadata;
  }
  return wire;
}
