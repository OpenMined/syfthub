/**
 * Base Domain Error
 *
 * All domain errors extend this class for consistent error handling.
 */

export abstract class DomainError extends Error {
  abstract readonly code: string;
  abstract readonly httpStatus: number;

  constructor(message: string) {
    super(message);
    this.name = this.constructor.name;

    // Capture stack trace if available (Node.js specific)
    if (typeof Error.captureStackTrace === 'function') {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  /**
   * Convert to RFC 9457 Problem Details format
   */
  toProblemDetails(instance?: string): Record<string, unknown> {
    return {
      type: `https://api.ledger.example.com/problems/${this.code}`,
      title: this.name.replace(/Error$/, '').replace(/([A-Z])/g, ' $1').trim(),
      status: this.httpStatus,
      detail: this.message,
      instance,
    };
  }
}
