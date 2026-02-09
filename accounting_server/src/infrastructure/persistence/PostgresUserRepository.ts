/**
 * PostgreSQL User Repository
 *
 * Implements user persistence using PostgreSQL.
 */

import { Pool } from 'pg';
import { User, UserStatus } from '../../domain/entities/User';
import { UserId } from '../../domain/value-objects/Identifiers';
import { UserRepository } from '../../application/ports/output/UserRepository';

interface UserRow {
  id: string;
  email: string;
  password_hash: string;
  status: string;
  created_at: Date;
  updated_at: Date;
}

export class PostgresUserRepository implements UserRepository {
  constructor(private readonly pool: Pool) {}

  async save(user: User): Promise<void> {
    const query = `
      INSERT INTO users (id, email, password_hash, status, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6)
      ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        password_hash = EXCLUDED.password_hash,
        status = EXCLUDED.status,
        updated_at = NOW()
    `;

    await this.pool.query(query, [
      user.id,
      user.email,
      user.passwordHash,
      user.status,
      user.createdAt,
      user.updatedAt,
    ]);
  }

  async findById(id: UserId): Promise<User | null> {
    const query = `
      SELECT id, email, password_hash, status, created_at, updated_at
      FROM users
      WHERE id = $1
    `;

    const result = await this.pool.query<UserRow>(query, [id]);

    if (result.rows.length === 0) {
      return null;
    }

    return this.rowToUser(result.rows[0]!);
  }

  async findByEmail(email: string): Promise<User | null> {
    const query = `
      SELECT id, email, password_hash, status, created_at, updated_at
      FROM users
      WHERE email = $1
    `;

    const result = await this.pool.query<UserRow>(query, [email.toLowerCase().trim()]);

    if (result.rows.length === 0) {
      return null;
    }

    return this.rowToUser(result.rows[0]!);
  }

  async emailExists(email: string): Promise<boolean> {
    const query = `
      SELECT 1 FROM users WHERE email = $1 LIMIT 1
    `;

    const result = await this.pool.query(query, [email.toLowerCase().trim()]);
    return result.rows.length > 0;
  }

  private rowToUser(row: UserRow): User {
    return User.reconstitute({
      id: UserId.from(row.id),
      email: row.email,
      passwordHash: row.password_hash,
      status: row.status as UserStatus,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    });
  }
}
