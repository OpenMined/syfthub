/**
 * PostgreSQL Transaction Repository
 *
 * Implements the TransactionRepository port using PostgreSQL.
 */

import { Pool, PoolClient } from 'pg';
import {
  Transaction,
  TransactionType,
  TransactionStatus,
  ProviderCode,
} from '../../domain/entities/Transaction';
import { LedgerEntry, EntryType } from '../../domain/entities/LedgerEntry';
import { Money } from '../../domain/value-objects/Money';
import {
  TransactionId,
  AccountId,
  IdempotencyKey,
  LedgerEntryId,
  ExternalReference,
} from '../../domain/value-objects/Identifiers';
import {
  TransactionRepository,
  TransactionFilters,
  PaginationOptions,
  PaginatedResult,
} from '../../application/ports/output/TransactionRepository';

interface TransactionRow {
  id: string;
  idempotency_key: string;
  type: TransactionType;
  status: TransactionStatus;
  source_account_id: string | null;
  destination_account_id: string | null;
  amount: string;
  fee: string;
  currency: string;
  external_reference: string | null;
  provider_code: ProviderCode | null;
  description: string | null;
  metadata: Record<string, unknown>;
  error_details: Record<string, unknown> | null;
  parent_transaction_id: string | null;
  confirmation_token: string | null;
  confirmation_expires_at: Date | null;
  created_at: Date;
  completed_at: Date | null;
}

interface LedgerEntryRow {
  id: string;
  transaction_id: string;
  account_id: string;
  entry_type: EntryType;
  amount: string;
  balance_after: string;
  created_at: Date;
}

export class PostgresTransactionRepository implements TransactionRepository {
  constructor(
    private pool: Pool,
    private client?: PoolClient
  ) {}

  withClient(client: PoolClient): PostgresTransactionRepository {
    return new PostgresTransactionRepository(this.pool, client);
  }

  private get db(): Pool | PoolClient {
    return this.client ?? this.pool;
  }

