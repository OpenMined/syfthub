/**
 * Accounting Resource for SyftHub SDK
 *
 * This module connects to an external accounting/billing service for managing
 * user balances and transactions. The accounting service is separate from SyftHub
 * and uses its own authentication (Basic auth with email/password).
 *
 * @example
 * ```typescript
 * // Create accounting client
 * const accounting = new AccountingResource({
 *   url: 'https://accounting.example.com',
 *   email: 'user@example.com',
 *   password: 'secret'
 * });
 *
 * // Get user balance
 * const user = await accounting.getUser();
 * console.log(`Balance: ${user.balance}`);
 *
 * // Create a transaction
 * const tx = await accounting.createTransaction({
 *   recipientEmail: 'recipient@example.com',
 *   amount: 10.0,
 *   appName: 'syftai-space',
 *   appEpPath: 'alice/my-model'
 * });
 *
 * // Confirm the transaction
 * await accounting.confirmTransaction(tx.id);
 * ```
 */

import {
  type AccountingUser,
  type Transaction,
  type TransactionResponse,
  type CreateTransactionInput,
  parseTransaction,
} from '../models/index.js';
import { PageIterator } from '../pagination.js';
import {
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  APIError,
  SyftHubError,
} from '../errors.js';

// =============================================================================
// Types
// =============================================================================

/**
 * Options for creating an AccountingResource.
 */
export interface AccountingResourceOptions {
  /** Accounting service URL */
  url: string;
  /** Email for Basic auth */
  email: string;
  /** Password for Basic auth */
  password: string;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
}

/**
 * Options for listing transactions.
 */
export interface TransactionsOptions {
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

// =============================================================================
// Error Handling
// =============================================================================

/**
 * Handle HTTP error responses from accounting service.
 */
async function handleResponseError(response: Response): Promise<void> {
  if (response.ok) return;

  let detail: string;
  try {
    const body = await response.json() as { detail?: string; message?: string };
    detail = body.detail ?? body.message ?? JSON.stringify(body);
  } catch {
    detail = (await response.text()) || `HTTP ${response.status}`;
  }

  switch (response.status) {
    case 401:
      throw new AuthenticationError(`Authentication failed: ${detail}`);
    case 403:
      throw new AuthorizationError(`Permission denied: ${detail}`);
    case 404:
      throw new NotFoundError(`Not found: ${detail}`);
    case 422:
      throw new ValidationError(`Validation error: ${detail}`);
    default:
      throw new APIError(`Accounting API error: ${detail}`, response.status);
  }
}

/**
 * Create Basic auth header value.
 */
function createBasicAuth(email: string, password: string): string {
  const credentials = `${email}:${password}`;
  // Use btoa for browser, Buffer for Node.js
  const encoded = typeof btoa !== 'undefined'
    ? btoa(credentials)
    : Buffer.from(credentials).toString('base64');
  return `Basic ${encoded}`;
}

// =============================================================================
// AccountingResource
// =============================================================================

/**
 * Handle accounting/billing operations with external service.
 *
 * The accounting service manages user balances and transactions. It uses
 * Basic auth (email/password) for authentication, which is separate from
 * SyftHub's JWT-based authentication.
 *
 * Transaction Workflow:
 * 1. Sender creates transaction (status=PENDING)
 * 2. Either party confirms (status=COMPLETED) or cancels (status=CANCELLED)
 *
 * Delegated Transaction Workflow:
 * 1. Sender creates a transaction token for recipient
 * 2. Recipient uses token to create delegated transaction
 * 3. Recipient confirms the transaction
 */
export class AccountingResource {
  private readonly baseUrl: string;
  private readonly email: string;
  private readonly password: string;
  private readonly timeout: number;
  private readonly authHeader: string;

  constructor(options: AccountingResourceOptions) {
    this.baseUrl = options.url.replace(/\/$/, ''); // Remove trailing slash
    this.email = options.email;
    this.password = options.password;
    this.timeout = options.timeout ?? 30000;
    this.authHeader = createBasicAuth(this.email, this.password);
  }

  // ===========================================================================
  // Private HTTP Methods
  // ===========================================================================

