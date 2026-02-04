import type { HTTPClient } from '../http.js';
import type {
  AccountingCredentials,
  HeartbeatInput,
  HeartbeatResponse,
  User,
  UserUpdateInput,
} from '../models/index.js';

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

  /**
   * Send a heartbeat to indicate this SyftAI Space is alive.
   *
   * The heartbeat mechanism allows SyftAI Spaces to signal their availability
   * to SyftHub. This should be called periodically (before the TTL expires)
   * to maintain the "active" status.
   *
   * @param input - Heartbeat parameters
   * @param input.url - Full URL of this space (e.g., "https://myspace.example.com").
   *                    The server extracts the domain from this URL.
   * @param input.ttlSeconds - Time-to-live in seconds (1-3600). The server caps this
   *                           at a maximum of 600 seconds (10 minutes). Default is 300
   *                           seconds (5 minutes).
   * @returns HeartbeatResponse containing status, expiry time, domain, and effective TTL
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If URL or TTL is invalid
   *
   * @example
   * // Send heartbeat with default TTL (300 seconds)
   * const response = await client.users.sendHeartbeat({
   *   url: 'https://myspace.example.com'
   * });
   * console.log(`Next heartbeat before: ${response.expiresAt}`);
   *
   * @example
   * // Send heartbeat with custom TTL
   * const response = await client.users.sendHeartbeat({
   *   url: 'https://myspace.example.com',
   *   ttlSeconds: 600  // Maximum allowed
   * });
   */
  async sendHeartbeat(input: HeartbeatInput): Promise<HeartbeatResponse> {
    const response = await this.http.post<{
      status: string;
      received_at: string;
      expires_at: string;
      domain: string;
      ttl_seconds: number;
    }>('/api/v1/users/me/heartbeat', {
      url: input.url,
      ttl_seconds: input.ttlSeconds ?? 300,
    });

    return {
      status: response.status,
      receivedAt: new Date(response.received_at),
      expiresAt: new Date(response.expires_at),
      domain: response.domain,
      ttlSeconds: response.ttl_seconds,
    };
  }
}
