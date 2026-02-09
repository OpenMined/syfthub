/**
 * Account Not Found Error
 *
 * Thrown when attempting to access an account that doesn't exist.
 */

import { DomainError } from './DomainError';
import { AccountId } from '../value-objects/Identifiers';

export class AccountNotFoundError extends DomainError {
  readonly code = 'account-not-found';
  readonly httpStatus = 404;

  constructor(public readonly accountId: AccountId) {
    super(`Account ${accountId} not found`);
  }

  override toProblemDetails(instance?: string): Record<string, unknown> {
    return {
      ...super.toProblemDetails(instance),
      account_id: this.accountId,
    };
  }
}