  /**
   * Make an authenticated request to the accounting service.
   */
  private async request<T>(
    method: string,
    path: string,
    options?: {
      body?: Record<string, unknown>;
      params?: Record<string, string | number>;
    }
  ): Promise<T> {
    const url = new URL(path, this.baseUrl);

    if (options?.params) {
      for (const [key, value] of Object.entries(options.params)) {
        url.searchParams.set(key, String(value));
      }
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url.toString(), {
        method,
        headers: {
          'Authorization': this.authHeader,
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: options?.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });

      await handleResponseError(response);

      if (response.status === 204) {
        return {} as T;
      }

      return await response.json() as T;
    } catch (error) {
      if (error instanceof SyftHubError) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw new APIError('Request timeout', 408);
      }
      throw new APIError(`Accounting request failed: ${error instanceof Error ? error.message : 'Unknown error'}`, 0);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Make a request using Bearer token auth (for delegated transactions).
   */
  private async requestWithToken<T>(
    method: string,
    path: string,
    token: string,
    options?: {
      body?: Record<string, unknown>;
    }
  ): Promise<T> {
    const url = new URL(path, this.baseUrl);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url.toString(), {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: options?.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });

      await handleResponseError(response);

      if (response.status === 204) {
        return {} as T;
      }

      return await response.json() as T;
    } catch (error) {
      if (error instanceof SyftHubError) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw new APIError('Request timeout', 408);
      }
      throw new APIError(`Accounting request failed: ${error instanceof Error ? error.message : 'Unknown error'}`, 0);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // ===========================================================================
  // User Operations
  // ===========================================================================

  /**
   * Get the current user's account information including balance.
   *
   * @returns AccountingUser with id, email, balance, and organization
   * @throws {AuthenticationError} If authentication fails
   * @throws {APIError} On other errors
   *
   * @example
   * ```typescript
   * const user = await accounting.getUser();
   * console.log(`Balance: ${user.balance}`);
   * console.log(`Organization: ${user.organization}`);
   * ```
   */
  async getUser(): Promise<AccountingUser> {
    return this.request<AccountingUser>('GET', '/user');
  }

  /**
   * Update the user's password.
   *
   * @param currentPassword - Current password for verification
   * @param newPassword - New password to set
   * @throws {AuthenticationError} If current password is wrong
   * @throws {ValidationError} If new password doesn't meet requirements
   *
   * @example
   * ```typescript
   * await accounting.updatePassword('old_secret', 'new_secret');
   * ```
   */
  async updatePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.request<void>('PUT', '/user/password', {
      body: {
        oldPassword: currentPassword,
        newPassword: newPassword,
      },
    });
  }

  /**
   * Update the user's organization.
   *
   * @param organization - New organization name
   * @throws {AuthenticationError} If authentication fails
   *
   * @example
   * ```typescript
   * await accounting.updateOrganization('OpenMined');
   * ```
   */
  async updateOrganization(organization: string): Promise<void> {
    await this.request<void>('PUT', '/user/organization', {
      body: { organization },
    });
  }

  // ===========================================================================
  // Transaction Listing
  // ===========================================================================

  /**
   * List account transactions with pagination.
   *
   * Returns a lazy iterator that fetches pages on demand.
   *
   * @param options - Pagination options
   * @returns PageIterator that yields Transaction objects
   *
   * @example
   * ```typescript
   * // Iterate through all transactions
   * for await (const tx of accounting.getTransactions()) {
   *   console.log(`${tx.createdAt}: ${tx.amount} from ${tx.senderEmail}`);
   * }
   *
   * // Get first page only
   * const firstPage = await accounting.getTransactions().firstPage();
   *
   * // Get all transactions
   * const allTxs = await accounting.getTransactions().all();
   * ```
   */
  getTransactions(options?: TransactionsOptions): PageIterator<Transaction> {
    const pageSize = options?.pageSize ?? 20;

    return new PageIterator<Transaction>(
      async (skip, limit) => {
        const response = await this.request<TransactionResponse[]>('GET', '/transactions', {
          params: { skip, limit },
        });
        return response.map(parseTransaction);
      },
      pageSize
    );
  }

  /**
   * Get a specific transaction by ID.
   *
   * @param transactionId - The transaction ID
   * @returns Transaction object
   * @throws {NotFoundError} If transaction not found
   *
   * @example
   * ```typescript
   * const tx = await accounting.getTransaction('tx_123');
   * console.log(`Status: ${tx.status}`);
   * ```
   */
  async getTransaction(transactionId: string): Promise<Transaction> {
    const response = await this.request<TransactionResponse>(
      'GET',
      `/transactions/${transactionId}`
    );
    return parseTransaction(response);
  }

  // ===========================================================================
  // Direct Transaction Operations
  // ===========================================================================

  /**
   * Create a new transaction (direct transfer).
   *
   * Creates a PENDING transaction that must be confirmed or cancelled.
   * The transaction is created by the sender (current user).
   *
   * @param input - Transaction details
   * @returns Transaction in PENDING status
   * @throws {ValidationError} If amount <= 0 or insufficient balance
   *
   * @example
   * ```typescript
   * const tx = await accounting.createTransaction({
   *   recipientEmail: 'bob@example.com',
   *   amount: 10.0,
   *   appName: 'syftai-space',
   *   appEpPath: 'alice/my-model'
   * });
   * console.log(`Created transaction ${tx.id}: ${tx.status}`);
   *
   * // Later, confirm or cancel
   * await accounting.confirmTransaction(tx.id);
   * ```
   */
  async createTransaction(input: CreateTransactionInput): Promise<Transaction> {
    if (input.amount <= 0) {
      throw new ValidationError('Amount must be greater than 0');
    }

    const response = await this.request<TransactionResponse>('POST', '/transactions', {
      body: {
        recipientEmail: input.recipientEmail,
        amount: input.amount,
        ...(input.appName && { appName: input.appName }),
        ...(input.appEpPath && { appEpPath: input.appEpPath }),
      },
    });

    return parseTransaction(response);
  }

