import { HTTPClient, type AuthTokens } from './http.js';
import { SyftHubError } from './errors.js';
import { AuthResource } from './resources/auth.js';
import { UsersResource } from './resources/users.js';
import { MyEndpointsResource } from './resources/my-endpoints.js';
import { HubResource } from './resources/hub.js';
import { AccountingResource } from './resources/accounting.js';

/**
 * Configuration options for SyftHubClient.
 */
export interface SyftHubClientOptions {
  /**
   * Base URL for the SyftHub API.
   * Falls back to SYFTHUB_URL environment variable.
   * @example 'https://hub.syft.com'
   */
  baseUrl?: string;

  /**
   * Request timeout in milliseconds.
   * @default 30000
   */
  timeout?: number;

  /**
   * Base URL for the accounting service (optional).
   * Falls back to SYFTHUB_ACCOUNTING_URL environment variable.
   */
  accountingUrl?: string;

  /**
   * Email for accounting service authentication (optional).
   * Falls back to SYFTHUB_ACCOUNTING_EMAIL environment variable.
   */
  accountingEmail?: string;

  /**
   * Password for accounting service authentication (optional).
   * Falls back to SYFTHUB_ACCOUNTING_PASSWORD environment variable.
   */
  accountingPassword?: string;
}

/**
 * Get environment variable, handling both Node.js and browser environments.
 */
function getEnv(key: string): string | undefined {
  if (typeof process !== 'undefined' && process.env) {
    return process.env[key];
  }
  return undefined;
}

/**
 * Check if running in a browser environment.
 */
function isBrowser(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  return typeof globalThis !== 'undefined' &&
         typeof (globalThis as { window?: unknown }).window !== 'undefined' &&
         typeof (globalThis as { document?: unknown }).document !== 'undefined';
}

/**
 * SyftHub SDK client for interacting with the SyftHub API.
 *
 * @example
 * // Basic usage
 * import { SyftHubClient } from '@syfthub/sdk';
 *
 * const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });
 *
 * // Or use environment variable
 * // Set SYFTHUB_URL=https://hub.syft.com
 * const client = new SyftHubClient();
 *
 * @example
 * // Authentication
 * const user = await client.auth.login('alice', 'password123');
 * console.log(`Logged in as ${user.username}`);
 *
 * // Get current user
 * const me = await client.auth.me();
 *
 * @example
 * // Browse endpoints
 * for await (const endpoint of client.hub.browse()) {
 *   console.log(endpoint.name);
 * }
 *
 * @example
 * // Manage your endpoints
 * const endpoint = await client.myEndpoints.create({
 *   name: 'My Model',
 *   type: 'model',
 *   visibility: 'public',
 * });
 *
 * @example
 * // Token persistence
 * const tokens = client.getTokens();
 * // Save tokens to storage...
 *
 * // Later, restore tokens
 * client.setTokens(savedTokens);
 */
export class SyftHubClient {
  private readonly http: HTTPClient;
  private readonly options: SyftHubClientOptions;

  // Lazy-initialized resources
  private _auth?: AuthResource;
  private _users?: UsersResource;
  private _myEndpoints?: MyEndpointsResource;
  private _hub?: HubResource;
  private _accounting?: AccountingResource;

  /**
   * Create a new SyftHub client.
   *
   * @param options - Configuration options
   * @throws {SyftHubError} If baseUrl is not provided and SYFTHUB_URL is not set (in non-browser environments)
   */
  constructor(options: SyftHubClientOptions = {}) {
    this.options = options;
    let baseUrl = options.baseUrl ?? getEnv('SYFTHUB_URL');

    // In browser environments, empty baseUrl means same-origin requests
    // This is valid and commonly used when the API is served from the same domain
    if (!baseUrl && !isBrowser()) {
      throw new SyftHubError(
        'baseUrl is required. Provide it in options or set the SYFTHUB_URL environment variable.'
      );
    }

    // Default to empty string for same-origin browser requests
    baseUrl = baseUrl ?? '';

    // Remove trailing slash from base URL (only if not empty)
    const normalizedUrl = baseUrl ? baseUrl.replace(/\/+$/, '') : '';

    this.http = new HTTPClient(normalizedUrl, options.timeout ?? 30000);
  }

