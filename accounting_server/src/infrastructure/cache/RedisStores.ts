/**
 * Redis-based Stores
 *
 * Production-ready implementations of IdempotencyStore and RateLimitStore
 * using Redis for distributed caching and atomic operations.
 */

import { createClient, RedisClientType } from 'redis';
import {
  IdempotencyStore,
  IdempotencyEntry,
  StoredResponse,
} from '../http/middleware/idempotency';
import { RateLimitStore } from '../http/middleware/rateLimiting';

/**
 * Create and connect a Redis client
 */
export async function createRedisClient(
  url: string
): Promise<RedisClientType> {
  const client = createClient({ url }) as RedisClientType;

  client.on('error', (err: Error) => {
    console.error('Redis client error:', err);
  });

  client.on('connect', () => {
    console.log('Redis client connected');
  });

  client.on('reconnecting', () => {
    console.log('Redis client reconnecting');
  });

  await client.connect();
  return client;
}

/**
 * Redis-based Idempotency Store
 *
 * Stores idempotency responses in Redis with automatic expiration.
 */
export class RedisIdempotencyStore implements IdempotencyStore {
  private keyPrefix = 'idempotency';

  constructor(private client: RedisClientType) {}

  private makeKey(key: string, userId: string, endpoint: string): string {
    return `${this.keyPrefix}:${userId}:${endpoint}:${key}`;
  }

  async get(
    key: string,
    userId: string,
    endpoint: string
  ): Promise<StoredResponse | null> {
    const storeKey = this.makeKey(key, userId, endpoint);

    try {
      const data = await this.client.get(storeKey);
      if (!data) {
        return null;
      }

      const entry = JSON.parse(data) as IdempotencyEntry;
      return {
        requestHash: entry.requestHash,
        responseCode: entry.responseCode,
        responseBody: entry.responseBody,
        createdAt: new Date(entry.expiresAt),
      };
    } catch (error) {
      console.error('Redis idempotency get error:', error);
      return null;
    }
  }

  async set(entry: IdempotencyEntry): Promise<void> {
    const storeKey = this.makeKey(entry.key, entry.userId, entry.endpoint);
    const ttlMs = entry.expiresAt.getTime() - Date.now();

    if (ttlMs <= 0) {
      return;
    }

    const ttlSeconds = Math.ceil(ttlMs / 1000);

    try {
      await this.client.setEx(storeKey, ttlSeconds, JSON.stringify(entry));
    } catch (error) {
      console.error('Redis idempotency set error:', error);
      throw error;
    }
  }

  async delete(key: string, userId: string, endpoint: string): Promise<void> {
    const storeKey = this.makeKey(key, userId, endpoint);

    try {
      await this.client.del(storeKey);
    } catch (error) {
      console.error('Redis idempotency delete error:', error);
    }
  }
}

/**
 * Redis-based Rate Limit Store
 *
 * Implements sliding window rate limiting using Redis sorted sets
 * for accurate rate limiting across distributed instances.
 */
export class RedisRateLimitStore implements RateLimitStore {
  constructor(private client: RedisClientType) {}

  /**
   * Increment the rate limit counter using a sliding window algorithm
   */
  async increment(
    key: string,
    windowMs: number
  ): Promise<{ count: number; resetAt: Date }> {
    const now = Date.now();
    const windowStart = now - windowMs;
    const resetAt = new Date(now + windowMs);

    try {
      // Use Redis MULTI for atomic operations
      const results = await this.client
        .multi()
        // Remove expired entries
        .zRemRangeByScore(key, '-inf', windowStart)
        // Add current request
        .zAdd(key, { score: now, value: `${now}:${Math.random()}` })
        // Count requests in window
        .zCard(key)
        // Set expiration on the key
        .pExpire(key, windowMs)
        .exec();

      // zCard result is at index 2
      const count = (results?.[2] as number) ?? 1;

      return { count, resetAt };
    } catch (error) {
      console.error('Redis rate limit increment error:', error);
      // On error, allow the request through
      return { count: 1, resetAt };
    }
  }

  /**
   * Get current rate limit status without incrementing
   */
  async get(key: string): Promise<{ count: number; resetAt: Date } | null> {
    try {
      const count = await this.client.zCard(key);
      const ttl = await this.client.pTTL(key);

      if (count === 0 || ttl <= 0) {
        return null;
      }

      return {
        count,
        resetAt: new Date(Date.now() + ttl),
      };
    } catch (error) {
      console.error('Redis rate limit get error:', error);
      return null;
    }
  }
}

/**
 * Simple Redis-based Rate Limit Store
 *
 * Uses a simpler fixed window approach with Redis INCR.
 * Less accurate than sliding window but more efficient.
 */
export class SimpleRedisRateLimitStore implements RateLimitStore {
  constructor(private client: RedisClientType) {}

