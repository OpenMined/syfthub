import type { HTTPClient } from '../http.js';
import type { User, UserRegisterInput } from '../models/index.js';
import { AuthenticationError } from '../errors.js';

/**
 * Response from login/register endpoints.
 */
interface AuthResponse {
  user: User;
  accessToken: string;
  refreshToken: string;
  tokenType: string;
}

/**
 * Authentication resource for login, register, and session management.
 *
 * @example
 * // Register a new user
 * const user = await client.auth.register({
 *   username: 'alice',
 *   email: 'alice@example.com',
 *   password: 'SecurePass123!',
 *   fullName: 'Alice'
 * });
 *
 * @example
 * // Login
 * const user = await client.auth.login('alice', 'SecurePass123!');
 *
 * @example
 * // Get current user
 * const me = await client.auth.me();
 *
 * @example
 * // Logout
 * await client.auth.logout();
 */
export class AuthResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Register a new user account.
   *
   * @param input - Registration details (username, email, password, fullName)
   * @returns The created User
   * @throws {ValidationError} If input validation fails
   */
  async register(input: UserRegisterInput): Promise<User> {
    const response = await this.http.post<AuthResponse>('/api/v1/auth/register', input, {
      includeAuth: false,
    });

    // Store tokens in HTTP client
    this.http.setTokens(response.accessToken, response.refreshToken);

    return response.user;
  }

  /**
   * Login with username/email and password.
   *
   * Uses OAuth2 password flow (form-urlencoded body).
   *
   * @param username - Username or email
   * @param password - Password
   * @returns The authenticated User
   * @throws {AuthenticationError} If credentials are invalid
   */
  async login(username: string, password: string): Promise<User> {
    const response = await this.http.post<AuthResponse>(
      '/api/v1/auth/login',
      { username, password },
      {
        includeAuth: false,
        isFormData: true,
      }
    );

    // Store tokens in HTTP client
    this.http.setTokens(response.accessToken, response.refreshToken);

    return response.user;
  }

  /**
   * Logout the current user.
   *
   * Invalidates tokens on the server and clears local token storage.
   */
  async logout(): Promise<void> {
    try {
      await this.http.post<void>('/api/v1/auth/logout');
    } finally {
      // Always clear tokens, even if the API call fails
      this.http.clearTokens();
    }
  }

  /**
   * Get the current authenticated user.
   *
   * @returns The current User
   * @throws {AuthenticationError} If not authenticated
   */
  async me(): Promise<User> {
    return this.http.get<User>('/api/v1/auth/me');
  }

  /**
   * Manually refresh the access token.
   *
   * This is normally handled automatically when a request returns 401.
   *
   * @throws {AuthenticationError} If refresh token is invalid or expired
   */
  async refresh(): Promise<void> {
    const tokens = this.http.getTokens();
    if (!tokens) {
      throw new AuthenticationError('No refresh token available');
    }

    const response = await this.http.post<{
      accessToken: string;
      refreshToken: string;
    }>(
      '/api/v1/auth/refresh',
      { refreshToken: tokens.refreshToken },
      { includeAuth: false }
    );

    this.http.setTokens(response.accessToken, response.refreshToken);
  }

  /**
   * Change the current user's password.
   *
   * @param currentPassword - Current password for verification
   * @param newPassword - New password to set
   * @throws {AuthenticationError} If current password is incorrect
   * @throws {ValidationError} If new password doesn't meet requirements
   */
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.http.put<void>('/api/v1/auth/me/password', {
      currentPassword,
      newPassword,
    });
  }
}
