/**
 * Resource for message queue operations.
 */

import type { HTTPClient } from '../http.js';
import type {
  ClearResponse,
  ConsumeOptions,
  ConsumeResponse,
  PeekOptions,
  PeekResponse,
  PublishInput,
  PublishResponse,
  QueueStatusResponse,
  ReleaseQueueInput,
  ReleaseQueueResponse,
  ReserveQueueOptions,
  ReserveQueueResponse,
} from '../models/mq.js';

/**
 * Resource for message queue pub/consume operations.
 *
 * This resource provides access to the Redis-backed message queue system
 * for asynchronous user-to-user messaging and ephemeral reserved queues.
 *
 * @example
 * // Publish a message to another user
 * const result = await client.mq.publish({
 *   targetUsername: 'bob',
 *   message: JSON.stringify({ type: 'hello', data: 'Hi Bob!' }),
 * });
 * console.log(`Message queued at ${result.queuedAt}`);
 *
 * // Consume messages from your queue
 * const response = await client.mq.consume({ limit: 10 });
 * for (const msg of response.messages) {
 *   console.log(`From ${msg.fromUsername}: ${msg.message}`);
 * }
 *
 * // Check queue status
 * const status = await client.mq.status();
 * console.log(`You have ${status.queueLength} messages waiting`);
 *
 * // Peek without consuming
 * const peek = await client.mq.peek({ limit: 5 });
 * console.log(`Next messages:`, peek.messages);
 *
 * // Clear your queue
 * const cleared = await client.mq.clear();
 * console.log(`Cleared ${cleared.cleared} messages`);
 *
 * @example
 * // Reserved queue workflow
 * const queue = await client.mq.reserveQueue({ ttl: 300 });
 * console.log(`Reserved queue: ${queue.queueId}`);
 *
 * // Publish to reserved queue (rq_ prefix auto-detected)
 * await client.mq.publish({
 *   targetUsername: queue.queueId,  // rq_ prefix auto-detected
 *   message: JSON.stringify({ type: 'response', data: 'Hello!' }),
 * });
 *
 * // Consume from the reserved queue
 * const response = await client.mq.consume({
 *   queueId: queue.queueId,
 *   token: queue.token,
 *   limit: 10,
 * });
 *
 * // Release when done
 * await client.mq.releaseQueue({ queueId: queue.queueId, token: queue.token });
 */
