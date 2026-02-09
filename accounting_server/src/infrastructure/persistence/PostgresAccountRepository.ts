/**
 * PostgreSQL Account Repository
 *
 * Implements the AccountRepository port using PostgreSQL.
 */

import { Pool, PoolClient } from 'pg';
import { Account, AccountType, AccountStatus } from '../../domain/entities/Account';
import { Money } from '../../domain/value-objects/Money';
import { AccountId, UserId } from '../../domain/value-objects/Identifiers';
import { AccountRepository } from '../../application/ports/output/AccountRepository';

export class OptimisticLockError extends Error {
  constructor(entityType: string, id: string) {
    super(`${entityType} ${id} was modified concurrently. Please retry.`);
    this.name = 'OptimisticLockError';
  }
}

interface AccountRow {
  id: string;
  user_id: string;
  type: AccountType;
  status: AccountStatus;
  balance: string;
  available_balance: string;
  currency: string;
  metadata: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
  version: number;
}

export class PostgresAccountRepository implements AccountRepository {
  constructor(
    private pool: Pool,
    private client?: PoolClient // Optional client for transaction context
  ) {}

  /**
   * Create a new instance bound to a specific client (for transactions)
   */
  withClient(client: PoolClient): PostgresAccountRepository {
    return new PostgresAccountRepository(this.pool, client);
  }

  private get db(): Pool | PoolClient {
    return this.client ?? this.pool;
  }

  async findById(id: AccountId): Promise<Account | null> {
    const result = await this.db.query<AccountRow>(
      `SELECT * FROM accounts WHERE id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToAccount(result.rows[0]!);
  }

  async findByIdForUpdate(id: AccountId): Promise<Account | null> {
    const result = await this.db.query<AccountRow>(
      `SELECT * FROM accounts WHERE id = $1 FOR UPDATE`,
      [id]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToAccount(result.rows[0]!);
  }

  async findByUserId(userId: UserId): Promise<Account[]> {
    const result = await this.db.query<AccountRow>(
      `SELECT * FROM accounts WHERE user_id = $1 ORDER BY created_at DESC`,
      [userId]
    );

    return result.rows.map((row) => this.mapRowToAccount(row));
  }

  async findByIdsForUpdate(ids: AccountId[]): Promise<Account[]> {
    if (ids.length === 0) {
      return [];
    }

    // Sort IDs to ensure consistent lock ordering (prevent deadlocks)
    const sortedIds = [...ids].sort();

    const placeholders = sortedIds.map((_, i) => `$${i + 1}`).join(', ');
    const result = await this.db.query<AccountRow>(
      `SELECT * FROM accounts WHERE id IN (${placeholders}) ORDER BY id FOR UPDATE`,
      sortedIds
    );

    return result.rows.map((row) => this.mapRowToAccount(row));
  }

  async save(account: Account): Promise<void> {
    const data = account.toJSON();

    await this.db.query(
      `INSERT INTO accounts (
        id, user_id, type, status, balance, available_balance,
        currency, metadata, created_at, updated_at, version
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
      [
        data['id'],
        data['userId'],
        data['type'],
        data['status'],
        (data['balance'] as { amount: string }).amount,
        (data['availableBalance'] as { amount: string }).amount,
        (data['balance'] as { currency: string }).currency,
        JSON.stringify(data['metadata']),
        data['createdAt'],
        data['updatedAt'],
        data['version'],
      ]
    );
  }

  async update(account: Account): Promise<void> {
    const data = account.toJSON();
    const previousVersion = (data['version'] as number) - 1;

    const result = await this.db.query(
      `UPDATE accounts SET
        status = $1,
        balance = $2,
        available_balance = $3,
        metadata = $4,
        updated_at = $5,
        version = $6
      WHERE id = $7 AND version = $8`,
      [
        data['status'],
        (data['balance'] as { amount: string }).amount,
        (data['availableBalance'] as { amount: string }).amount,
        JSON.stringify(data['metadata']),
        data['updatedAt'],
        data['version'],
        data['id'],
        previousVersion,
      ]
    );

    if (result.rowCount === 0) {
      throw new OptimisticLockError('Account', data['id'] as string);
    }
  }

  async exists(id: AccountId): Promise<boolean> {
    const result = await this.db.query(
      `SELECT 1 FROM accounts WHERE id = $1`,
      [id]
    );
    return result.rows.length > 0;
  }

  private mapRowToAccount(row: AccountRow): Account {
    return Account.fromPersistence({
      id: AccountId.from(row.id),
      userId: UserId.from(row.user_id),
      type: row.type,
      status: row.status,
      balance: Money.fromString(row.balance, 'CREDIT'),
      availableBalance: Money.fromString(row.available_balance, 'CREDIT'),
      metadata: row.metadata,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      version: row.version,
    });
  }
}
