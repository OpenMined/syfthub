import type { HTTPClient } from '../http.js';
import type {
  Endpoint,
  EndpointCreateInput,
  EndpointUpdateInput,
  Visibility,
} from '../models/index.js';
import { PageIterator } from '../pagination.js';

/**
 * Options for listing endpoints.
 */
export interface ListEndpointsOptions {
  /** Filter by visibility level */
  visibility?: Visibility;
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

/**
 * My Endpoints resource for CRUD operations on user's own endpoints.
 *
 * For browsing public endpoints from other users, see the Hub resource.
 *
 * @example
 * // List your endpoints
 * for await (const endpoint of client.myEndpoints.list()) {
 *   console.log(endpoint.name);
 * }
 *
 * @example
 * // Create a new endpoint
 * const endpoint = await client.myEndpoints.create({
 *   name: 'My API',
 *   type: 'model',
 *   visibility: 'public',
 *   description: 'A cool API'
 * });
 *
 * @example
 * // Get a specific endpoint
 * const endpoint = await client.myEndpoints.get('alice/my-api');
 *
 * @example
 * // Update an endpoint
 * const updated = await client.myEndpoints.update('alice/my-api', {
 *   description: 'Updated description'
 * });
 *
 * @example
 * // Delete an endpoint
 * await client.myEndpoints.delete('alice/my-api');
 */
export class MyEndpointsResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Parse an endpoint path into owner and slug.
   *
   * @param path - Path in "owner/slug" format
   * @returns Tuple of [owner, slug]
   * @throws {Error} If path format is invalid
   */
  private parsePath(path: string): [string, string] {
    const parts = path.replace(/^\/|\/$/g, '').split('/');
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new Error(`Invalid endpoint path: '${path}'. Expected format: 'owner/slug'`);
    }
    return [parts[0], parts[1]];
  }

  /**
   * Resolve an endpoint path to its ID.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @returns The endpoint ID
   */
  private async resolveEndpointId(path: string): Promise<number> {
    const [owner, slug] = this.parsePath(path);

    // Get the endpoint via the public route (returns full details for owners)
    const response = await this.http.get<{ id?: number }>(`/${owner}/${slug}`);

    if (response.id === undefined) {
      throw new Error(
        `Could not resolve endpoint ID for '${path}'. Make sure you own this endpoint.`
      );
    }

    return response.id;
  }

  /**
   * List the current user's endpoints.
   *
   * @param options - Filtering and pagination options
   * @returns PageIterator that lazily fetches endpoints
   * @throws {AuthenticationError} If not authenticated
   */
  list(options?: ListEndpointsOptions): PageIterator<Endpoint> {
    const pageSize = options?.pageSize ?? 20;

    return new PageIterator<Endpoint>(async (skip, limit) => {
      const params: Record<string, unknown> = { skip, limit };
      if (options?.visibility) {
        params['visibility'] = options.visibility;
      }
      return this.http.get<Endpoint[]>('/api/v1/endpoints', params);
    }, pageSize);
  }

  /**
   * Create a new endpoint.
   *
   * @param input - Endpoint creation details
   * @param organizationId - Optional organization ID (for org-owned endpoints)
   * @returns The created Endpoint
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If input validation fails
   */
  async create(input: EndpointCreateInput, organizationId?: number): Promise<Endpoint> {
    const body = organizationId !== undefined ? { ...input, organizationId } : input;
    return this.http.post<Endpoint>('/api/v1/endpoints', body);
  }

  /**
   * Get a specific endpoint by path.
   *
   * @param path - Endpoint path in "owner/slug" format (e.g., "alice/my-api")
   * @returns The Endpoint
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   * @throws {AuthorizationError} If not authorized to view
   */
  async get(path: string): Promise<Endpoint> {
    const [owner, slug] = this.parsePath(path);
    return this.http.get<Endpoint>(`/${owner}/${slug}`);
  }

  /**
   * Update an endpoint.
   *
   * Only provided fields will be updated.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @param input - Fields to update
   * @returns The updated Endpoint
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   * @throws {AuthorizationError} If not owner/admin
   */
  async update(path: string, input: EndpointUpdateInput): Promise<Endpoint> {
    const endpointId = await this.resolveEndpointId(path);
    return this.http.patch<Endpoint>(`/api/v1/endpoints/${endpointId}`, input);
  }

  /**
   * Delete an endpoint.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   * @throws {AuthorizationError} If not owner/admin
   */
  async delete(path: string): Promise<void> {
    const endpointId = await this.resolveEndpointId(path);
    await this.http.delete<void>(`/api/v1/endpoints/${endpointId}`);
  }
}
