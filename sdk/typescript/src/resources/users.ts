import type { HTTPClient } from '../http.js';
import type { User, UserUpdateInput } from '../models/index.js';

/**
 * Users resource for profile management and availability checks.
 *
 * @example
 * // Update your profile
 * const user = await client.users.update({
 *   fullName: 'Alice Smith',
 *   avatarUrl: 'https://example.com/avatar.jpg'
 * });
 *
 * @example
 * // Check if username is available
 * const available = await client.users.checkUsername('newusername');
 *
 * @example
 * // Check if email is available
 * const available = await client.users.checkEmail('new@example.com');
 */
export class UsersResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Update the current user's profile.
   *
   * Only provided fields will be updated.
   *
   * @param input - Fields to update
   * @returns The updated User
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If input validation fails
   */
  async update(input: UserUpdateInput): Promise<User> {
    return this.http.put<User>('/api/v1/users/me', input);
  }

  /**
   * Check if a username is available.
   *
   * @param username - Username to check
   * @returns True if the username is available
   */
  async checkUsername(username: string): Promise<boolean> {
    const response = await this.http.get<{ available: boolean }>(
      `/api/v1/users/check-username/${encodeURIComponent(username)}`,
      undefined,
      { includeAuth: false }
    );
    return response.available;
  }

  /**
   * Check if an email is available.
   *
   * @param email - Email to check
   * @returns True if the email is available
   */
  async checkEmail(email: string): Promise<boolean> {
    const response = await this.http.get<{ available: boolean }>(
      `/api/v1/users/check-email/${encodeURIComponent(email)}`,
      undefined,
      { includeAuth: false }
    );
    return response.available;
  }
}