  /**
   * Confirm a pending transaction.
   *
   * Confirms the transaction, transferring funds from sender to recipient.
   * Can be called by either the sender or recipient.
   *
   * @param transactionId - The transaction ID to confirm
   * @returns Transaction in COMPLETED status
   * @throws {NotFoundError} If transaction not found
   * @throws {ValidationError} If transaction is not in PENDING status
   *
   * @example
   * ```typescript
   * const tx = await accounting.confirmTransaction('tx_123');
   * console.log(`Confirmed: ${tx.status}`); // "completed"
   * ```
   */
  async confirmTransaction(transactionId: string): Promise<Transaction> {
    const response = await this.request<TransactionResponse>(
      'POST',
      `/transactions/${transactionId}/confirm`
    );
    return parseTransaction(response);
  }

  /**
   * Cancel a pending transaction.
   *
   * Cancels the transaction without transferring funds.
   * Can be called by either the sender or recipient.
   *
   * @param transactionId - The transaction ID to cancel
   * @returns Transaction in CANCELLED status
   * @throws {NotFoundError} If transaction not found
   * @throws {ValidationError} If transaction is not in PENDING status
   *
   * @example
   * ```typescript
   * const tx = await accounting.cancelTransaction('tx_123');
   * console.log(`Cancelled: ${tx.status}`); // "cancelled"
   * ```
   */
  async cancelTransaction(transactionId: string): Promise<Transaction> {
    const response = await this.request<TransactionResponse>(
      'POST',
      `/transactions/${transactionId}/cancel`
    );
    return parseTransaction(response);
  }

  // ===========================================================================
  // Delegated Transaction Operations
  // ===========================================================================

  /**
   * Create a transaction token for delegated transfers.
   *
   * Creates a JWT token that authorizes the recipient to create a
   * transaction on behalf of the sender (current user). The token
   * is short-lived (typically ~5 minutes).
   *
   * Use this when you want to pre-authorize a payment that will be
   * initiated by the recipient (e.g., a service charging for usage).
   *
   * @param recipientEmail - Email of the authorized recipient
   * @returns JWT token string to share with recipient
   *
   * @example
   * ```typescript
   * // Sender creates token
   * const token = await accounting.createTransactionToken('service@example.com');
   *
   * // Share token with recipient out-of-band
   * // Recipient uses token to create delegated transaction
   * ```
   */
  async createTransactionToken(recipientEmail: string): Promise<string> {
    const response = await this.request<{ token: string }>('POST', '/token/create', {
      body: { recipientEmail },
    });
    return response.token;
  }

  /**
   * Create a delegated transaction using a pre-authorized token.
   *
   * Creates a transaction on behalf of the sender using their token.
   * This is typically used by services to charge users for usage.
   *
   * The token authenticates the request instead of Basic auth.
   *
   * @param senderEmail - Email of the sender who created the token
   * @param amount - Amount to transfer (must be > 0)
   * @param token - JWT token from sender's createTransactionToken()
   * @returns Transaction in PENDING status (createdBy=RECIPIENT)
   * @throws {AuthenticationError} If token is invalid or expired
   * @throws {ValidationError} If amount <= 0
   *
   * @example
   * ```typescript
   * // Recipient creates transaction using sender's token
   * const tx = await accounting.createDelegatedTransaction(
   *   'alice@example.com',
   *   5.0,
   *   aliceToken
   * );
   *
   * // Recipient confirms the transaction
   * await accounting.confirmTransaction(tx.id);
   * ```
   */
  async createDelegatedTransaction(
    senderEmail: string,
    amount: number,
    token: string
  ): Promise<Transaction> {
    if (amount <= 0) {
      throw new ValidationError('Amount must be greater than 0');
    }

    const response = await this.requestWithToken<TransactionResponse>(
      'POST',
      '/transactions',
      token,
      {
        body: {
          senderEmail,
          amount,
        },
      }
    );

    return parseTransaction(response);
  }
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create a new AccountingResource instance.
 *
 * @param options - Configuration options
 * @returns AccountingResource instance
 *
 * @example
 * ```typescript
 * const accounting = createAccountingResource({
 *   url: process.env.ACCOUNTING_URL!,
 *   email: process.env.ACCOUNTING_EMAIL!,
 *   password: process.env.ACCOUNTING_PASSWORD!
 * });
 * ```
 */
export function createAccountingResource(
  options: AccountingResourceOptions
): AccountingResource {
  return new AccountingResource(options);
}