  /**
   * Authentication resource for login, register, and session management.
   *
   * @example
   * const user = await client.auth.login('alice', 'password');
   * await client.auth.logout();
   */
  get auth(): AuthResource {
    if (!this._auth) {
      this._auth = new AuthResource(this.http);
    }
    return this._auth;
  }

  /**
   * Users resource for profile management.
   *
   * @example
   * const user = await client.users.update({ fullName: 'Alice Smith' });
   * const available = await client.users.checkUsername('newname');
   */
  get users(): UsersResource {
    if (!this._users) {
      this._users = new UsersResource(this.http);
    }
    return this._users;
  }

  /**
   * My Endpoints resource for managing your own endpoints.
   *
   * @example
   * const endpoints = await client.myEndpoints.list().all();
   * const endpoint = await client.myEndpoints.create({ name: 'My API', type: 'model' });
   */
  get myEndpoints(): MyEndpointsResource {
    if (!this._myEndpoints) {
      this._myEndpoints = new MyEndpointsResource(this.http);
    }
    return this._myEndpoints;
  }

  /**
   * Hub resource for browsing public endpoints.
   *
   * @example
   * for await (const endpoint of client.hub.browse()) {
   *   console.log(endpoint.name);
   * }
   */
  get hub(): HubResource {
    if (!this._hub) {
      this._hub = new HubResource(this.http);
    }
    return this._hub;
  }

  /**
   * Accounting resource for billing and transactions.
   *
   * The accounting service is external and uses separate credentials
   * (email/password Basic auth) from SyftHub's JWT authentication.
   *
   * Credentials can be provided via:
   * - Constructor options: accountingUrl, accountingEmail, accountingPassword
   * - Environment variables: SYFTHUB_ACCOUNTING_URL, SYFTHUB_ACCOUNTING_EMAIL, SYFTHUB_ACCOUNTING_PASSWORD
   *
   * @throws {SyftHubError} If accounting credentials are not configured
   *
   * @example
   * const user = await client.accounting.getUser();
   * console.log(`Balance: ${user.balance}`);
   *
   * // Create a transaction
   * const tx = await client.accounting.createTransaction({
   *   recipientEmail: 'bob@example.com',
   *   amount: 10.0
   * });
   */
  get accounting(): AccountingResource {
    if (!this._accounting) {
      const url = this.options.accountingUrl ?? getEnv('SYFTHUB_ACCOUNTING_URL');
      const email = this.options.accountingEmail ?? getEnv('SYFTHUB_ACCOUNTING_EMAIL');
      const password = this.options.accountingPassword ?? getEnv('SYFTHUB_ACCOUNTING_PASSWORD');

      if (!url || !email || !password) {
        throw new SyftHubError(
          'Accounting credentials not configured. Provide accountingUrl, accountingEmail, and accountingPassword ' +
          'in options or set SYFTHUB_ACCOUNTING_URL, SYFTHUB_ACCOUNTING_EMAIL, and SYFTHUB_ACCOUNTING_PASSWORD ' +
          'environment variables.'
        );
      }

      this._accounting = new AccountingResource({
        url,
        email,
        password,
        timeout: this.options.timeout,
      });
    }
    return this._accounting;
  }

  /**
   * Get current authentication tokens.
   *
   * Use this to persist tokens for later sessions.
   *
   * @returns Current tokens or null if not authenticated
   *
   * @example
   * const tokens = client.getTokens();
   * if (tokens) {
   *   localStorage.setItem('tokens', JSON.stringify(tokens));
   * }
   */
  getTokens(): AuthTokens | null {
    return this.http.getTokens();
  }

  /**
   * Set authentication tokens.
   *
   * Use this to restore a session from previously saved tokens.
   *
   * @param tokens - Tokens to set
   *
   * @example
   * const saved = JSON.parse(localStorage.getItem('tokens'));
   * if (saved) {
   *   client.setTokens(saved);
   * }
   */
  setTokens(tokens: AuthTokens): void {
    this.http.setTokens(tokens.accessToken, tokens.refreshToken);
  }

  /**
   * Check if the client is currently authenticated.
   *
   * @returns True if tokens are present
   */
  get isAuthenticated(): boolean {
    return this.http.hasTokens();
  }

  /**
   * Close the client and clean up resources.
   *
   * Currently a no-op, but may be used in future for connection pooling.
   */
  close(): void {
    // Currently a no-op
    // Could be used for cleanup in future (e.g., connection pools)
  }
}
