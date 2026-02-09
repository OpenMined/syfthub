/**
 * Confirmation Token Value Object
 *
 * Generates and validates secure HMAC-based tokens for transfer confirmation.
 * Tokens are time-limited and cryptographically secure.
 */

import { createHmac, randomBytes, timingSafeEqual } from 'crypto';

/** Default token expiration: 24 hours */
const DEFAULT_EXPIRATION_HOURS = 24;

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
    const payload = [
      params.transactionId,
      params.destinationAccountId,
      params.amount,
      salt,
      expiresAt.toISOString(),
    ].join(':');

    // Generate HMAC
    const hmac = createHmac('sha256', params.secret);
    hmac.update(payload);
    const signature = hmac.digest('hex');

    // Token format: transactionId.salt.expiresAt.signature
    // This allows validation without database lookup and enables
    // the recipient to call /transfers/:id/confirm with just the token
    const token = `${params.transactionId}.${salt}.${expiresAt.getTime()}.${signature}`;

    return { token, expiresAt };
  }

  /**
   * Validate a confirmation token.
   *
   * Regenerates the expected token using the same parameters
   * and compares using timing-safe comparison.
   */
  static validate(params: {
    token: string;
    transactionId: string;
    destinationAccountId: string;
    amount: string;
    secret: string;
  }): { valid: boolean; expired: boolean; error?: string } {
    try {
      // Parse token components
      // Token format: transactionId.salt.expiresAt.signature
      const parts = params.token.split('.');
      if (parts.length !== 4) {
        return { valid: false, expired: false, error: 'Invalid token format' };
      }

      const [tokenTransactionId, salt, expiresAtMs, providedSignature] = parts;

      if (!tokenTransactionId || !salt || !expiresAtMs || !providedSignature) {
        return { valid: false, expired: false, error: 'Invalid token format' };
      }

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
      const payload = [
        params.transactionId,
        params.destinationAccountId,
        params.amount,
        salt,
        expiresAt.toISOString(),
      ].join(':');

      const hmac = createHmac('sha256', params.secret);
      hmac.update(payload);
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
   */
  static getExpiration(token: string): Date | null {
    try {
      const parts = token.split('.');
      // Token format: transactionId.salt.expiresAt.signature
      if (parts.length !== 4 || !parts[2]) {
        return null;
      }
      const expiresAt = new Date(parseInt(parts[2], 10));
      return isNaN(expiresAt.getTime()) ? null : expiresAt;
    } catch {
      return null;
    }
  }

  /**
   * Extract transaction ID from a token without full validation.
   * Useful for routing confirmation requests to the correct endpoint.
   */
  static getTransactionId(token: string): string | null {
    try {
      const parts = token.split('.');
      // Token format: transactionId.salt.expiresAt.signature
      if (parts.length !== 4 || !parts[0]) {
        return null;
      }
      return parts[0];
    } catch {
      return null;
    }
  }
}
