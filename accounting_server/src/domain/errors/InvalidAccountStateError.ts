/**
 * Invalid Account State Error
 *
 * Thrown when an operation is attempted on an account
 * that is not in a valid state for that operation.
 */

import { DomainError } from './DomainError';

export class InvalidAccountStateError extends DomainError {
  readonly code = 'invalid-account-state';
  readonly httpStatus = 409;

  constructor(message: string) {
    super(message);
  }
}