export class MQResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Publish a message to another user's queue or a reserved queue.
   *
   * The target type is auto-detected by prefix:
   * - Regular username (e.g., "alice") - publishes to user's queue
   * - Reserved queue ID (e.g., "rq_abc123") - publishes to reserved queue
   *
   * @param input - The publish input containing target username and message
   * @returns PublishResponse with status and queue information
   *
   * @throws {NotFoundError} If target user or queue doesn't exist
   * @throws {ValidationError} If target user is not active or queue is full
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const result = await client.mq.publish({
   *   targetUsername: 'bob',
   *   message: JSON.stringify({ type: 'request', data: '...' }),
   * });
   * console.log(`Published! Queue length: ${result.queueLength}`);
   */
  async publish(input: PublishInput): Promise<PublishResponse> {
    return this.http.post<PublishResponse>('/api/v1/mq/pub', {
      target_username: input.targetUsername,
      message: input.message,
    });
  }

  /**
   * Consume messages from your queue or a reserved queue.
   *
   * By default, consumes from the authenticated user's queue.
   * If queueId is provided (with 'rq_' prefix), consumes from that
   * reserved queue using the provided token for authentication.
   *
   * Messages are returned in FIFO order (oldest first) and are
   * removed from the queue.
   *
   * @param options - Optional consume options (limit, queueId, token)
   * @returns ConsumeResponse with messages and remaining count
   *
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If reserved queue not found or expired
   * @throws {AuthorizationError} If reserved queue token is invalid
   * @throws {ValidationError} If queueId provided without token
   *
   * @example
   * // Consume from your own queue
   * const response = await client.mq.consume({ limit: 10 });
   * for (const msg of response.messages) {
   *   console.log(`From ${msg.fromUsername}: ${msg.message}`);
   * }
   *
   * @example
   * // Consume from a reserved queue
   * const response = await client.mq.consume({
   *   queueId: 'rq_abc123',
   *   token: 'secret_token',
   *   limit: 10,
   * });
   */
  async consume(options: ConsumeOptions = {}): Promise<ConsumeResponse> {
    const body: Record<string, string | number> = { limit: options.limit ?? 10 };
    if (options.queueId !== undefined) {
      body.queue_id = options.queueId;
    }
    if (options.token !== undefined) {
      body.token = options.token;
    }
    return this.http.post<ConsumeResponse>('/api/v1/mq/consume', body);
  }

  /**
   * Get the status of your queue.
   *
   * @returns QueueStatusResponse with queue length
   *
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const status = await client.mq.status();
   * console.log(`You have ${status.queueLength} messages waiting`);
   */
  async status(): Promise<QueueStatusResponse> {
    return this.http.get<QueueStatusResponse>('/api/v1/mq/status');
  }

  /**
   * Peek at messages without consuming them.
   *
   * Messages are returned in FIFO order (oldest first) but are
   * NOT removed from the queue.
   *
   * @param options - Optional peek options
   * @returns PeekResponse with messages and total count
   *
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const peek = await client.mq.peek({ limit: 5 });
   * console.log(`Total messages: ${peek.total}`);
   * for (const msg of peek.messages) {
   *   console.log(`Preview: ${msg.message.substring(0, 50)}...`);
   * }
   */
  async peek(options: PeekOptions = {}): Promise<PeekResponse> {
    const body = { limit: options.limit ?? 10 };
    return this.http.post<PeekResponse>('/api/v1/mq/peek', body);
  }

  /**
   * Clear all messages from your queue.
   *
   * This is a destructive operation that cannot be undone.
   *
   * @returns ClearResponse with number of messages cleared
   *
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const result = await client.mq.clear();
   * console.log(`Cleared ${result.cleared} messages`);
   */
  async clear(): Promise<ClearResponse> {
    return this.http.delete<ClearResponse>('/api/v1/mq/clear', undefined);
  }

  // ==========================================================================
  // Reserved Queue Operations (for ephemeral queues used by aggregator/tunneling)
  // ==========================================================================

  /**
   * Reserve an ephemeral queue for receiving messages.
   *
   * Creates a temporary queue with a unique ID and secret token.
   * The queue will automatically expire after the specified TTL.
   *
   * This is used for tunneling workflows where a client needs to receive
   * responses from endpoint owners via the aggregator.
   *
   * @param options - Optional reserve options
   * @returns ReserveQueueResponse with queue_id, token, and expiration
   *
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const queue = await client.mq.reserveQueue({ ttl: 300 });
   * console.log(`Queue ID: ${queue.queueId}, Token: ${queue.token}`);
   */
  async reserveQueue(
    options: ReserveQueueOptions = {}
  ): Promise<ReserveQueueResponse> {
    const body = { ttl: options.ttl ?? 300 };
    return this.http.post<ReserveQueueResponse>('/api/v1/mq/reserve-queue', body);
  }

  /**
   * Release (delete) a reserved queue.
   *
   * Immediately deletes the reserved queue and all pending messages.
   *
   * @param input - Release input containing queueId and token
   * @returns ReleaseQueueResponse with queue_id and messages cleared count
   *
   * @throws {NotFoundError} If queue not found or expired
   * @throws {AuthorizationError} If token is invalid
   *
   * @example
   * const result = await client.mq.releaseQueue({
   *   queueId: 'rq_abc123',
   *   token: 'secret_token',
   * });
   * console.log(`Cleared ${result.messagesCleared} messages`);
   */
  async releaseQueue(input: ReleaseQueueInput): Promise<ReleaseQueueResponse> {
    const body = { queue_id: input.queueId, token: input.token };
    return this.http.post<ReleaseQueueResponse>('/api/v1/mq/release-queue', body);
  }
}
