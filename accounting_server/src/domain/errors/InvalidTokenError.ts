/**
 * Invalid Token Error
 *
 * Thrown when an API token is invalid (expired, revoked, or malformed).
 */

import { DomainError } from './DomainError';

export type InvalidTokenReason = 'expired' | 'revoked' | 'malformed' | 'not_found';

export class InvalidTokenError extends DomainError {
  readonly code = 'invalid-token';
  readonly httpStatus = 401;
  readonly reason: InvalidTokenReason;

  constructor(reason: InvalidTokenReason, message?: string) {
    const defaultMessages: Record<InvalidTokenReason, string> = {
      expired: 'The API token has expired',
      revoked: 'The API token has been revoked',
      malformed: 'The API token is malformed',
      not_found: 'The API token was not found',
    };
    super(message ?? defaultMessages[reason]);
    this.reason = reason;
  }
}
