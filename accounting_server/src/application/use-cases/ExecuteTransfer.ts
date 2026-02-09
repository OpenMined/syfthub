/**
 * Execute Transfer Use Case
 *
 * Handles P2P transfers between two internal accounts with confirmation flow.
 * Implements the TransferService input port.
 *
 * Flow:
 * 1. Sender initiates transfer → funds held, confirmation token generated
 * 2. Recipient confirms with token → funds transferred
 * 3. Sender can cancel → funds released
 */

import { Account } from '../../domain/entities/Account';
import { Transaction } from '../../domain/entities/Transaction';
import { LedgerEntry } from '../../domain/entities/LedgerEntry';
import { AccountId, TransactionId } from '../../domain/value-objects/Identifiers';
import { ConfirmationToken } from '../../domain/value-objects/ConfirmationToken';
import {
  TransferService,
  InitiateTransferCommand,
  InitiateTransferResult,
  ConfirmTransferCommand,
  CancelTransferCommand,
} from '../ports/input/TransferService';
import { AccountRepository } from '../ports/output/AccountRepository';
import { TransactionRepository } from '../ports/output/TransactionRepository';
import { AccountNotFoundError } from '../../domain/errors/AccountNotFoundError';
import { InvalidAccountStateError } from '../../domain/errors/InvalidAccountStateError';
import { InvalidTransactionStateError } from '../../domain/errors/InvalidTransactionStateError';

/**
 * Database transaction interface
 * Allows the use case to coordinate with the persistence layer
 */
export interface TransactionManager {
  executeInTransaction<T>(fn: () => Promise<T>): Promise<T>;
}

/**
 * Configuration for the transfer use case
 */
export interface TransferConfig {
  /** Secret key for HMAC-based confirmation tokens */
  confirmationTokenSecret: string;
  /** Token expiration in hours (default: 24) */
  confirmationExpirationHours?: number;
}

/**
 * Custom errors for transfer operations
 */
export class TransferNotFoundError extends Error {
  constructor(transactionId: string) {
    super(`Transfer ${transactionId} not found`);
    this.name = 'TransferNotFoundError';
  }
}

export class InvalidConfirmationTokenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'InvalidConfirmationTokenError';
  }
}

export class ExecuteTransferUseCase implements TransferService {
  constructor(
    private accountRepository: AccountRepository,
    private transactionRepository: TransactionRepository,
    private transactionManager: TransactionManager,
    private config: TransferConfig
  ) {}

  async initiateTransfer(command: InitiateTransferCommand): Promise<InitiateTransferResult> {
    // Check for existing transaction with same idempotency key
    const existing = await this.transactionRepository.findByIdempotencyKey(
      command.idempotencyKey
    );

    if (existing) {
      // Return existing transaction (idempotent response)
      // Note: We can't return the original token, but the transaction is already created
      return {
        transaction: existing,
        confirmationToken: existing.confirmationToken ?? '',
        expiresAt: existing.confirmationExpiresAt ?? new Date(),
      };
    }

    // Execute initiation within a database transaction
    return await this.transactionManager.executeInTransaction(async () => {
      // Lock source account only (we're just holding funds)
      const sourceAccount = await this.accountRepository.findByIdForUpdate(
        command.sourceAccountId
      );

      if (!sourceAccount) {
        throw new AccountNotFoundError(command.sourceAccountId);
      }

      // Validate destination account exists (don't need to lock it yet)
      const destinationAccount = await this.accountRepository.findById(
        command.destinationAccountId
      );

      if (!destinationAccount) {
        throw new AccountNotFoundError(command.destinationAccountId);
      }

      // Validate account states
      if (!sourceAccount.canInitiateTransfer()) {
        throw new InvalidAccountStateError(
          `Source account ${sourceAccount.id} is ${sourceAccount.status}`
        );
      }
      if (!destinationAccount.canReceiveDeposit()) {
        throw new InvalidAccountStateError(
          `Destination account ${destinationAccount.id} is ${destinationAccount.status}`
        );
      }

      // Generate a transaction ID first so we can use it for both token and transaction
      const transactionId = TransactionId.generate();

      // Generate confirmation token using the actual transaction ID
      const expirationHours = this.config.confirmationExpirationHours ?? 24;
      const tokenData = ConfirmationToken.generate({
        transactionId: transactionId.toString(),
        destinationAccountId: command.destinationAccountId.toString(),
        amount: command.amount.amount.toString(),
        secret: this.config.confirmationTokenSecret,
        expirationHours,
      });

      // Build transfer params - only include optional fields if defined
      const transferParams: Parameters<typeof Transaction.createTransferWithId>[0] = {
        id: transactionId,
        idempotencyKey: command.idempotencyKey,
        sourceAccountId: command.sourceAccountId,
        destinationAccountId: command.destinationAccountId,
        amount: command.amount,
        confirmationToken: tokenData.token,
        confirmationExpiresAt: tokenData.expiresAt,
      };
      if (command.description !== undefined) {
        transferParams.description = command.description;
      }
      if (command.metadata !== undefined) {
        transferParams.metadata = command.metadata;
      }

      // Create the transaction in awaiting_confirmation status
      const transaction = Transaction.createTransferWithId(transferParams);

      // Hold funds from source account
      sourceAccount.hold(command.amount);

      // Persist changes
      await this.accountRepository.update(sourceAccount);
      await this.transactionRepository.save(transaction);

      return {
        transaction,
        confirmationToken: tokenData.token,
        expiresAt: tokenData.expiresAt,
      };
    });
  }

