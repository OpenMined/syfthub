import type { HTTPClient } from '../http.js';
import type { EndpointPublic } from '../models/index.js';
import { PageIterator } from '../pagination.js';

/**
 * Options for browsing endpoints.
 */
export interface BrowseOptions {
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

/**
 * Options for trending endpoints.
 */
export interface TrendingOptions {
  /** Minimum number of stars */
  minStars?: number;
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

/**
 * Hub resource for browsing and discovering public endpoints.
 *
 * For managing your own endpoints, see the MyEndpoints resource.
 *
 * @example
 * // Browse all public endpoints
 * for await (const endpoint of client.hub.browse()) {
 *   console.log(`${endpoint.ownerUsername}/${endpoint.slug}: ${endpoint.name}`);
 * }
 *
 * @example
 * // Get trending endpoints
 * for await (const endpoint of client.hub.trending({ minStars: 10 })) {
 *   console.log(`${endpoint.name} - ${endpoint.starsCount} stars`);
 * }
 *
 * @example
 * // Get a specific endpoint
 * const endpoint = await client.hub.get('alice/cool-api');
 * console.log(endpoint.readme);
 *
 * @example
 * // Star an endpoint (requires auth)
 * await client.hub.star('alice/cool-api');
 *
 * @example
 * // Check if you've starred an endpoint
 * const starred = await client.hub.isStarred('alice/cool-api');
 */
export class HubResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Parse an endpoint path into owner and slug.
   *
   * @param path - Path in "owner/slug" format
   * @returns Tuple of [owner, slug]
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
   * This searches the user's own endpoints to find the ID.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @returns The endpoint ID
   */
  private async resolveEndpointId(path: string): Promise<number> {
    const [, slug] = this.parsePath(path);

    // Search the user's endpoints to find the ID
    // This uses /api/v1/endpoints which returns full details including ID
    const endpoints = await this.http.get<Array<{ id?: number; slug?: string }>>(
      '/api/v1/endpoints',
      { limit: 100 }
    );

    for (const ep of endpoints) {
      if (ep.slug === slug && ep.id !== undefined) {
        return ep.id;
      }
    }

    // Import NotFoundError here to avoid circular dependency
    const { NotFoundError } = await import('../errors.js');
    throw new NotFoundError(
      `Could not resolve endpoint ID for '${path}'. ` +
        'Endpoint not found or you don\'t have access to get its ID.'
    );
  }

  /**
   * Browse all public endpoints.
   *
   * @param options - Pagination options
   * @returns PageIterator that lazily fetches endpoints
   */
  browse(options?: BrowseOptions): PageIterator<EndpointPublic> {
    const pageSize = options?.pageSize ?? 20;

    return new PageIterator<EndpointPublic>(async (skip, limit) => {
      return this.http.get<EndpointPublic[]>(
        '/api/v1/endpoints/public',
        { skip, limit },
        { includeAuth: false }
      );
    }, pageSize);
  }

  /**
   * Get trending endpoints sorted by stars.
   *
   * @param options - Filter and pagination options
   * @returns PageIterator that lazily fetches endpoints
   */
  trending(options?: TrendingOptions): PageIterator<EndpointPublic> {
    const pageSize = options?.pageSize ?? 20;

    return new PageIterator<EndpointPublic>(async (skip, limit) => {
      const params: Record<string, unknown> = { skip, limit };
      if (options?.minStars !== undefined) {
        params['minStars'] = options.minStars;
      }
      return this.http.get<EndpointPublic[]>(
        '/api/v1/endpoints/trending',
        params,
        { includeAuth: false }
      );
    }, pageSize);
  }

  /**
   * Get an endpoint by its path.
   *
   * This method searches the public endpoints API to find the endpoint,
   * which works reliably across all deployment configurations.
   *
   * @param path - Endpoint path in "owner/slug" format (e.g., "alice/cool-api")
   * @returns The EndpointPublic
   * @throws {NotFoundError} If endpoint not found
   */
  async get(path: string): Promise<EndpointPublic> {
    const [owner, slug] = this.parsePath(path);

    // Search public endpoints to find the matching one
    // This approach works because /api/v1/endpoints/public is reliably
    // served by the backend API, unlike /{owner}/{slug} which may be
    // intercepted by frontend routing in some deployments.
    for await (const endpoint of this.browse({ pageSize: 100 })) {
      if (endpoint.ownerUsername === owner && endpoint.slug === slug) {
        return endpoint;
      }
    }

    // Import NotFoundError here to avoid circular dependency
    const { NotFoundError } = await import('../errors.js');
    throw new NotFoundError(
      `Endpoint not found: '${path}'. No public endpoint found with owner '${owner}' and slug '${slug}'.`
    );
  }

  /**
   * Star an endpoint.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   */
  async star(path: string): Promise<void> {
    const endpointId = await this.resolveEndpointId(path);
    await this.http.patch<void>(`/api/v1/endpoints/${endpointId}/star`);
  }

  /**
   * Unstar an endpoint.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   */
  async unstar(path: string): Promise<void> {
    const endpointId = await this.resolveEndpointId(path);
    await this.http.patch<void>(`/api/v1/endpoints/${endpointId}/unstar`);
  }

  /**
   * Check if you have starred an endpoint.
   *
   * @param path - Endpoint path in "owner/slug" format
   * @returns True if starred, False otherwise
   * @throws {AuthenticationError} If not authenticated
   * @throws {NotFoundError} If endpoint not found
   */
  async isStarred(path: string): Promise<boolean> {
    const endpointId = await this.resolveEndpointId(path);
    const response = await this.http.get<{ starred: boolean }>(
      `/api/v1/endpoints/${endpointId}/starred`
    );
    return response.starred ?? false;
  }
}
