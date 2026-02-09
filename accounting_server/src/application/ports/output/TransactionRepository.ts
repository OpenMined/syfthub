/**
 * Transaction Repository Port (Output)
 *
 * Defines the interface for transaction persistence operations.
 */

import { Transaction, TransactionType, TransactionStatus } from '../../../domain/entities/Transaction';
import { LedgerEntry } from '../../../domain/entities/LedgerEntry';
import {
  TransactionId,
  AccountId,
  IdempotencyKey,
  ExternalReference,
} from '../../../domain/value-objects/Identifiers';

export interface TransactionFilters {
  accountId?: AccountId;
  type?: TransactionType[];
  status?: TransactionStatus[];
  createdAfter?: Date;
  createdBefore?: Date;
}

export interface PaginationOptions {
  limit: number;
  cursor?: string;
  sortBy?: 'created_at' | 'amount';
  sortOrder?: 'asc' | 'desc';
}

export interface PaginatedResult<T> {
  data: T[];
  pagination: {
    hasMore: boolean;
    nextCursor: string | null;
    prevCursor: string | null;
  };
}

export interface TransactionRepository {
  /**
   * Find transaction by ID
   */
  findById(id: TransactionId): Promise<Transaction | null>;

  /**
   * Find transaction by idempotency key
   * Used to detect duplicate requests
   */
  findByIdempotencyKey(key: IdempotencyKey): Promise<Transaction | null>;

  /**
   * Find transaction by external reference (provider transaction ID)
   */
  findByExternalReference(reference: ExternalReference): Promise<Transaction | null>;

  /**
   * Find transactions with filters and pagination
   */
  findWithFilters(
    filters: TransactionFilters,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<Transaction>>;

  /**
   * Find transactions for an account
   */
  findByAccountId(
    accountId: AccountId,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<Transaction>>;

  /**
   * Find child transactions (e.g., refunds of a transaction)
   */
  findByParentId(parentId: TransactionId): Promise<Transaction[]>;

  /**
   * Save a new transaction with its ledger entries
   * This should be atomic
   */
  save(transaction: Transaction): Promise<void>;

  /**
   * Update a transaction
   */
  update(transaction: Transaction): Promise<void>;

  /**
   * Save ledger entries for a transaction
   */
  saveLedgerEntries(entries: LedgerEntry[]): Promise<void>;

  /**
   * Get ledger entries for a transaction
   */
  getLedgerEntries(transactionId: TransactionId): Promise<LedgerEntry[]>;

  /**
   * Get ledger entries for an account (for balance audit)
   */
  getLedgerEntriesByAccount(
    accountId: AccountId,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<LedgerEntry>>;
}
