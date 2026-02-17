import type { HTTPClient } from '../http.js';
import type {
  UserAggregator,
  UserAggregatorCreateInput,
  UserAggregatorUpdateInput,
} from '../models/index.js';

/**
 * Resource for managing user's aggregator configurations.
 *
 * Aggregators are custom RAG orchestration service endpoints that users can
 * configure to use for chat operations. Each user can have multiple aggregator
 * configurations, with one set as the default.
 *
 * The first aggregator created is automatically set as the default. Only one
 * aggregator can be the default at a time; setting a new default automatically
 * unsets the previous one.
 *
 * @example
 * // List all aggregators
 * const aggregators = await client.users.aggregators.list();
 * for (const agg of aggregators) {
 *   console.log(`${agg.name}: ${agg.url}`);
 * }
 *
 * @example
 * // Create a new aggregator
 * const agg = await client.users.aggregators.create({
 *   name: 'My Custom Aggregator',
 *   url: 'https://my-aggregator.example.com'
 * });
 *
 * @example
 * // Set as default
 * const defaultAgg = await client.users.aggregators.setDefault(agg.id);
 */
export class AggregatorsResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * List all aggregator configurations for the current user.
   *
   * @returns Array of UserAggregator objects
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const aggregators = await client.users.aggregators.list();
   * for (const agg of aggregators) {
   *   if (agg.isDefault) {
   *     console.log(`Default: ${agg.name}`);
   *   }
   * }
   */
  async list(): Promise<UserAggregator[]> {
    return this.http.get<UserAggregator[]>('/api/v1/users/me/aggregators');
  }

  /**
   * Get a specific aggregator configuration by ID.
   *
   * @param aggregatorId - The aggregator ID
   * @returns The UserAggregator object
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If aggregator not found
   *
   * @example
   * const agg = await client.users.aggregators.get(1);
   * console.log(`${agg.name}: ${agg.url}`);
   */
  async get(aggregatorId: number): Promise<UserAggregator> {
    return this.http.get<UserAggregator>(`/api/v1/users/me/aggregators/${aggregatorId}`);
  }

  /**
   * Create a new aggregator configuration.
   *
   * The first aggregator created is automatically set as the default.
   *
   * @param input - Aggregator creation input
   * @returns The created UserAggregator object
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If input is invalid
   *
   * @example
   * const agg = await client.users.aggregators.create({
   *   name: 'My Custom Aggregator',
   *   url: 'https://my-aggregator.example.com'
   * });
   * console.log(`Created: ${agg.id}`);
   */
  async create(input: UserAggregatorCreateInput): Promise<UserAggregator> {
    return this.http.post<UserAggregator>('/api/v1/users/me/aggregators', input);
  }

  /**
   * Update an aggregator configuration.
   *
   * Only provided fields will be updated.
   *
   * @param aggregatorId - The aggregator ID to update
   * @param input - Fields to update
   * @returns The updated UserAggregator object
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If aggregator not found
   * @throws {ValidationError} If input is invalid
   *
   * @example
   * const agg = await client.users.aggregators.update(1, {
   *   name: 'Updated Name'
   * });
   */
  async update(aggregatorId: number, input: UserAggregatorUpdateInput): Promise<UserAggregator> {
    return this.http.put<UserAggregator>(`/api/v1/users/me/aggregators/${aggregatorId}`, input);
  }

  /**
   * Delete an aggregator configuration.
   *
   * @param aggregatorId - The aggregator ID to delete
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If aggregator not found
   *
   * @example
   * await client.users.aggregators.delete(1);
   */
  async delete(aggregatorId: number): Promise<void> {
    await this.http.delete<void>(`/api/v1/users/me/aggregators/${aggregatorId}`);
  }

  /**
   * Set an aggregator as the default.
   *
   * Only one aggregator can be the default at a time. Setting a new default
   * automatically unsets the previous one.
   *
   * @param aggregatorId - The aggregator ID to set as default
   * @returns The updated UserAggregator object with isDefault=true
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If aggregator not found
   *
   * @example
   * const agg = await client.users.aggregators.setDefault(2);
   * console.log(`${agg.name} is now the default`);
   */
  async setDefault(aggregatorId: number): Promise<UserAggregator> {
    return this.http.patch<UserAggregator>(`/api/v1/users/me/aggregators/${aggregatorId}/default`);
  }
}
