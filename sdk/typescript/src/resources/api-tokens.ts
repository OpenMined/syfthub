/**
 * Resource for managing API tokens.
 */

import type { HTTPClient } from '../http.js';
import type {
  APIToken,
  APITokenCreateResponse,
  APITokenListResponse,
  CreateAPITokenInput,
  UpdateAPITokenInput,
} from '../models/api-token.js';

/**
 * Resource for managing API tokens.
 *
 * API tokens provide an alternative to username/password authentication.
 * They are ideal for CI/CD pipelines, scripts, and programmatic access.
 *
 * @example
 * // Create a new token
 * const result = await client.apiTokens.create({
 *   name: 'CI/CD Pipeline',
 *   scopes: ['write'],
 * });
 * console.log('Save this token:', result.token);
 *
 * // List all tokens
 * const { tokens } = await client.apiTokens.list();
 *
 * // Revoke a token
 * await client.apiTokens.revoke(tokenId);
 */
export class APITokensResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Create a new API token.
   *
   * IMPORTANT: The returned token is only shown ONCE!
   * Make sure to save it immediately - it cannot be retrieved later.
   *
   * @param input - Token creation options
   * @returns The created token with the full token value
   *
   * @example
   * const result = await client.apiTokens.create({
   *   name: 'CI/CD Pipeline',
   *   scopes: ['write'],
   *   expiresAt: new Date('2025-12-31'),
   * });
   *
   * // SAVE THIS TOKEN - it will not be shown again!
   * console.log(result.token);
   */
  async create(input: CreateAPITokenInput): Promise<APITokenCreateResponse> {
    return this.http.post<APITokenCreateResponse>('/api/v1/auth/tokens', input);
  }

  /**
   * List all API tokens for the current user.
   *
   * By default, only active tokens are returned.
   * Note: The full token value is never returned - only the prefix.
   *
   * @param options - List options
   * @returns List of tokens and total count
   *
   * @example
   * // List active tokens
   * const { tokens, total } = await client.apiTokens.list();
   *
   * // Include revoked tokens
   * const all = await client.apiTokens.list({ includeInactive: true });
   */
  async list(options: {
    includeInactive?: boolean;
    skip?: number;
    limit?: number;
  } = {}): Promise<APITokenListResponse> {
    const params: Record<string, unknown> = {};
    if (options.includeInactive !== undefined) {
      params.include_inactive = options.includeInactive;
    }
    if (options.skip !== undefined) {
      params.skip = options.skip;
    }
    if (options.limit !== undefined) {
      params.limit = options.limit;
    }
    return this.http.get<APITokenListResponse>('/api/v1/auth/tokens', params);
  }

  /**
   * Get a single API token by ID.
   *
   * Note: The full token value is never returned - only the prefix.
   *
   * @param tokenId - The token ID
   * @returns The token details
   *
   * @example
   * const token = await client.apiTokens.get(123);
   * console.log(token.name, token.lastUsedAt);
   */
  async get(tokenId: number): Promise<APIToken> {
    return this.http.get<APIToken>(`/api/v1/auth/tokens/${tokenId}`);
  }

  /**
   * Update an API token's name.
   *
   * Only the name can be updated. Scopes and expiration cannot be
   * changed after creation.
   *
   * @param tokenId - The token ID
   * @param input - Update options
   * @returns The updated token
   *
   * @example
   * const updated = await client.apiTokens.update(123, {
   *   name: 'New Name',
   * });
   */
  async update(tokenId: number, input: UpdateAPITokenInput): Promise<APIToken> {
    return this.http.patch<APIToken>(`/api/v1/auth/tokens/${tokenId}`, input);
  }

  /**
   * Revoke an API token.
   *
   * The token becomes immediately unusable. This action cannot be undone.
   *
   * @param tokenId - The token ID to revoke
   *
   * @example
   * await client.apiTokens.revoke(123);
   */
  async revoke(tokenId: number): Promise<void> {
    await this.http.delete<void>(`/api/v1/auth/tokens/${tokenId}`);
  }
}
