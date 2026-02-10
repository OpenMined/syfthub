/**
 * Withdrawal Service Port (Input)
 *
 * Defines the interface for withdrawal operations (internal → external).
 * Implemented by the InitiateWithdrawal use case.
 */

import { Transaction } from '../../../domain/entities/Transaction';
import {
  AccountId,
  IdempotencyKey,
  PaymentMethodId,
  TransactionId,
} from '../../../domain/value-objects/Identifiers';
import { Money } from '../../../domain/value-objects/Money';

export interface InitiateWithdrawalCommand {
  idempotencyKey: IdempotencyKey;
  accountId: AccountId;
  amount: Money;
  paymentMethodId: PaymentMethodId;
  description?: string | undefined;
  metadata?: Record<string, unknown> | undefined;
}

export interface CompleteWithdrawalCommand {
  transactionId: TransactionId;
  externalReference?: string | undefined;
}

export interface FailWithdrawalCommand {
  transactionId: TransactionId;
  reason: string;
  errorDetails?: Record<string, unknown> | undefined;
}

export interface CancelWithdrawalCommand {
  transactionId: TransactionId;
}

export interface WithdrawalResult {
  transaction: Transaction;
  estimatedCompletion?: Date | undefined;
}

export interface WithdrawalService {
  /**
   * Initiate a withdrawal to an external destination
   * Holds funds immediately, initiates async transfer
   *
   * @throws InsufficientFundsError if account has insufficient balance
   * @throws InvalidPaymentMethodError if payment method can't receive withdrawals
   */
  initiateWithdrawal(command: InitiateWithdrawalCommand): Promise<WithdrawalResult>;

  /**
   * Complete a pending withdrawal (called via webhook)
   * Finalizes the debit from user's account
   */
  completeWithdrawal(command: CompleteWithdrawalCommand): Promise<Transaction>;

  /**
   * Mark a withdrawal as failed (called via webhook)
   * Releases the held funds back to available balance
   */
  failWithdrawal(command: FailWithdrawalCommand): Promise<Transaction>;

  /**
   * Cancel a pending withdrawal (user-initiated)
   * Only works for withdrawals in pending state
   *
   * @throws InvalidTransactionStateError if withdrawal is already processing
   */
  cancelWithdrawal(command: CancelWithdrawalCommand): Promise<Transaction>;

  /**
   * Get withdrawal by ID
   */
  getWithdrawal(transactionId: TransactionId): Promise<Transaction | null>;
}
