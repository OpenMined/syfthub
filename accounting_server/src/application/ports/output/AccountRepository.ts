/**
 * Account Repository Port (Output)
 *
 * Defines the interface for account persistence operations.
 * Implemented by infrastructure adapters (PostgreSQL, etc.)
 */

import { Account } from '../../../domain/entities/Account';
import { AccountId, UserId } from '../../../domain/value-objects/Identifiers';

export interface AccountRepository {
  /**
   * Find account by ID
   * @returns Account or null if not found
   */
  findById(id: AccountId): Promise<Account | null>;

  /**
   * Find account by ID with row-level lock for update
   * Use within a transaction for balance modifications
   */
  findByIdForUpdate(id: AccountId): Promise<Account | null>;

  /**
   * Find all accounts for a user
   */
  findByUserId(userId: UserId): Promise<Account[]>;

  /**
   * Find multiple accounts by IDs with row-level locks
   * Returns accounts in consistent order (by ID) to prevent deadlocks
   */
  findByIdsForUpdate(ids: AccountId[]): Promise<Account[]>;

  /**
   * Save a new account
   */
  save(account: Account): Promise<void>;

  /**
   * Update an existing account
   * Uses optimistic locking via version field
   * @throws OptimisticLockError if version mismatch
   */
  update(account: Account): Promise<void>;

  /**
   * Check if an account exists
   */
  exists(id: AccountId): Promise<boolean>;
}
