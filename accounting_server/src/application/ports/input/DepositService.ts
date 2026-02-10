/**
 * Deposit Service Port (Input)
 *
 * Defines the interface for deposit operations (external → internal).
 * Implemented by the ProcessDeposit use case.
 */

import { Transaction, ProviderCode } from '../../../domain/entities/Transaction';
import {
  AccountId,
  IdempotencyKey,
  PaymentMethodId,
  TransactionId,
} from '../../../domain/value-objects/Identifiers';
import { Money } from '../../../domain/value-objects/Money';

export interface InitiateDepositCommand {
  idempotencyKey: IdempotencyKey;
  accountId: AccountId;
  amount: Money;
  paymentMethodId: PaymentMethodId;
  metadata?: Record<string, unknown> | undefined;
}

export interface CompleteDepositCommand {
  transactionId: TransactionId;
  externalReference?: string | undefined;
}

export interface FailDepositCommand {
  transactionId: TransactionId;
  reason: string;
  errorDetails?: Record<string, unknown> | undefined;
}

export interface DepositResult {
  transaction: Transaction;
  requiresAction: boolean;
  clientSecret?: string | undefined;
}

export interface DepositService {
  /**
   * Initiate a deposit from an external payment source
   * This is async - creates pending transaction and initiates provider charge
   *
   * @returns Transaction in pending state, may include client secret for 3DS
   */
  initiateDeposit(command: InitiateDepositCommand): Promise<DepositResult>;

  /**
   * Complete a pending deposit (called via webhook)
   * Credits the user's account
   */
  completeDeposit(command: CompleteDepositCommand): Promise<Transaction>;

  /**
   * Mark a deposit as failed (called via webhook)
   */
  failDeposit(command: FailDepositCommand): Promise<Transaction>;

  /**
   * Get deposit by ID
   */
  getDeposit(transactionId: TransactionId): Promise<Transaction | null>;
}
