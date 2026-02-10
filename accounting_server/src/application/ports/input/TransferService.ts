/**
 * Transfer Service Port (Input)
 *
 * Defines the interface for P2P transfer operations.
 * Implemented by the ExecuteTransfer use case.
 */

import { Transaction } from '../../../domain/entities/Transaction';
import { AccountId, IdempotencyKey, TransactionId } from '../../../domain/value-objects/Identifiers';
import { Money } from '../../../domain/value-objects/Money';

export interface InitiateTransferCommand {
  idempotencyKey: IdempotencyKey;
  sourceAccountId: AccountId;
  destinationAccountId: AccountId;
  amount: Money;
  description?: string | undefined;
  metadata?: Record<string, unknown> | undefined;
}

export interface InitiateTransferResult {
  transaction: Transaction;
  /** Token that recipient must provide to confirm the transfer */
  confirmationToken: string;
  /** When the confirmation token expires */
  expiresAt: Date;
}

export interface ConfirmTransferCommand {
  transactionId: TransactionId;
  confirmationToken: string;
}

export interface CancelTransferCommand {
  transactionId: TransactionId;
  reason?: string | undefined;
}

export interface TransferService {
  /**
   * Initiate a P2P transfer between two accounts.
   * Funds are held from sender's account until recipient confirms.
   *
   * @returns Transaction in 'awaiting_confirmation' status with confirmation token
   * @throws InsufficientFundsError if source has insufficient balance
   * @throws AccountNotFoundError if either account doesn't exist
   * @throws InvalidAccountStateError if either account is not active
   */
  initiateTransfer(command: InitiateTransferCommand): Promise<InitiateTransferResult>;

  /**
   * Confirm a pending transfer (called by recipient).
   * Transfers the held funds to recipient's account.
   *
   * @throws TransferNotFoundError if transfer doesn't exist
   * @throws InvalidConfirmationTokenError if token is invalid or expired
   * @throws InvalidTransactionStateError if transfer is not awaiting confirmation
   */
  confirmTransfer(command: ConfirmTransferCommand): Promise<Transaction>;

  /**
   * Cancel a pending transfer (called by sender).
   * Releases the held funds back to sender's available balance.
   *
   * @throws TransferNotFoundError if transfer doesn't exist
   * @throws InvalidTransactionStateError if transfer is not awaiting confirmation
   * @throws UnauthorizedError if caller is not the sender
   */
  cancelTransfer(command: CancelTransferCommand): Promise<Transaction>;

  /**
   * Get a transfer by ID
   */
  getTransfer(transactionId: TransactionId): Promise<Transaction | null>;
}
