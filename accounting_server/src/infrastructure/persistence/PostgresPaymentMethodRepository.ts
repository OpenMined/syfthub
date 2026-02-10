/**
 * PostgreSQL Payment Method Repository
 *
 * Implements the PaymentMethodRepository port using PostgreSQL.
 */

import { Pool, PoolClient } from 'pg';
import {
  PaymentMethod,
  PaymentMethodType,
  PaymentMethodStatus,
} from '../../domain/entities/PaymentMethod';
import { ProviderCode } from '../../domain/entities/Transaction';
import {
  PaymentMethodId,
  AccountId,
} from '../../domain/value-objects/Identifiers';
import { PaymentMethodRepository } from '../../application/use-cases/ProcessDeposit';

interface PaymentMethodRow {
  id: string;
  account_id: string;
  provider_code: ProviderCode;
  type: PaymentMethodType;
  status: PaymentMethodStatus;
  external_id: string;
  display_name: string;
  is_default: boolean;
  is_withdrawable: boolean;
  metadata: Record<string, unknown>;
  expires_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export class PostgresPaymentMethodRepository implements PaymentMethodRepository {
  constructor(
    private pool: Pool,
    private client?: PoolClient
  ) {}

  withClient(client: PoolClient): PostgresPaymentMethodRepository {
    return new PostgresPaymentMethodRepository(this.pool, client);
  }

  private get db(): Pool | PoolClient {
    return this.client ?? this.pool;
  }

  async findById(id: string): Promise<PaymentMethod | null> {
    const result = await this.db.query<PaymentMethodRow>(
      `SELECT * FROM payment_methods WHERE id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToPaymentMethod(result.rows[0]!);
  }

  async findByAccountId(accountId: string): Promise<PaymentMethod[]> {
    const result = await this.db.query<PaymentMethodRow>(
      `SELECT * FROM payment_methods
       WHERE account_id = $1 AND status != 'disabled'
       ORDER BY is_default DESC, created_at DESC`,
      [accountId]
    );

    return result.rows.map((row) => this.mapRowToPaymentMethod(row));
  }

  async findByExternalId(externalId: string): Promise<PaymentMethod | null> {
    const result = await this.db.query<PaymentMethodRow>(
      `SELECT * FROM payment_methods WHERE external_id = $1`,
      [externalId]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToPaymentMethod(result.rows[0]!);
  }

  async findDefaultForAccount(accountId: string): Promise<PaymentMethod | null> {
    const result = await this.db.query<PaymentMethodRow>(
      `SELECT * FROM payment_methods
       WHERE account_id = $1 AND is_default = true AND status = 'verified'
       LIMIT 1`,
      [accountId]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToPaymentMethod(result.rows[0]!);
  }

  async findWithdrawableForAccount(accountId: string): Promise<PaymentMethod[]> {
    const result = await this.db.query<PaymentMethodRow>(
      `SELECT * FROM payment_methods
       WHERE account_id = $1
         AND is_withdrawable = true
         AND status = 'verified'
         AND (expires_at IS NULL OR expires_at > NOW())
       ORDER BY is_default DESC, created_at DESC`,
      [accountId]
    );

    return result.rows.map((row) => this.mapRowToPaymentMethod(row));
  }

  async save(paymentMethod: PaymentMethod): Promise<void> {
    const data = paymentMethod.toJSON();

    await this.db.query(
      `INSERT INTO payment_methods (
        id, account_id, provider_code, type, status,
        external_id, display_name, is_default, is_withdrawable,
        metadata, expires_at, created_at, updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)`,
      [
        data['id'],
        data['accountId'],
        data['providerCode'],
        data['type'],
        data['status'],
        paymentMethod.externalId,
        data['displayName'],
        data['isDefault'],
        data['isWithdrawable'],
        JSON.stringify(data['metadata']),
        data['expiresAt'],
        data['createdAt'],
        data['updatedAt'],
      ]
    );
  }

  async update(paymentMethod: PaymentMethod): Promise<void> {
    const data = paymentMethod.toJSON();

    await this.db.query(
      `UPDATE payment_methods SET
        status = $1,
        display_name = $2,
        is_default = $3,
        metadata = $4,
        updated_at = $5
      WHERE id = $6`,
      [
        data['status'],
        data['displayName'],
        data['isDefault'],
        JSON.stringify(data['metadata']),
        data['updatedAt'],
        data['id'],
      ]
    );
  }

  async delete(id: string): Promise<void> {
    // Soft delete by setting status to disabled
    await this.db.query(
      `UPDATE payment_methods SET status = 'disabled', updated_at = NOW() WHERE id = $1`,
      [id]
    );
  }

  async clearDefaultForAccount(accountId: string): Promise<void> {
    await this.db.query(
      `UPDATE payment_methods SET is_default = false, updated_at = NOW()
       WHERE account_id = $1 AND is_default = true`,
      [accountId]
    );
  }

  async countByAccountId(accountId: string): Promise<number> {
    const result = await this.db.query<{ count: string }>(
      `SELECT COUNT(*) as count FROM payment_methods
       WHERE account_id = $1 AND status != 'disabled'`,
      [accountId]
    );

    return parseInt(result.rows[0]?.count ?? '0', 10);
  }

  private mapRowToPaymentMethod(row: PaymentMethodRow): PaymentMethod {
    return PaymentMethod.fromPersistence({
      id: PaymentMethodId.from(row.id),
      accountId: AccountId.from(row.account_id),
      providerCode: row.provider_code,
      type: row.type,
      status: row.status,
      externalId: row.external_id,
      displayName: row.display_name,
      isDefault: row.is_default,
      isWithdrawable: row.is_withdrawable,
      metadata: row.metadata,
      expiresAt: row.expires_at,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    });
  }
}
