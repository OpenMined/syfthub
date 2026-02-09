/**
 * Idempotency Middleware
 *
 * Ensures that requests with the same Idempotency-Key produce
 * the same response, preventing duplicate operations.
 */

import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import { AuthenticatedRequest } from './authentication';

export interface IdempotencyStore {
  get(key: string, userId: string, endpoint: string): Promise<StoredResponse | null>;
  set(entry: IdempotencyEntry): Promise<void>;
  delete(key: string, userId: string, endpoint: string): Promise<void>;
}

export interface StoredResponse {
  requestHash: string;
  responseCode: number;
  responseBody: unknown;
  createdAt: Date;
}

export interface IdempotencyEntry {
  key: string;
  userId: string;
  endpoint: string;
  requestHash: string;
  responseCode: number;
  responseBody: unknown;
  expiresAt: Date;
}

interface IdempotencyConfig {
  store: IdempotencyStore;
  ttlMs?: number; // Default 24 hours
  requiredForMethods?: string[]; // Default: POST, PUT, PATCH
}

export function createIdempotencyMiddleware(config: IdempotencyConfig) {
  const ttlMs = config.ttlMs ?? 24 * 60 * 60 * 1000; // 24 hours
  const requiredMethods = config.requiredForMethods ?? ['POST', 'PUT', 'PATCH'];

  return async function idempotencyMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
  ): Promise<void> {
    // Only apply to methods that require idempotency
    if (!requiredMethods.includes(req.method)) {
      next();
      return;
    }

    const idempotencyKey = req.headers['idempotency-key'];

    if (!idempotencyKey || typeof idempotencyKey !== 'string') {
      res.status(400).json({
        type: 'https://api.ledger.example.com/problems/missing-idempotency-key',
        title: 'Missing Idempotency Key',
        status: 400,
        detail: 'Idempotency-Key header is required for this request',
      });
      return;
    }

    // Validate idempotency key format (must be a valid UUID v4)
    // This prevents low-entropy keys and ensures uniqueness
    const uuidV4Regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    if (!uuidV4Regex.test(idempotencyKey)) {
      res.status(400).json({
        type: 'https://api.ledger.example.com/problems/invalid-idempotency-key',
        title: 'Invalid Idempotency Key',
        status: 400,
        detail: 'Idempotency-Key must be a valid UUID v4 (e.g., 550e8400-e29b-41d4-a716-446655440000)',
      });
      return;
    }

    const authReq = req as AuthenticatedRequest;
    const userId = authReq.user?.id as string ?? 'anonymous';
    const endpoint = `${req.method}:${req.path}`;
    const requestHash = hashRequestBody(req.body);

    try {
      // Check for existing response
      const existing = await config.store.get(idempotencyKey, userId, endpoint);

      if (existing) {
        // Verify request body matches
        if (existing.requestHash !== requestHash) {
          res.status(422).json({
            type: 'https://api.ledger.example.com/problems/idempotency-key-reuse',
            title: 'Idempotency Key Reuse',
            status: 422,
            detail: 'This idempotency key was already used with a different request body',
          });
          return;
        }

        // Return cached response
        res.status(existing.responseCode).json(existing.responseBody);
        return;
      }

      // Capture the response
      const originalJson = res.json.bind(res);
      let responseCaptured = false;

      res.json = function (body: unknown) {
        if (!responseCaptured && res.statusCode < 500) {
          responseCaptured = true;

          // Store the response asynchronously
          config.store.set({
            key: idempotencyKey,
            userId,
            endpoint,
            requestHash,
            responseCode: res.statusCode,
            responseBody: body,
            expiresAt: new Date(Date.now() + ttlMs),
          }).catch((err) => {
            console.error('Failed to store idempotency response:', err);
          });
        }

        return originalJson(body);
      };

      next();
    } catch (error) {
      next(error);
    }
  };
}

function hashRequestBody(body: unknown): string {
  const content = typeof body === 'string' ? body : JSON.stringify(body ?? {});
  return crypto.createHash('sha256').update(content).digest('hex');
}

/**
 * In-memory idempotency store (for development/testing)
 * Use Redis in production!
 */
export class InMemoryIdempotencyStore implements IdempotencyStore {
  private store = new Map<string, IdempotencyEntry>();

  private makeKey(key: string, userId: string, endpoint: string): string {
    return `${userId}:${endpoint}:${key}`;
  }

  async get(
    key: string,
    userId: string,
    endpoint: string
  ): Promise<StoredResponse | null> {
    const storeKey = this.makeKey(key, userId, endpoint);
    const entry = this.store.get(storeKey);

    if (!entry) {
      return null;
    }

    // Check expiration
    if (entry.expiresAt < new Date()) {
      this.store.delete(storeKey);
      return null;
    }

    return {
      requestHash: entry.requestHash,
      responseCode: entry.responseCode,
      responseBody: entry.responseBody,
      createdAt: entry.expiresAt, // Not ideal but works for testing
    };
  }

  async set(entry: IdempotencyEntry): Promise<void> {
    const storeKey = this.makeKey(entry.key, entry.userId, entry.endpoint);
    this.store.set(storeKey, entry);
  }

  async delete(key: string, userId: string, endpoint: string): Promise<void> {
    const storeKey = this.makeKey(key, userId, endpoint);
    this.store.delete(storeKey);
  }

  // Cleanup expired entries
  cleanup(): void {
    const now = new Date();
    for (const [key, entry] of this.store.entries()) {
      if (entry.expiresAt < now) {
        this.store.delete(key);
      }
    }
  }
}