  async confirmTransfer(command: ConfirmTransferCommand): Promise<Transaction> {
    // Find the transaction
    const transaction = await this.transactionRepository.findById(command.transactionId);

    if (!transaction || transaction.type !== 'transfer') {
      throw new TransferNotFoundError(command.transactionId.toString());
    }

    // Check if already completed (idempotent)
    if (transaction.status === 'completed') {
      return transaction;
    }

    // Validate transaction state
    if (!transaction.canBeConfirmed()) {
      throw new InvalidTransactionStateError(
        `Transfer ${transaction.id} cannot be confirmed (status: ${transaction.status})`
      );
    }

    // Validate confirmation token
    const validation = ConfirmationToken.validate({
      token: command.confirmationToken,
      transactionId: transaction.id.toString(),
      destinationAccountId: transaction.destinationAccountId!.toString(),
      amount: transaction.amount.amount.toString(),
      secret: this.config.confirmationTokenSecret,
    });

    if (!validation.valid) {
      if (validation.expired) {
        throw new InvalidConfirmationTokenError('Confirmation token has expired');
      }
      throw new InvalidConfirmationTokenError(validation.error ?? 'Invalid confirmation token');
    }

    // Execute the actual transfer within a database transaction
    return await this.transactionManager.executeInTransaction(async () => {
      // Lock both accounts in consistent order to prevent deadlocks
      const accounts = await this.lockAccountsInOrder(
        transaction.sourceAccountId!,
        transaction.destinationAccountId!
      );

      const sourceAccount = accounts.get(transaction.sourceAccountId!);
      const destinationAccount = accounts.get(transaction.destinationAccountId!);

      if (!sourceAccount || !destinationAccount) {
        throw new AccountNotFoundError(
          !sourceAccount
            ? transaction.sourceAccountId!
            : transaction.destinationAccountId!
        );
      }

      // Mark transaction as confirmed (moves to 'processing')
      transaction.confirm();

      // Complete the held debit (balance -= amount, hold is released)
      sourceAccount.completeHeldDebit(transaction.amount);

      // Credit destination account
      destinationAccount.credit(transaction.amount);

      // Create ledger entries
      const entries = this.createLedgerEntries(
        transaction,
        sourceAccount,
        destinationAccount
      );

      // Complete the transaction
      transaction.complete(entries);

      // Persist everything
      await this.accountRepository.update(sourceAccount);
      await this.accountRepository.update(destinationAccount);
      await this.transactionRepository.update(transaction);
      await this.transactionRepository.saveLedgerEntries(entries);

      return transaction;
    });
  }

  async cancelTransfer(command: CancelTransferCommand): Promise<Transaction> {
    // Find the transaction
    const transaction = await this.transactionRepository.findById(command.transactionId);

    if (!transaction || transaction.type !== 'transfer') {
      throw new TransferNotFoundError(command.transactionId.toString());
    }

    // Check if already cancelled (idempotent)
    if (transaction.status === 'cancelled') {
      return transaction;
    }

    // Validate transaction can be cancelled
    if (!transaction.canBeCancelled()) {
      throw new InvalidTransactionStateError(
        `Transfer ${transaction.id} cannot be cancelled (status: ${transaction.status})`
      );
    }

    // Execute cancellation within a database transaction
    return await this.transactionManager.executeInTransaction(async () => {
      // Lock the source account to release the hold
      const sourceAccount = await this.accountRepository.findByIdForUpdate(
        transaction.sourceAccountId!
      );

      if (!sourceAccount) {
        throw new AccountNotFoundError(transaction.sourceAccountId!);
      }

      // Release the held funds
      sourceAccount.releaseHold(transaction.amount);

      // Cancel the transaction
      transaction.cancel(command.reason);

      // Persist changes
      await this.accountRepository.update(sourceAccount);
      await this.transactionRepository.update(transaction);

      return transaction;
    });
  }

  async getTransfer(transactionId: TransactionId): Promise<Transaction | null> {
    const transaction = await this.transactionRepository.findById(transactionId);

    if (transaction && transaction.type !== 'transfer') {
      return null;
    }

    return transaction;
  }

  /**
   * Lock accounts in consistent order (by ID) to prevent deadlocks
   */
  private async lockAccountsInOrder(
    sourceId: AccountId,
    destinationId: AccountId
  ): Promise<Map<AccountId, Account>> {
    const sortedIds = [sourceId, destinationId].sort();
    const accounts = await this.accountRepository.findByIdsForUpdate(sortedIds);

    const accountMap = new Map<AccountId, Account>();
    for (const account of accounts) {
      accountMap.set(account.id, account);
    }

    return accountMap;
  }

  /**
   * Create double-entry ledger entries for the transfer
   */
  private createLedgerEntries(
    transaction: Transaction,
    sourceAccount: Account,
    destinationAccount: Account
  ): LedgerEntry[] {
    const entries: LedgerEntry[] = [];

    // Debit entry for source account
    entries.push(
      LedgerEntry.createDebit({
        transactionId: transaction.id,
        accountId: sourceAccount.id,
        amount: transaction.amount,
        balanceAfter: sourceAccount.balance,
      })
    );

    // Credit entry for destination account
    entries.push(
      LedgerEntry.createCredit({
        transactionId: transaction.id,
        accountId: destinationAccount.id,
        amount: transaction.amount,
        balanceAfter: destinationAccount.balance,
      })
    );

    return entries;
  }
}
