/**
 * User Repository Port
 *
 * Defines the interface for user persistence operations.
 */

import { User } from '../../../domain/entities/User';
import { UserId } from '../../../domain/value-objects/Identifiers';

export interface UserRepository {
  /**
   * Save a new user to the repository
   */
  save(user: User): Promise<void>;

  /**
   * Find a user by their unique ID
   */
  findById(id: UserId): Promise<User | null>;

  /**
   * Find a user by their email address
   */
  findByEmail(email: string): Promise<User | null>;

  /**
   * Check if an email is already registered
   */
  emailExists(email: string): Promise<boolean>;
}
