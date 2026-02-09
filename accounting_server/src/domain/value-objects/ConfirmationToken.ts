/**
 * Confirmation Token Value Object
 *
 * Generates and validates secure HMAC-based tokens for transfer confirmation.
 * Tokens are time-limited and cryptographically secure.
 *
 * Token Format (v1):
 * - Prefix: "ct1_" (confirmation token version 1)
 * - Body: URL-safe base64 encoded payload
 * - Payload: transactionId|salt|expiresAt|signature
 *
 * Security features:
 * - HMAC-SHA256 signature prevents tampering
 * - Random salt prevents replay attacks
 * - Time-limited expiration
 * - Opaque format hides internal structure from attackers
 * - Timing-safe comparison prevents timing attacks
 */

import { createHmac, randomBytes, timingSafeEqual } from 'crypto';

/** Default token expiration: 24 hours */
const DEFAULT_EXPIRATION_HOURS = 24;

/** Token version prefix for format evolution */
const TOKEN_VERSION_PREFIX = 'ct1_';

/** Internal delimiter for token components (not visible in final token) */
const INTERNAL_DELIMITER = '|';

export interface ConfirmationTokenData {
  token: string;
  expiresAt: Date;
}

export class ConfirmationToken {
  private constructor(
    private readonly token: string,
    private readonly expiresAt: Date
  ) {}

  /**
   * Generate a new confirmation token for a transfer.
   *
   * Token is created using HMAC-SHA256 with:
   * - Transaction ID
   * - Destination account ID (recipient)
   * - Amount
   * - Random salt
   * - Secret key
   *
   * This ensures:
   * - Tokens are unpredictable (random salt)
   * - Tokens are tamper-proof (HMAC)
   * - Tokens are transfer-specific (bound to transaction details)
   */
  static generate(params: {
    transactionId: string;
    destinationAccountId: string;
    amount: string;
    secret: string;
    expirationHours?: number;
  }): ConfirmationTokenData {
    const salt = randomBytes(16).toString('hex');
    const expirationHours = params.expirationHours ?? DEFAULT_EXPIRATION_HOURS;
    const expiresAt = new Date(Date.now() + expirationHours * 60 * 60 * 1000);

    // Create payload for HMAC
    const signaturePayload = [
      params.transactionId,
      params.destinationAccountId,
      params.amount,
      salt,
      expiresAt.toISOString(),
    ].join(':');

    // Generate HMAC
    const hmac = createHmac('sha256', params.secret);
    hmac.update(signaturePayload);
    const signature = hmac.digest('hex');

    // Create opaque token body: transactionId|salt|expiresAt|signature
    // Using pipe delimiter internally, then base64url encode
    const tokenBody = [
      params.transactionId,
      salt,
      expiresAt.getTime().toString(),
      signature,
    ].join(INTERNAL_DELIMITER);

    // Encode to URL-safe base64 and add version prefix
    const encodedBody = Buffer.from(tokenBody).toString('base64url');
    const token = `${TOKEN_VERSION_PREFIX}${encodedBody}`;

    return { token, expiresAt };
  }

  /**
   * Parse a token string into its components.
   * Handles both v1 (ct1_...) format and legacy (dot-separated) format.
   */
  private static parseToken(token: string): {
    transactionId: string;
    salt: string;
    expiresAtMs: string;
    signature: string;
  } | null {
    // Check for v1 format (ct1_ prefix with base64url body)
    if (token.startsWith(TOKEN_VERSION_PREFIX)) {
      try {
        const encodedBody = token.slice(TOKEN_VERSION_PREFIX.length);
        const decoded = Buffer.from(encodedBody, 'base64url').toString('utf8');
        const parts = decoded.split(INTERNAL_DELIMITER);
        if (parts.length !== 4) return null;
        const [transactionId, salt, expiresAtMs, signature] = parts;
        if (!transactionId || !salt || !expiresAtMs || !signature) return null;
        return { transactionId, salt, expiresAtMs, signature };
      } catch {
        return null;
      }
    }

    // Legacy format: transactionId.salt.expiresAt.signature
    const parts = token.split('.');
    if (parts.length !== 4) return null;
    const [transactionId, salt, expiresAtMs, signature] = parts;
    if (!transactionId || !salt || !expiresAtMs || !signature) return null;
    return { transactionId, salt, expiresAtMs, signature };
  }

  /**
   * Validate a confirmation token.
   *
   * Regenerates the expected token using the same parameters
   * and compares using timing-safe comparison.
   * Supports both v1 (ct1_) and legacy token formats.
   */
  static validate(params: {
    token: string;
    transactionId: string;
    destinationAccountId: string;
    amount: string;
    secret: string;
  }): { valid: boolean; expired: boolean; error?: string } {
    try {
      // Parse token components (supports both formats)
      const parsed = this.parseToken(params.token);
      if (!parsed) {
        return { valid: false, expired: false, error: 'Invalid token format' };
      }

      const { transactionId: tokenTransactionId, salt, expiresAtMs, signature: providedSignature } = parsed;

      // Verify transaction ID matches
      if (tokenTransactionId !== params.transactionId) {
        return { valid: false, expired: false, error: 'Transaction ID mismatch' };
      }

      // Check expiration
      const expiresAt = new Date(parseInt(expiresAtMs, 10));
      if (isNaN(expiresAt.getTime())) {
        return { valid: false, expired: false, error: 'Invalid expiration timestamp' };
      }

      if (new Date() > expiresAt) {
        return { valid: false, expired: true, error: 'Token has expired' };
      }

      // Regenerate expected signature
      const signaturePayload = [
        params.transactionId,
        params.destinationAccountId,
        params.amount,
        salt,
        expiresAt.toISOString(),
      ].join(':');

      const hmac = createHmac('sha256', params.secret);
      hmac.update(signaturePayload);
      const expectedSignature = hmac.digest('hex');

      // Timing-safe comparison to prevent timing attacks
      const providedBuffer = Buffer.from(providedSignature, 'hex');
      const expectedBuffer = Buffer.from(expectedSignature, 'hex');

      if (providedBuffer.length !== expectedBuffer.length) {
        return { valid: false, expired: false, error: 'Invalid signature' };
      }

      const valid = timingSafeEqual(providedBuffer, expectedBuffer);

      if (!valid) {
        return { valid: false, expired: false, error: 'Invalid signature' };
      }

      return { valid: true, expired: false };
    } catch (error) {
      return {
        valid: false,
        expired: false,
        error: error instanceof Error ? error.message : 'Token validation failed',
      };
    }
  }

  /**
   * Extract expiration time from a token without full validation.
   * Useful for displaying expiration info to users.
   * Supports both v1 and legacy token formats.
   */
  static getExpiration(token: string): Date | null {
    try {
      const parsed = this.parseToken(token);
      if (!parsed) return null;
      const expiresAt = new Date(parseInt(parsed.expiresAtMs, 10));
      return isNaN(expiresAt.getTime()) ? null : expiresAt;
    } catch {
      return null;
    }
  }

  /**
   * Extract transaction ID from a token without full validation.
   * Useful for routing confirmation requests to the correct endpoint.
   * Supports both v1 and legacy token formats.
   */
  static getTransactionId(token: string): string | null {
    try {
      const parsed = this.parseToken(token);
      return parsed?.transactionId ?? null;
    } catch {
      return null;
    }
  }

  /**
   * Check if a token uses the new opaque format (v1).
   */
  static isOpaqueFormat(token: string): boolean {
    return token.startsWith(TOKEN_VERSION_PREFIX);
  }
}
