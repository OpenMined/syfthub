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
 */
export interface PublishInput {
  /** Username of the recipient (1-50 characters) */
  targetUsername: string;
  /** The message payload (1-65536 characters, can be JSON string) */
  message: string;
}

/**
 * Options for consuming messages.
 */
export interface ConsumeOptions {
  /** Maximum number of messages to retrieve (1-100, default 10) */
  limit?: number;
}

/**
 * Options for peeking at messages.
 */
export interface PeekOptions {
  /** Maximum number of messages to peek (1-100, default 10) */
  limit?: number;
}
