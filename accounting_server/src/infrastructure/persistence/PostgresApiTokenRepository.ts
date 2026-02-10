/**
 * PostgreSQL API Token Repository
 *
 * Implements the ApiTokenRepository port using PostgreSQL.
 */

import { Pool, PoolClient } from 'pg';
import { ApiToken, TokenScope } from '../../domain/entities/ApiToken';
import { ApiTokenId, UserId } from '../../domain/value-objects/Identifiers';
import { ApiTokenRepository } from '../../application/ports/output/ApiTokenRepository';
import { OptimisticLockError } from './PostgresAccountRepository';

interface ApiTokenRow {
  id: string;
  user_id: string;
  token_prefix: string;
  token_hash: Buffer;
  name: string;
  scopes: string[];
  created_at: Date;
  expires_at: Date | null;
  last_used_at: Date | null;
  last_used_ip: string | null;
  revoked_at: Date | null;
  revoked_reason: string | null;
  version: number;
}

export class PostgresApiTokenRepository implements ApiTokenRepository {
  constructor(
    private pool: Pool,
    private client?: PoolClient
  ) {}

  /**
   * Create a new instance bound to a specific client (for transactions)
   */
  withClient(client: PoolClient): PostgresApiTokenRepository {
    return new PostgresApiTokenRepository(this.pool, client);
  }

  private get db(): Pool | PoolClient {
    return this.client ?? this.pool;
  }

  async findById(id: ApiTokenId): Promise<ApiToken | null> {
    const result = await this.db.query<ApiTokenRow>(
      `SELECT * FROM api_tokens WHERE id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToToken(result.rows[0]!);
  }

  async findByHash(hash: Buffer): Promise<ApiToken | null> {
    const result = await this.db.query<ApiTokenRow>(
      `SELECT * FROM api_tokens WHERE token_hash = $1 AND revoked_at IS NULL`,
      [hash]
    );

    if (result.rows.length === 0) {
      return null;
    }

    return this.mapRowToToken(result.rows[0]!);
  }

  async findByUserId(userId: UserId): Promise<ApiToken[]> {
    const result = await this.db.query<ApiTokenRow>(
      `SELECT * FROM api_tokens
       WHERE user_id = $1 AND revoked_at IS NULL
       ORDER BY created_at DESC`,
      [userId]
    );

    return result.rows.map((row) => this.mapRowToToken(row));
  }

  async save(token: ApiToken): Promise<void> {
    await this.db.query(
      `INSERT INTO api_tokens (
        id, user_id, token_prefix, token_hash, name, scopes,
        created_at, expires_at, last_used_at, last_used_ip,
        revoked_at, revoked_reason, version
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)`,
      [
        token.id,
        token.userId,
        token.prefix,
        token.tokenHash,
        token.name,
        token.scopes,
        token.createdAt,
        token.expiresAt,
        token.lastUsedAt,
        token.lastUsedIp,
        token.revokedAt,
        token.revokedReason,
        token.version,
      ]
    );
  }

  async update(token: ApiToken): Promise<void> {
    const previousVersion = token.version - 1;

    const result = await this.db.query(
      `UPDATE api_tokens SET
        name = $1,
        last_used_at = $2,
        last_used_ip = $3,
        revoked_at = $4,
        revoked_reason = $5,
        version = $6
      WHERE id = $7 AND version = $8`,
      [
        token.name,
        token.lastUsedAt,
        token.lastUsedIp,
        token.revokedAt,
        token.revokedReason,
        token.version,
        token.id,
        previousVersion,
      ]
    );

    if (result.rowCount === 0) {
      throw new OptimisticLockError('ApiToken', token.id);
    }
  }

  async countByUserId(userId: UserId): Promise<number> {
    const result = await this.db.query<{ count: string }>(
      `SELECT COUNT(*) as count FROM api_tokens
       WHERE user_id = $1 AND revoked_at IS NULL`,
      [userId]
    );

    return parseInt(result.rows[0]?.count ?? '0', 10);
  }

  private mapRowToToken(row: ApiTokenRow): ApiToken {
    return ApiToken.fromPersistence({
      id: ApiTokenId.from(row.id),
      userId: UserId.from(row.user_id),
      tokenPrefix: row.token_prefix.trim(), // char(8) may have trailing spaces
      tokenHash: row.token_hash,
      name: row.name,
      scopes: row.scopes as TokenScope[],
      createdAt: row.created_at,
      expiresAt: row.expires_at,
      lastUsedAt: row.last_used_at,
      lastUsedIp: row.last_used_ip,
      revokedAt: row.revoked_at,
      revokedReason: row.revoked_reason,
      version: row.version,
    });
  }
}
