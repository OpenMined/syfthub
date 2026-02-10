/**
 * PostgreSQL Transaction Manager
 *
 * Manages database transactions for use cases that need atomic operations.
 */

import { Pool, PoolClient } from 'pg';
import { TransactionManager } from '../../application/use-cases/ExecuteTransfer';

/**
 * Context that holds the current transaction client
 * Uses AsyncLocalStorage for request-scoped transactions
 */
import { AsyncLocalStorage } from 'async_hooks';

const transactionContext = new AsyncLocalStorage<PoolClient>();

export function getCurrentClient(): PoolClient | undefined {
  return transactionContext.getStore();
}

export class PostgresTransactionManager implements TransactionManager {
  constructor(private pool: Pool) {}

  async executeInTransaction<T>(fn: () => Promise<T>): Promise<T> {
    // Check if we're already in a transaction
    const existingClient = getCurrentClient();
    if (existingClient) {
      // Reuse existing transaction (nested call)
      return fn();
    }

    // Start new transaction
    const client = await this.pool.connect();

    try {
      await client.query('BEGIN');

      const result = await transactionContext.run(client, fn);

      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  /**
   * Execute a function with serializable isolation level
   * Use for operations that require the highest consistency
   */
  async executeSerializable<T>(fn: () => Promise<T>): Promise<T> {
    const client = await this.pool.connect();

    try {
      await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');

      const result = await transactionContext.run(client, fn);

      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK');

      // Check for serialization failure
      if (this.isSerializationError(error)) {
        // Could implement retry logic here
        throw new SerializationError('Transaction failed due to concurrent modification');
      }

      throw error;
    } finally {
      client.release();
    }
  }

  private isSerializationError(error: unknown): boolean {
    if (error && typeof error === 'object' && 'code' in error) {
      // PostgreSQL serialization_failure error code
      return (error as { code: string }).code === '40001';
    }
    return false;
  }
}

export class SerializationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SerializationError';
  }
}