  async increment(
    key: string,
    windowMs: number
  ): Promise<{ count: number; resetAt: Date }> {
    const windowKey = this.getWindowKey(key, windowMs);
    const windowSeconds = Math.ceil(windowMs / 1000);

    try {
      // INCR and set expiration atomically
      const count = await this.client.incr(windowKey);

      // Set expiration only on first request in window
      if (count === 1) {
        await this.client.expire(windowKey, windowSeconds);
      }

      // Get TTL for reset time
      const ttl = await this.client.ttl(windowKey);
      const resetAt = new Date(Date.now() + ttl * 1000);

      return { count, resetAt };
    } catch (error) {
      console.error('Redis rate limit increment error:', error);
      return { count: 1, resetAt: new Date(Date.now() + windowMs) };
    }
  }

  async get(key: string): Promise<{ count: number; resetAt: Date } | null> {
    try {
      // For fixed window, we need to check current window
      const windowKey = this.getWindowKey(key, 60000); // Default 1 minute
      const count = await this.client.get(windowKey);

      if (!count) {
        return null;
      }

      const ttl = await this.client.ttl(windowKey);
      return {
        count: parseInt(count, 10),
        resetAt: new Date(Date.now() + ttl * 1000),
      };
    } catch (error) {
      console.error('Redis rate limit get error:', error);
      return null;
    }
  }

  /**
   * Generate a window key based on current time bucket
   */
  private getWindowKey(key: string, windowMs: number): string {
    const bucket = Math.floor(Date.now() / windowMs);
    return `${key}:${bucket}`;
  }
}

/**
 * Redis-based Distributed Lock
 *
 * Provides distributed locking for coordinating operations
 * across multiple server instances.
 */
export class RedisDistributedLock {
  private lockPrefix = 'lock';

  constructor(private client: RedisClientType) {}

  /**
   * Acquire a lock with automatic expiration
   */
  async acquire(
    resource: string,
    ttlMs: number
  ): Promise<{ acquired: boolean; token: string }> {
    const token = `${Date.now()}:${Math.random().toString(36).substring(2)}`;
    const key = `${this.lockPrefix}:${resource}`;

    try {
      const result = await this.client.set(key, token, {
        NX: true, // Only set if not exists
        PX: ttlMs, // Expiration in milliseconds
      });

      return {
        acquired: result === 'OK',
        token,
      };
    } catch (error) {
      console.error('Redis lock acquire error:', error);
      return { acquired: false, token: '' };
    }
  }

  /**
   * Release a lock if we own it
   */
  async release(resource: string, token: string): Promise<boolean> {
    const key = `${this.lockPrefix}:${resource}`;

    // Use Lua script to ensure atomic check-and-delete
    const script = `
      if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
      else
        return 0
      end
    `;

    try {
      const result = await this.client.eval(script, {
        keys: [key],
        arguments: [token],
      });

      return result === 1;
    } catch (error) {
      console.error('Redis lock release error:', error);
      return false;
    }
  }

  /**
   * Extend a lock's TTL if we own it
   */
  async extend(
    resource: string,
    token: string,
    ttlMs: number
  ): Promise<boolean> {
    const key = `${this.lockPrefix}:${resource}`;

    // Use Lua script to ensure atomic check-and-extend
    const script = `
      if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
      else
        return 0
      end
    `;

    try {
      const result = await this.client.eval(script, {
        keys: [key],
        arguments: [token, ttlMs.toString()],
      });

      return result === 1;
    } catch (error) {
      console.error('Redis lock extend error:', error);
      return false;
    }
  }

  /**
   * Run a function while holding a lock
   */
  async withLock<T>(
    resource: string,
    ttlMs: number,
    fn: () => Promise<T>
  ): Promise<T> {
    const { acquired, token } = await this.acquire(resource, ttlMs);

    if (!acquired) {
      throw new Error(`Failed to acquire lock for resource: ${resource}`);
    }

    try {
      return await fn();
    } finally {
      await this.release(resource, token);
    }
  }
}

/**
 * Redis-based Session Cache
 *
 * Caches session data for fast authentication lookups.
 */
export class RedisSessionCache {
  private keyPrefix = 'session';

  constructor(
    private client: RedisClientType,
    private defaultTtlSeconds: number = 3600
  ) {}

  async get<T>(sessionId: string): Promise<T | null> {
    const key = `${this.keyPrefix}:${sessionId}`;

    try {
      const data = await this.client.get(key);
      return data ? (JSON.parse(data) as T) : null;
    } catch (error) {
      console.error('Redis session get error:', error);
      return null;
    }
  }

  async set<T>(
    sessionId: string,
    data: T,
    ttlSeconds?: number
  ): Promise<void> {
    const key = `${this.keyPrefix}:${sessionId}`;
    const ttl = ttlSeconds ?? this.defaultTtlSeconds;

    try {
      await this.client.setEx(key, ttl, JSON.stringify(data));
    } catch (error) {
      console.error('Redis session set error:', error);
    }
  }

  async delete(sessionId: string): Promise<void> {
    const key = `${this.keyPrefix}:${sessionId}`;

    try {
      await this.client.del(key);
    } catch (error) {
      console.error('Redis session delete error:', error);
    }
  }

  async refresh(sessionId: string, ttlSeconds?: number): Promise<void> {
    const key = `${this.keyPrefix}:${sessionId}`;
    const ttl = ttlSeconds ?? this.defaultTtlSeconds;

    try {
      await this.client.expire(key, ttl);
    } catch (error) {
      console.error('Redis session refresh error:', error);
    }
  }
}
