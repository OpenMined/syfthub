/**
 * API Token Repository Port (Output)
 *
 * Defines the interface for API token persistence operations.
 * Implemented by infrastructure adapters (PostgreSQL, etc.)
 */

import { ApiToken } from '../../../domain/entities/ApiToken';
import { ApiTokenId, UserId } from '../../../domain/value-objects/Identifiers';

export interface ApiTokenRepository {
  /**
   * Find token by ID
   * @returns Token or null if not found
   */
  findById(id: ApiTokenId): Promise<ApiToken | null>;

  /**
   * Find token by hash (for authentication)
   * Only returns non-revoked tokens
   * @returns Token or null if not found
   */
  findByHash(hash: Buffer): Promise<ApiToken | null>;

  /**
   * Find all tokens for a user
   * Only returns non-revoked tokens, ordered by creation date (newest first)
   */
  findByUserId(userId: UserId): Promise<ApiToken[]>;

  /**
   * Save a new token
   */
  save(token: ApiToken): Promise<void>;

  /**
   * Update an existing token
   * Uses optimistic locking via version field
   * @throws OptimisticLockError if version mismatch
   */
  update(token: ApiToken): Promise<void>;

  /**
   * Count tokens for a user (non-revoked only)
   * Used to enforce maximum token limit
   */
  countByUserId(userId: UserId): Promise<number>;
}