  async findById(id: TransactionId): Promise<Transaction | null> {
    const result = await this.db.query<TransactionRow>(
      `SELECT * FROM transactions WHERE id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return null;
    }

    const entries = await this.getLedgerEntries(id);
    return this.mapRowToTransaction(result.rows[0]!, entries);
  }

  async findByIdempotencyKey(key: IdempotencyKey): Promise<Transaction | null> {
    const result = await this.db.query<TransactionRow>(
      `SELECT * FROM transactions WHERE idempotency_key = $1`,
      [key]
    );

    if (result.rows.length === 0) {
      return null;
    }

    const id = TransactionId.from(result.rows[0]!.id);
    const entries = await this.getLedgerEntries(id);
    return this.mapRowToTransaction(result.rows[0]!, entries);
  }

  async findByExternalReference(reference: ExternalReference): Promise<Transaction | null> {
    const result = await this.db.query<TransactionRow>(
      `SELECT * FROM transactions WHERE external_reference = $1`,
      [reference]
    );

    if (result.rows.length === 0) {
      return null;
    }

    const id = TransactionId.from(result.rows[0]!.id);
    const entries = await this.getLedgerEntries(id);
    return this.mapRowToTransaction(result.rows[0]!, entries);
  }

  async findWithFilters(
    filters: TransactionFilters,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<Transaction>> {
    const conditions: string[] = [];
    const params: unknown[] = [];
    let paramIndex = 1;

    // Build WHERE conditions
    if (filters.accountId) {
      conditions.push(
        `(source_account_id = $${paramIndex} OR destination_account_id = $${paramIndex})`
      );
      params.push(filters.accountId);
      paramIndex++;
    }

    if (filters.type && filters.type.length > 0) {
      const placeholders = filters.type.map(() => `$${paramIndex++}`).join(', ');
      conditions.push(`type IN (${placeholders})`);
      params.push(...filters.type);
    }

    if (filters.status && filters.status.length > 0) {
      const placeholders = filters.status.map(() => `$${paramIndex++}`).join(', ');
      conditions.push(`status IN (${placeholders})`);
      params.push(...filters.status);
    }

    if (filters.createdAfter) {
      conditions.push(`created_at >= $${paramIndex++}`);
      params.push(filters.createdAfter);
    }

    if (filters.createdBefore) {
      conditions.push(`created_at <= $${paramIndex++}`);
      params.push(filters.createdBefore);
    }

    // Handle cursor pagination
    if (pagination.cursor) {
      const cursor = this.decodeCursor(pagination.cursor);
      const op = pagination.sortOrder === 'asc' ? '>' : '<';
      conditions.push(`(created_at, id) ${op} ($${paramIndex++}, $${paramIndex++})`);
      params.push(cursor.createdAt, cursor.id);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    // Sort order
    const sortOrder = pagination.sortOrder === 'asc' ? 'ASC' : 'DESC';
    const orderClause = `ORDER BY created_at ${sortOrder}, id ${sortOrder}`;

    // Limit + 1 to check if there are more results
    const limit = pagination.limit + 1;
    params.push(limit);

    const query = `
      SELECT * FROM transactions
      ${whereClause}
      ${orderClause}
      LIMIT $${paramIndex}
    `;

    const result = await this.db.query<TransactionRow>(query, params);

    const hasMore = result.rows.length > pagination.limit;
    const rows = hasMore ? result.rows.slice(0, -1) : result.rows;

    // Map rows to transactions (without entries for list queries)
    const transactions = rows.map((row) => this.mapRowToTransaction(row, []));

    // Build cursors
    let nextCursor: string | null = null;
    if (hasMore && rows.length > 0) {
      const lastRow = rows[rows.length - 1]!;
      nextCursor = this.encodeCursor({
        id: lastRow.id,
        createdAt: lastRow.created_at,
      });
    }

    return {
      data: transactions,
      pagination: {
        hasMore,
        nextCursor,
        prevCursor: null, // Could implement bi-directional pagination if needed
      },
    };
  }

  async findByAccountId(
    accountId: AccountId,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<Transaction>> {
    return this.findWithFilters({ accountId }, pagination);
  }

  async findByParentId(parentId: TransactionId): Promise<Transaction[]> {
    const result = await this.db.query<TransactionRow>(
      `SELECT * FROM transactions WHERE parent_transaction_id = $1 ORDER BY created_at`,
      [parentId]
    );

    return Promise.all(
      result.rows.map(async (row) => {
        const entries = await this.getLedgerEntries(TransactionId.from(row.id));
        return this.mapRowToTransaction(row, entries);
      })
    );
  }

  async save(transaction: Transaction): Promise<void> {
    const data = transaction.toJSON();

    await this.db.query(
      `INSERT INTO transactions (
        id, idempotency_key, type, status,
        source_account_id, destination_account_id,
        amount, fee, currency,
        external_reference, provider_code,
        description, metadata, error_details,
        parent_transaction_id,
        confirmation_token, confirmation_expires_at,
        created_at, completed_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)`,
      [
        data['id'],
        data['idempotencyKey'],
        data['type'],
        data['status'],
        data['sourceAccountId'],
        data['destinationAccountId'],
        (data['amount'] as { amount: string }).amount,
        (data['fee'] as { amount: string }).amount,
        (data['amount'] as { currency: string }).currency,
        data['externalReference'],
        data['providerCode'],
        data['description'],
        JSON.stringify(data['metadata']),
        data['errorDetails'] ? JSON.stringify(data['errorDetails']) : null,
        data['parentTransactionId'],
        data['confirmationToken'],
        data['confirmationExpiresAt'],
        data['createdAt'],
        data['completedAt'],
      ]
    );
  }

  async update(transaction: Transaction): Promise<void> {
    const data = transaction.toJSON();

    await this.db.query(
      `UPDATE transactions SET
        status = $1,
        external_reference = $2,
        error_details = $3,
        completed_at = $4,
        metadata = $5,
        confirmation_token = $6,
        confirmation_expires_at = $7
      WHERE id = $8`,
      [
        data['status'],
        data['externalReference'],
        data['errorDetails'] ? JSON.stringify(data['errorDetails']) : null,
        data['completedAt'],
        JSON.stringify(data['metadata']),
        data['confirmationToken'],
        data['confirmationExpiresAt'],
        data['id'],
      ]
    );
  }

  async saveLedgerEntries(entries: LedgerEntry[]): Promise<void> {
    if (entries.length === 0) return;

    const values: unknown[] = [];
    const placeholders: string[] = [];

    entries.forEach((entry, index) => {
      const data = entry.toJSON();
      const offset = index * 7;
      placeholders.push(
        `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}, $${offset + 6}, $${offset + 7})`
      );
      values.push(
        data['id'],
        data['transactionId'],
        data['accountId'],
        data['entryType'],
        (data['amount'] as { amount: string }).amount,
        (data['balanceAfter'] as { amount: string }).amount,
        data['createdAt']
      );
    });

    await this.db.query(
      `INSERT INTO ledger_entries (
        id, transaction_id, account_id, entry_type,
        amount, balance_after, created_at
      ) VALUES ${placeholders.join(', ')}`,
      values
    );
  }

  async getLedgerEntries(transactionId: TransactionId): Promise<LedgerEntry[]> {
    const result = await this.db.query<LedgerEntryRow>(
      `SELECT * FROM ledger_entries WHERE transaction_id = $1 ORDER BY created_at`,
      [transactionId]
    );

    return result.rows.map((row) => this.mapRowToLedgerEntry(row));
  }

  async getLedgerEntriesByAccount(
    accountId: AccountId,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<LedgerEntry>> {
    const params: unknown[] = [accountId];
    let paramIndex = 2;

    let cursorCondition = '';
    if (pagination.cursor) {
      const cursor = this.decodeCursor(pagination.cursor);
      cursorCondition = `AND (created_at, id) < ($${paramIndex++}, $${paramIndex++})`;
      params.push(cursor.createdAt, cursor.id);
    }

    const limit = pagination.limit + 1;
    params.push(limit);

    const result = await this.db.query<LedgerEntryRow>(
      `SELECT * FROM ledger_entries
       WHERE account_id = $1 ${cursorCondition}
       ORDER BY created_at DESC, id DESC
       LIMIT $${paramIndex}`,
      params
    );

    const hasMore = result.rows.length > pagination.limit;
    const rows = hasMore ? result.rows.slice(0, -1) : result.rows;

    const entries = rows.map((row) => this.mapRowToLedgerEntry(row));

    let nextCursor: string | null = null;
    if (hasMore && rows.length > 0) {
      const lastRow = rows[rows.length - 1]!;
      nextCursor = this.encodeCursor({
        id: lastRow.id,
        createdAt: lastRow.created_at,
      });
    }

    return {
      data: entries,
      pagination: {
        hasMore,
        nextCursor,
        prevCursor: null,
      },
    };
  }

  private mapRowToTransaction(
    row: TransactionRow,
    entries: LedgerEntry[]
  ): Transaction {
    return Transaction.fromPersistence({
      id: TransactionId.from(row.id),
      idempotencyKey: IdempotencyKey.from(row.idempotency_key),
      type: row.type,
      status: row.status,
      sourceAccountId: row.source_account_id
        ? AccountId.from(row.source_account_id)
        : null,
      destinationAccountId: row.destination_account_id
        ? AccountId.from(row.destination_account_id)
        : null,
      amount: Money.fromString(row.amount, 'CREDIT'),
      fee: Money.fromString(row.fee, 'CREDIT'),
      externalReference: row.external_reference
        ? ExternalReference.from(row.external_reference)
        : null,
      providerCode: row.provider_code,
      description: row.description ?? '',
      metadata: row.metadata,
      errorDetails: row.error_details,
      parentTransactionId: row.parent_transaction_id
        ? TransactionId.from(row.parent_transaction_id)
        : null,
      confirmationToken: row.confirmation_token,
      confirmationExpiresAt: row.confirmation_expires_at,
      entries,
      createdAt: row.created_at,
      completedAt: row.completed_at,
    });
  }

  private mapRowToLedgerEntry(row: LedgerEntryRow): LedgerEntry {
    return LedgerEntry.fromPersistence({
      id: LedgerEntryId.from(row.id),
      transactionId: TransactionId.from(row.transaction_id),
      accountId: AccountId.from(row.account_id),
      entryType: row.entry_type,
      amount: Money.fromString(row.amount, 'CREDIT'),
      balanceAfter: Money.fromString(row.balance_after, 'CREDIT'),
      createdAt: row.created_at,
    });
  }

  private encodeCursor(data: { id: string; createdAt: Date }): string {
    return Buffer.from(JSON.stringify(data)).toString('base64');
  }

  private decodeCursor(cursor: string): { id: string; createdAt: Date } {
    const decoded = JSON.parse(Buffer.from(cursor, 'base64').toString('utf-8'));
    return {
      id: decoded.id,
      createdAt: new Date(decoded.createdAt),
    };
  }
}
