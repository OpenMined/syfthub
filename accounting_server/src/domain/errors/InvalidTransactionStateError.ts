/**
 * Invalid Transaction State Error
 *
 * Thrown when an operation is attempted on a transaction
 * that is not in a valid state for that operation.
 */

import { DomainError } from './DomainError';

export class InvalidTransactionStateError extends DomainError {
  readonly code = 'invalid-transaction-state';
  readonly httpStatus = 409;

  constructor(message: string) {
    super(message);
  }
}
