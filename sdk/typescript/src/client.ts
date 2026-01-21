import { HTTPClient, type AuthTokens } from './http.js';
import { AuthenticationError, ConfigurationError, SyftHubError } from './errors.js';
import { AuthResource } from './resources/auth.js';
import { UsersResource } from './resources/users.js';
import { MyEndpointsResource } from './resources/my-endpoints.js';
import { HubResource } from './resources/hub.js';
import { AccountingResource } from './resources/accounting.js';
import { ChatResource } from './resources/chat.js';
import { SyftAIResource } from './resources/syftai.js';

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
   * Base URL for the aggregator service (optional).
   * Falls back to SYFTHUB_AGGREGATOR_URL environment variable.
   * Defaults to {baseUrl}/aggregator/api/v1
   */
  aggregatorUrl?: string;
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
  private readonly aggregatorUrl: string;

  // Lazy-initialized resources
  private _auth?: AuthResource;
  private _users?: UsersResource;
  private _myEndpoints?: MyEndpointsResource;
  private _hub?: HubResource;
  private _accounting?: AccountingResource;
  private _accountingInitPromise: Promise<AccountingResource> | null = null;
  private _chat?: ChatResource;
  private _syftai?: SyftAIResource;

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

    // Resolve aggregator URL (default to {baseUrl}/aggregator/api/v1)
    this.aggregatorUrl =
      options.aggregatorUrl ??
      getEnv('SYFTHUB_AGGREGATOR_URL') ??
      `${normalizedUrl}/aggregator/api/v1`;
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
   * Credentials are automatically retrieved from the backend after login.
   * You must call `initAccounting()` after login to initialize this resource.
   *
   * @throws {AuthenticationError} If not initialized
   *
   * @example
   * // Login first, then initialize accounting
   * await client.auth.login('alice', 'password');
   * await client.initAccounting();
   *
   * // Now accounting is available
   * const user = await client.accounting.getUser();
   */
  get accounting(): AccountingResource {
    if (this._accounting) {
      return this._accounting;
    }

    throw new AuthenticationError(
      'Accounting not initialized. ' +
      'Call `await client.initAccounting()` after login.'
    );
  }

  /**
   * Initialize accounting resource by fetching credentials from the backend.
   *
   * This method retrieves accounting credentials from the SyftHub backend
   * and initializes the accounting resource. Requires authentication.
   *
   * @returns The initialized AccountingResource
   * @throws {AuthenticationError} If not authenticated
   * @throws {ConfigurationError} If user has no accounting service configured
   *
   * @example
   * // Login first, then initialize accounting
   * await client.auth.login('alice', 'password');
   * await client.initAccounting();
   *
   * // Now accounting is available
   * const user = await client.accounting.getUser();
   */
  async initAccounting(): Promise<AccountingResource> {
    // Return cached instance
    if (this._accounting) {
      return this._accounting;
    }

    // Prevent concurrent initialization
    if (this._accountingInitPromise) {
      return this._accountingInitPromise;
    }

    this._accountingInitPromise = this._doInitAccounting();

    try {
      this._accounting = await this._accountingInitPromise;
      return this._accounting;
    } finally {
      this._accountingInitPromise = null;
    }
  }

  /**
   * Internal method to perform accounting initialization.
   */
  private async _doInitAccounting(): Promise<AccountingResource> {
    if (!this.isAuthenticated) {
      throw new AuthenticationError(
        'Must be logged in to use accounting. ' +
        'Call client.auth.login() first.'
      );
    }

    // Fetch credentials from backend
    const creds = await this.users.getAccountingCredentials();

    if (!creds.url) {
      throw new ConfigurationError(
        'No accounting service configured for this user. ' +
        'Contact your administrator to set up accounting.'
      );
    }

    if (!creds.password) {
      throw new ConfigurationError(
        'Accounting password not available. ' +
        'This may indicate an issue with your account setup.'
      );
    }

    return new AccountingResource({
      url: creds.url,
      email: creds.email,
      password: creds.password,
      timeout: this.options.timeout,
    });
  }

  /**
   * Chat resource for RAG-augmented conversations via the Aggregator.
   *
   * This resource provides high-level chat functionality that integrates
   * with the SyftHub Aggregator service for RAG workflows.
   *
   * @example
   * // Simple chat completion
   * const response = await client.chat.complete({
   *   prompt: 'What is machine learning?',
   *   model: 'alice/gpt-model',
   *   dataSources: ['bob/ml-docs'],
   * });
   * console.log(response.response);
   *
   * // Streaming chat
   * for await (const event of client.chat.stream(options)) {
   *   if (event.type === 'token') {
   *     process.stdout.write(event.content);
   *   }
   * }
   *
   * // Get available endpoints
   * const models = await client.chat.getAvailableModels();
   * const sources = await client.chat.getAvailableDataSources();
   */
  get chat(): ChatResource {
    if (!this._chat) {
      this._chat = new ChatResource(
        this.hub,
        this.auth,
        this.aggregatorUrl
      );
    }
    return this._chat;
  }

  /**
   * SyftAI-Space resource for direct endpoint queries (low-level API).
   *
   * This resource provides direct access to SyftAI-Space endpoints without
   * going through the aggregator. Use this when you need custom RAG pipelines
   * or fine-grained control over queries.
   *
   * For most use cases, prefer the higher-level `client.chat` API instead.
   *
   * @example
   * // Query a data source directly
   * const docs = await client.syftai.queryDataSource({
   *   endpoint: { url: 'http://syftai:8080', slug: 'docs' },
   *   query: 'What is Python?',
   *   userEmail: 'alice@example.com',
   * });
   *
   * // Query a model directly
   * const response = await client.syftai.queryModel({
   *   endpoint: { url: 'http://syftai:8080', slug: 'gpt-model' },
   *   messages: [{ role: 'user', content: 'Hello!' }],
   *   userEmail: 'alice@example.com',
   * });
   */
  get syftai(): SyftAIResource {
    if (!this._syftai) {
      this._syftai = new SyftAIResource();
    }
    return this._syftai;
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
   * Check if accounting has been initialized.
   *
   * Use this to check if accounting is available before accessing
   * the `accounting` property, which will throw if not initialized.
   *
   * @returns True if accounting has been initialized via `initAccounting()`
   *
   * @example
   * if (client.isAccountingInitialized) {
   *   const user = await client.accounting.getUser();
   * }
   */
  get isAccountingInitialized(): boolean {
    return this._accounting !== undefined && this._accounting !== null;
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
