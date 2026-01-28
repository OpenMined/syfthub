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
} from '../models/mq.js';

/**
 * Resource for message queue pub/consume operations.
 *
 * This resource provides access to the Redis-backed message queue system
 * for asynchronous user-to-user messaging.
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
 */
export class MQResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Publish a message to another user's queue.
   *
   * @param input - The publish input containing target username and message
   * @returns PublishResponse with status and queue information
   *
   * @throws {NotFoundError} If target user doesn't exist
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
    return this.http.post<PublishResponse>('/api/v1/mq/pub', input);
  }

  /**
   * Consume messages from your own queue.
   *
   * Messages are returned in FIFO order (oldest first) and are
   * removed from the queue.
   *
   * @param options - Optional consume options
   * @returns ConsumeResponse with messages and remaining count
   *
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const response = await client.mq.consume({ limit: 10 });
   * for (const msg of response.messages) {
   *   console.log(`From ${msg.fromUsername}: ${msg.message}`);
   *   const data = JSON.parse(msg.message);
   *   // Process message...
   * }
   * console.log(`${response.remaining} messages remaining`);
   */
  async consume(options: ConsumeOptions = {}): Promise<ConsumeResponse> {
    const body = { limit: options.limit ?? 10 };
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
    return this.http.delete<ClearResponse>('/api/v1/mq/clear');
  }
}
