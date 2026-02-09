/**
 * Rate Limiting Middleware
 *
 * Implements token bucket rate limiting with Redis support.
 */

import { Request, Response, NextFunction } from 'express';
import { AuthenticatedRequest } from './authentication';

export interface RateLimitConfig {
  windowMs: number;      // Time window in milliseconds
  maxRequests: number;   // Max requests per window
  keyPrefix?: string;    // Prefix for rate limit keys
}

export interface RateLimitStore {
  increment(key: string, windowMs: number): Promise<{ count: number; resetAt: Date }>;
  get(key: string): Promise<{ count: number; resetAt: Date } | null>;
}

export function createRateLimitMiddleware(
  config: RateLimitConfig,
  store: RateLimitStore
) {
  const keyPrefix = config.keyPrefix ?? 'ratelimit';

  return async function rateLimitMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
  ): Promise<void> {
    const authReq = req as AuthenticatedRequest;

    // Build rate limit key based on user or IP
    const identifier = authReq.user?.id ?? req.ip ?? 'anonymous';
    const key = `${keyPrefix}:${identifier}`;

    try {
      const result = await store.increment(key, config.windowMs);

      // Set rate limit headers on all responses
      res.setHeader('X-RateLimit-Limit', config.maxRequests);
      res.setHeader('X-RateLimit-Remaining', Math.max(0, config.maxRequests - result.count));
      res.setHeader('X-RateLimit-Reset', Math.floor(result.resetAt.getTime() / 1000));

      if (result.count > config.maxRequests) {
        const retryAfter = Math.ceil((result.resetAt.getTime() - Date.now()) / 1000);
        res.setHeader('Retry-After', retryAfter);

        res.status(429).json({
          type: 'https://api.ledger.example.com/problems/rate-limit-exceeded',
          title: 'Rate Limit Exceeded',
          status: 429,
          detail: `Too many requests. Please wait ${retryAfter} seconds before retrying.`,
          retry_after: retryAfter,
        });
        return;
      }

      next();
    } catch (error) {
      // On rate limit store failure, allow the request through
      // but log the error
      console.error('Rate limit store error:', error);
      next();
    }
  };
}

/**
 * In-memory rate limit store (for development/testing)
 * Use Redis in production!
 */
export class InMemoryRateLimitStore implements RateLimitStore {
  private store = new Map<string, { count: number; resetAt: Date }>();

  async increment(
    key: string,
    windowMs: number
  ): Promise<{ count: number; resetAt: Date }> {
    const now = Date.now();
    const existing = this.store.get(key);

    if (!existing || existing.resetAt.getTime() <= now) {
      // Start new window
      const entry = {
        count: 1,
        resetAt: new Date(now + windowMs),
      };
      this.store.set(key, entry);
      return entry;
    }

    // Increment existing window
    existing.count++;
    return existing;
  }

  async get(key: string): Promise<{ count: number; resetAt: Date } | null> {
    const entry = this.store.get(key);
    if (!entry || entry.resetAt.getTime() <= Date.now()) {
      return null;
    }
    return entry;
  }

  // Cleanup expired entries
  cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.store.entries()) {
      if (entry.resetAt.getTime() <= now) {
        this.store.delete(key);
      }
    }
  }
}

/**
 * Create rate limiters for different endpoint categories
 */
export function createRateLimiters(store: RateLimitStore) {
  return {
    // Standard API endpoints
    standard: createRateLimitMiddleware(
      { windowMs: 60 * 1000, maxRequests: 1000, keyPrefix: 'rl:standard' },
      store
    ),

    // Transfer operations
    transfers: createRateLimitMiddleware(
      { windowMs: 60 * 1000, maxRequests: 100, keyPrefix: 'rl:transfers' },
      store
    ),

    // Deposit operations
    deposits: createRateLimitMiddleware(
      { windowMs: 60 * 60 * 1000, maxRequests: 20, keyPrefix: 'rl:deposits' },
      store
    ),

    // Withdrawal operations
    withdrawals: createRateLimitMiddleware(
      { windowMs: 60 * 60 * 1000, maxRequests: 10, keyPrefix: 'rl:withdrawals' },
      store
    ),

    // Webhook endpoints (higher limit)
    webhooks: createRateLimitMiddleware(
      { windowMs: 1000, maxRequests: 100, keyPrefix: 'rl:webhooks' },
      store
    ),
  };
}
