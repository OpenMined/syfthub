/**
 * Message Queue models for pub/consume operations.
 */

/**
 * A message from the queue.
 */
export interface MQMessage {
  /** Unique message identifier (UUID) */
  id: string;
  /** Sender's username */
  fromUsername: string;
  /** Sender's user ID */
  fromUserId: number;
  /** The message payload */
  message: string;
  /** Timestamp when message was queued */
  queuedAt: Date;
}

/**
 * Response after publishing a message.
 */
export interface PublishResponse {
  /** Status of the publish operation */
  status: string;
  /** Timestamp when message was queued */
  queuedAt: Date;
  /** Username of the recipient */
  targetUsername: string;
  /** Current queue length after publish */
  queueLength: number;
}

/**
 * Response with consumed messages.
 */
export interface ConsumeResponse {
  /** List of consumed messages */
  messages: MQMessage[];
  /** Number of messages remaining in queue */
  remaining: number;
}

/**
 * Response with queue status information.
 */
export interface QueueStatusResponse {
  /** Current number of messages in queue */
  queueLength: number;
  /** Username of the queue owner */
  username: string;
}

/**
 * Response with peeked messages (not consumed).
 */
export interface PeekResponse {
  /** List of messages (not removed from queue) */
  messages: MQMessage[];
  /** Total number of messages in queue */
  total: number;
}

/**
 * Response after clearing the queue.
 */
export interface ClearResponse {
  /** Status of the clear operation */
  status: string;
  /** Number of messages cleared */
  cleared: number;
}

/**
 * Input for publishing a message.
 * The target type is auto-detected by prefix:
 * - Regular username (e.g., "alice") - publishes to user's queue
 * - Reserved queue ID (e.g., "rq_abc123") - publishes to reserved queue
 */
export interface PublishInput {
  /** Username of the recipient or reserved queue ID (with 'rq_' prefix) */
  targetUsername: string;
  /** The message payload (1-65536 characters, can be JSON string) */
  message: string;
}

/**
 * Options for consuming messages.
 * By default, consumes from the authenticated user's queue.
 * If queueId is provided, consumes from that reserved queue using the token.
 */
export interface ConsumeOptions {
  /** Maximum number of messages to retrieve (1-100, default 10) */
  limit?: number;
  /** Optional reserved queue ID (must start with 'rq_') */
  queueId?: string;
  /** Required when queueId is provided. Authentication token for the reserved queue. */
  token?: string;
}

/**
 * Options for peeking at messages.
 */
export interface PeekOptions {
  /** Maximum number of messages to peek (1-100, default 10) */
  limit?: number;
}

// ==============================================================================
// Reserved Queue Types (for ephemeral queues used by aggregator/tunneling)
// ==============================================================================

/**
 * Options for reserving a queue.
 */
export interface ReserveQueueOptions {
  /** Time-to-live in seconds (30-3600, default 300) */
  ttl?: number;
}

/**
 * Response after reserving an ephemeral queue.
 */
export interface ReserveQueueResponse {
  /** Unique queue identifier (starts with 'rq_') */
  queueId: string;
  /** Secret token for consuming from this queue */
  token: string;
  /** When the queue will expire */
  expiresAt: Date;
  /** TTL in seconds */
  ttl: number;
}

/**
 * Input for releasing a reserved queue.
 */
export interface ReleaseQueueInput {
  /** Queue identifier */
  queueId: string;
  /** Secret token for authenticating queue access */
  token: string;
}

/**
 * Response after releasing a reserved queue.
 */
export interface ReleaseQueueResponse {
  /** Queue identifier that was released */
  queueId: string;
  /** Number of messages that were in the queue */
  messagesCleared: number;
}
