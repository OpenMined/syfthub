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
   * If an accounting service URL is configured (via `accountingServiceUrl` or server default),
   * the backend will handle accounting integration using a "try-create-first" approach:
   *
   * **Accounting Password Behavior:**
   * - **Not provided**: A secure password is auto-generated and a new accounting account is created.
   * - **Provided (new user)**: The account is created with your chosen password.
   * - **Provided (existing user)**: Your password is validated and accounts are linked.
   *
   * This means you can set your own accounting password during registration even if you're
   * a new user - you don't need an existing accounting account first.
   *
   * @param input - Registration details (username, email, password, fullName)
   * @returns The created User
   * @throws {ValidationError} If input validation fails
   * @throws {UserAlreadyExistsError} If username or email already exists in SyftHub
   * @throws {AccountingAccountExistsError} If email already exists in accounting service
   *         and no `accountingPassword` was provided. Retry with the password.
   * @throws {InvalidAccountingPasswordError} If the provided accounting password doesn't
   *         match an existing accounting account
   * @throws {AccountingServiceUnavailableError} If the accounting service is unreachable
   *
   * @example
   * // Basic registration (auto-generated accounting password)
   * const user = await client.auth.register({
   *   username: 'alice',
   *   email: 'alice@example.com',
   *   password: 'SecurePass123!',
   *   fullName: 'Alice'
   * });
   *
   * @example
   * // Registration with custom accounting password (NEW user)
   * const user = await client.auth.register({
   *   username: 'bob',
   *   email: 'bob@example.com',
   *   password: 'SecurePass123!',
   *   fullName: 'Bob',
   *   accountingPassword: 'MyChosenAccountingPass!'  // Creates account with this password
   * });
   *
   * @example
   * // Handle existing accounting account
   * try {
   *   await client.auth.register({ username, email, password, fullName });
   * } catch (error) {
   *   if (error instanceof AccountingAccountExistsError) {
   *     // Prompt user for their existing accounting password
   *     const accountingPassword = await promptUser('Enter your existing accounting password:');
   *     await client.auth.register({ username, email, password, fullName, accountingPassword });
   *   } else {
   *     throw error;
   *   }
   * }
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
    }>('/api/v1/auth/refresh', { refreshToken: tokens.refreshToken }, { includeAuth: false });

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

  /**
   * Get a peer token for NATS communication with tunneling spaces.
   *
   * Peer tokens are short-lived credentials that allow the aggregator to
   * communicate with tunneling SyftAI Spaces via NATS pub/sub.
   *
   * @param targetUsernames - Usernames of the tunneling spaces to communicate with
   * @returns PeerTokenResponse with token, channel, expiry, and NATS URL
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * const peer = await client.auth.getPeerToken(['alice', 'bob']);
   * console.log(`Peer channel: ${peer.peerChannel}, expires in ${peer.expiresIn}s`);
   */
  async getPeerToken(targetUsernames: string[]): Promise<PeerTokenResponse> {
    return this.http.post<PeerTokenResponse>('/api/v1/peer-token', {
      target_usernames: targetUsernames,
    });
  }

  /**
   * Get a satellite token for a specific audience (target service).
   *
   * Satellite tokens are short-lived, RS256-signed JWTs that allow satellite
   * services (like SyftAI-Space) to verify user identity without calling
   * SyftHub for every request.
   *
   * @param audience - Target service identifier (username of the service owner)
   * @returns Satellite token response with token and expiry
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If audience is invalid or inactive
   *
   * @example
   * // Get a token for querying alice's SyftAI-Space endpoints
   * const tokenResponse = await client.auth.getSatelliteToken('alice');
   * console.log(`Token expires in ${tokenResponse.expiresIn} seconds`);
   */
  async getSatelliteToken(audience: string): Promise<SatelliteTokenResponse> {
    return this.http.get<SatelliteTokenResponse>('/api/v1/token', { aud: audience });
  }

  /**
   * Get satellite tokens for multiple audiences in parallel.
   *
   * This is useful when making requests to endpoints owned by different users.
   * Tokens are cached and reused where possible.
   *
   * @param audiences - Array of unique audience identifiers (usernames)
   * @returns Map of audience to satellite token
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * // Get tokens for multiple endpoint owners
   * const tokens = await client.auth.getSatelliteTokens(['alice', 'bob']);
   * console.log(`Got ${tokens.size} tokens`);
   */
  async getSatelliteTokens(audiences: string[]): Promise<Map<string, string>> {
    const uniqueAudiences = [...new Set(audiences)];
    const tokenMap = new Map<string, string>();

    // Fetch tokens in parallel
    const results = await Promise.allSettled(
      uniqueAudiences.map(async (aud) => {
        const response = await this.getSatelliteToken(aud);
        return { audience: aud, token: response.targetToken };
      })
    );

    // Collect successful results; warn on failures so misconfigured IDPs are visible
    for (const [i, result] of results.entries()) {
      if (result.status === 'fulfilled') {
        tokenMap.set(result.value.audience, result.value.token);
      } else {
        console.warn(
          `[SyftHub] Failed to fetch satellite token for "${uniqueAudiences[i]}":`,
          result.reason
        );
      }
    }

    return tokenMap;
  }

  /**
   * Get a guest satellite token for a specific audience (target service).
   *
   * Guest tokens allow unauthenticated users to access policy-free endpoints.
   * No authentication is required to call this method.
   *
   * @param audience - Target service identifier (username of the service owner)
   * @returns Satellite token response with token and expiry
   * @throws {ValidationError} If audience is invalid or inactive
   *
   * @example
   * // Get a guest token for querying alice's policy-free endpoints
   * const tokenResponse = await client.auth.getGuestSatelliteToken('alice');
   */
  async getGuestSatelliteToken(audience: string): Promise<SatelliteTokenResponse> {
    return this.http.get<SatelliteTokenResponse>(
      '/api/v1/token/guest',
      { aud: audience },
      { includeAuth: false }
    );
  }

  /**
   * Get guest satellite tokens for multiple audiences in parallel.
   *
   * No authentication is required to call this method.
   *
   * @param audiences - Array of unique audience identifiers (usernames)
   * @returns Map of audience to satellite token
   *
   * @example
   * const tokens = await client.auth.getGuestSatelliteTokens(['alice', 'bob']);
   */
  async getGuestSatelliteTokens(audiences: string[]): Promise<Map<string, string>> {
    const uniqueAudiences = [...new Set(audiences)];
    const tokenMap = new Map<string, string>();

    const results = await Promise.allSettled(
      uniqueAudiences.map(async (aud) => {
        const response = await this.getGuestSatelliteToken(aud);
        return { audience: aud, token: response.targetToken };
      })
    );

    for (const result of results) {
      if (result.status === 'fulfilled') {
        tokenMap.set(result.value.audience, result.value.token);
      }
    }

    return tokenMap;
  }

  /**
   * Get transaction tokens for multiple endpoint owners.
   *
   * Transaction tokens are short-lived JWTs that pre-authorize the endpoint owner
   * (recipient) to charge the current user (sender) for usage. These tokens are
   * created via the accounting service and passed to the aggregator.
   *
   * This is used by the chat flow to enable billing for endpoint usage.
   *
   * @param ownerUsernames - Array of endpoint owner usernames
   * @returns TransactionTokensResponse with tokens map and any errors
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * // Get transaction tokens for endpoint owners
   * const response = await client.auth.getTransactionTokens(['alice', 'bob']);
   * console.log(`Got ${Object.keys(response.tokens).length} tokens`);
   * if (Object.keys(response.errors).length > 0) {
   *   console.log('Some tokens failed:', response.errors);
   * }
   */
  async getTransactionTokens(ownerUsernames: string[]): Promise<TransactionTokensResponse> {
    const uniqueOwners = [...new Set(ownerUsernames)];

    if (uniqueOwners.length === 0) {
      return { tokens: {}, errors: {} };
    }

    try {
      return await this.http.post<TransactionTokensResponse>(
        '/api/v1/accounting/transaction-tokens',
        { owner_usernames: uniqueOwners }
      );
    } catch (error) {
      // If accounting is not configured or fails, return empty tokens
      // The chat can proceed without transaction tokens (billing will fail later)
      console.warn('Failed to get transaction tokens:', error);
      return { tokens: {}, errors: {} };
    }
  }
}

/**
 * Response from peer token endpoint.
 */
export interface PeerTokenResponse {
  /** Short-lived token for NATS authentication */
  peerToken: string;
  /** Unique reply channel for receiving responses */
  peerChannel: string;
  /** Seconds until the token expires */
  expiresIn: number;
  /** NATS server URL for WebSocket connections */
  natsUrl: string;
}

/**
 * Response from satellite token endpoint.
 */
export interface SatelliteTokenResponse {
  /** RS256-signed JWT for the target service */
  targetToken: string;
  /** Seconds until the token expires */
  expiresIn: number;
}

/**
 * Response from transaction tokens endpoint.
 */
export interface TransactionTokensResponse {
  /** Mapping of owner_username to transaction token */
  tokens: Record<string, string>;
  /** Mapping of owner_username to error message (for failed tokens) */
  errors: Record<string, string>;
}
