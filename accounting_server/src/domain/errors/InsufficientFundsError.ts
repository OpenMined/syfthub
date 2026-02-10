/**
 * Insufficient Funds Error
 *
 * Thrown when an account doesn't have enough available balance
 * for a requested operation.
 */

import { DomainError } from './DomainError';
import { Money } from '../value-objects/Money';
import { AccountId } from '../value-objects/Identifiers';

export class InsufficientFundsError extends DomainError {
  readonly code = 'insufficient-funds';
  readonly httpStatus = 422;

  constructor(
    public readonly accountId: AccountId,
    public readonly requiredAmount: Money,
    public readonly availableAmount: Money
  ) {
    super(
      `Account ${accountId} has insufficient available balance. ` +
        `Required: ${requiredAmount}, Available: ${availableAmount}`
    );
  }

  override toProblemDetails(instance?: string): Record<string, unknown> {
    return {
      ...super.toProblemDetails(instance),
      account_id: this.accountId,
      required_amount: this.requiredAmount.toJSON(),
      available_amount: this.availableAmount.toJSON(),
    };
  }
}
