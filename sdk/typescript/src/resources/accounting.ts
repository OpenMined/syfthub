import type { HTTPClient } from '../http.js';
import type { AccountingBalance, AccountingTransaction } from '../models/index.js';
import { PageIterator } from '../pagination.js';

/**
 * Options for listing transactions.
 */
export interface TransactionsOptions {
  /** Number of items per page (default: 20) */
  pageSize?: number;
}

/**
 * Accounting resource for billing and credits management.
 *
 * @example
 * // Get current balance
 * const balance = await client.accounting.balance();
 * console.log(`Credits: ${balance.credits} ${balance.currency}`);
 *
 * @example
 * // List transactions
 * for await (const tx of client.accounting.transactions()) {
 *   console.log(`${tx.createdAt}: ${tx.amount} - ${tx.description}`);
 * }
 */
export class AccountingResource {
  constructor(private readonly http: HTTPClient) {}

  /**
   * Get the current account balance.
   *
   * @returns Account balance information
   * @throws {AuthenticationError} If not authenticated
   */
  async balance(): Promise<AccountingBalance> {
    return this.http.get<AccountingBalance>('/api/v1/accounting/balance');
  }

  /**
   * List account transactions.
   *
   * @param options - Pagination options
   * @returns PageIterator that lazily fetches transactions
   * @throws {AuthenticationError} If not authenticated
   */
  transactions(options?: TransactionsOptions): PageIterator<AccountingTransaction> {
    const pageSize = options?.pageSize ?? 20;

    return new PageIterator<AccountingTransaction>(async (skip, limit) => {
      return this.http.get<AccountingTransaction[]>('/api/v1/accounting/transactions', {
        skip,
        limit,
      });
    }, pageSize);
  }
}
