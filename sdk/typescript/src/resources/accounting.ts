/**
 * Accounting Resource for SyftHub SDK (MPP Wallet)
 *
 * This module provides wallet management operations via the SyftHub API.
 * Payments are handled through the MPP (Micropayment Protocol) 402 flow,
 * replacing the previous external accounting service with direct wallet support.
 *
 * @example
 * ```typescript
 * // Initialize via client (after login)
 * await client.auth.login('alice', 'password');
 * await client.initAccounting();
 *
 * // Get wallet info
 * const wallet = await client.accounting.getWallet();
 * console.log(`Wallet address: ${wallet.address}`);
 *
 * // Get balance
 * const balance = await client.accounting.getBalance();
 * console.log(`Balance: ${balance.balance} ${balance.currency}`);
 *
 * // Get transactions
 * const transactions = await client.accounting.getTransactions();
 * for (const tx of transactions) {
 *   console.log(`${tx.created_at}: ${tx.amount} from ${tx.sender_email}`);
 * }
 * ```
 */

import type { HTTPClient } from '../http.js';
import type { WalletInfo, WalletBalance, WalletTransaction } from '../models/accounting.js';

// =============================================================================
// Types
// =============================================================================

/**
 * Options for creating an AccountingResource.
 *
 * @deprecated The old AccountingResourceOptions with external service credentials
 * are no longer needed. Use the HTTPClient-based constructor instead.
 */
export interface AccountingResourceOptions {
  /** @deprecated No longer used - wallet API is accessed via SyftHub */
  url: string;
  /** @deprecated No longer used */
  email: string;
  /** @deprecated No longer used */
  password: string;
  /** @deprecated No longer used */
  timeout?: number;
}

/**
 * Options for listing transactions.
 *
 * @deprecated Use getTransactions() which returns all transactions directly.
 */
export interface TransactionsOptions {
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

// =============================================================================
// AccountingResource
// =============================================================================

/**
 * Wallet and payment operations via the SyftHub API.
 *
 * Manages MPP (Micropayment Protocol) wallets for users. Payments for
 * endpoint usage are handled automatically via the 402 payment flow
 * between the aggregator and SyftAI-Space instances.
 *
 * @example
 * ```typescript
 * // Get wallet info
 * const wallet = await client.accounting.getWallet();
 * if (!wallet.exists) {
 *   // Create a new wallet
 *   const result = await client.accounting.createWallet();
 *   console.log(`Created wallet: ${result.address}`);
 * }
 *
 * // Check balance
 * const balance = await client.accounting.getBalance();
 * console.log(`Balance: ${balance.balance} ${balance.currency}`);
 * ```
 */
export class AccountingResource {
  constructor(private readonly http: HTTPClient) {}

  // ===========================================================================
  // Wallet Operations
  // ===========================================================================

  /**
   * Get the current user's wallet information.
   *
   * @returns WalletInfo with address and existence status
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * ```typescript
   * const wallet = await client.accounting.getWallet();
   * if (wallet.exists) {
   *   console.log(`Wallet address: ${wallet.address}`);
   * } else {
   *   console.log('No wallet configured');
   * }
   * ```
   */
  async getWallet(): Promise<WalletInfo> {
    return this.http.get<WalletInfo>('/api/v1/wallet/');
  }

  /**
   * Get the current user's wallet balance and recent transactions.
   *
   * @returns WalletBalance with balance, currency, and recent transactions
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * ```typescript
   * const balance = await client.accounting.getBalance();
   * console.log(`Balance: ${balance.balance} ${balance.currency}`);
   * console.log(`Wallet configured: ${balance.wallet_configured}`);
   * ```
   */
  async getBalance(): Promise<WalletBalance> {
    return this.http.get<WalletBalance>('/api/v1/wallet/balance');
  }

  /**
   * Get the current user's wallet transactions.
   *
   * @returns Array of WalletTransaction objects
   * @throws {AuthenticationError} If not authenticated
   *
   * @example
   * ```typescript
   * const transactions = await client.accounting.getTransactions();
   * for (const tx of transactions) {
   *   console.log(`${tx.created_at}: ${tx.amount} ${tx.status}`);
   * }
   * ```
   */
  async getTransactions(): Promise<WalletTransaction[]> {
    return this.http.get<WalletTransaction[]>('/api/v1/wallet/transactions');
  }

  /**
   * Create a new wallet for the current user.
   *
   * Generates a new wallet with a fresh keypair. The wallet address
   * is returned and stored on the server.
   *
   * @returns Object with the new wallet address
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If user already has a wallet
   *
   * @example
   * ```typescript
   * const result = await client.accounting.createWallet();
   * console.log(`New wallet address: ${result.address}`);
   * ```
   */
  async createWallet(): Promise<{ address: string }> {
    return this.http.post<{ address: string }>('/api/v1/wallet/create', {});
  }

  /**
   * Import an existing wallet using a private key.
   *
   * @param privateKey - The private key to import
   * @returns Object with the imported wallet address
   * @throws {AuthenticationError} If not authenticated
   * @throws {ValidationError} If the private key is invalid
   *
   * @example
   * ```typescript
   * const result = await client.accounting.importWallet('0x...');
   * console.log(`Imported wallet address: ${result.address}`);
   * ```
   */
  async importWallet(privateKey: string): Promise<{ address: string }> {
    return this.http.post<{ address: string }>('/api/v1/wallet/import', {
      private_key: privateKey,
    });
  }
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create a new AccountingResource instance.
 *
 * @deprecated Use the SyftHubClient's built-in accounting resource instead.
 * The wallet API is now accessed through the SyftHub HTTP client, not
 * a separate external service.
 *
 * @param options - Configuration options (ignored, kept for backward compatibility)
 * @returns AccountingResource instance
 */
export function createAccountingResource(options: AccountingResourceOptions): AccountingResource {
  void options;
  throw new Error(
    'createAccountingResource() is deprecated. ' +
      'The wallet API is now accessed through the SyftHubClient. ' +
      'Use client.initAccounting() after login instead.'
  );
}
