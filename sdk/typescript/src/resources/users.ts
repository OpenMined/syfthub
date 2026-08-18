import type { HTTPClient } from '../http.js';
import type { AccountingCredentials, User, UserUpdateInput } from '../models/index.js';
import { AggregatorsResource } from './aggregators.js';

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
 *
 * @example
 * // Manage aggregators
 * const aggregators = await client.users.aggregators.list();
 * const newAgg = await client.users.aggregators.create({
 *   name: 'My Aggregator',
 *   url: 'https://my-aggregator.example.com'
 * });
 */
export class UsersResource {
  private _aggregators?: AggregatorsResource;

  constructor(private readonly http: HTTPClient) {}

  /**
   * Access aggregator management operations.
   *
   * @returns AggregatorsResource for managing user's aggregator configurations
   *
   * @example
   * // List aggregators
   * const aggregators = await client.users.aggregators.list();
   * for (const agg of aggregators) {
   *   console.log(`${agg.name}: ${agg.url}`);
   * }
   *
   * // Create aggregator
   * const agg = await client.users.aggregators.create({
   *   name: 'My Aggregator',
   *   url: 'https://my-aggregator.example.com'
   * });
   *
   * // Set as default
   * await client.users.aggregators.setDefault(agg.id);
   */
  get aggregators(): AggregatorsResource {
    if (!this._aggregators) {
      this._aggregators = new AggregatorsResource(this.http);
    }
    return this._aggregators;
  }

  /**
   * Set a user's email address outright (admin only).
   *
   * Applies immediately and clears the verified flag: an administrator has not
   * proven the new address belongs to its owner, so it cannot inherit the old
   * address's verified status. The account holder re-proves it through the
   * normal OTP flow.
   *
   * Admins changing their *own* address should use `auth.requestEmailChange()`,
   * which keeps the current address working until the new one is verified.
   *
   * @param userId - The user whose address to set
   * @param email - The new email address
   * @returns The updated User
   * @throws {ValidationError} If the caller is not an admin
   * @throws {ConflictError} If another account already holds the address
   */
  async setEmail(userId: number, email: string): Promise<User> {
    return this.http.put<User>(`/api/v1/users/${String(userId)}/email`, { email });
  }

  /**
   * Update the current user's profile.
   *
   * Only provided fields will be updated. `email` is not updatable here and is
   * rejected with 422 — see `auth.requestEmailChange()`.
   *
   * @param input - Fields to update
   * @returns The updated User
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If input validation fails, or `email` is supplied
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

  /**
   * Get the current user's accounting service credentials.
   *
   * Returns credentials stored in SyftHub for connecting to an external
   * accounting service. The email is always the same as the user's SyftHub email.
   *
   * @returns Accounting credentials (url and password may be null if not configured)
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const credentials = await client.users.getAccountingCredentials();
   * if (credentials.url && credentials.password) {
   *   // Use credentials to connect to accounting service
   * }
   */
  async getAccountingCredentials(): Promise<AccountingCredentials> {
    return this.http.get<AccountingCredentials>('/api/v1/users/me/accounting');
  }
}
