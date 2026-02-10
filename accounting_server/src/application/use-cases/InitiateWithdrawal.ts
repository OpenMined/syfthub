/**
 * Initiate Withdrawal Use Case
 *
 * Handles withdrawals from internal accounts to external destinations.
 * Implements the WithdrawalService input port.
 */

import { Transaction } from '../../domain/entities/Transaction';
import { LedgerEntry } from '../../domain/entities/LedgerEntry';
import {
  WithdrawalService,
  InitiateWithdrawalCommand,
  CompleteWithdrawalCommand,
  FailWithdrawalCommand,
  CancelWithdrawalCommand,
  WithdrawalResult,
} from '../ports/input/WithdrawalService';
import { AccountRepository } from '../ports/output/AccountRepository';
import { TransactionRepository } from '../ports/output/TransactionRepository';
import { AccountNotFoundError } from '../../domain/errors/AccountNotFoundError';
import { InvalidAccountStateError } from '../../domain/errors/InvalidAccountStateError';
import { InvalidTransactionStateError } from '../../domain/errors/InvalidTransactionStateError';
import { TransactionId } from '../../domain/value-objects/Identifiers';
import { TransactionManager } from './ExecuteTransfer';
import {
  PaymentMethodRepository,
  PaymentProviderFactory,
  InvalidPaymentMethodError,
  PaymentMethodNotFoundError,
} from './ProcessDeposit';

export class InitiateWithdrawalUseCase implements WithdrawalService {
  constructor(
    private accountRepository: AccountRepository,
    private transactionRepository: TransactionRepository,
    private paymentMethodRepository: PaymentMethodRepository,
    private providerFactory: PaymentProviderFactory,
    private transactionManager: TransactionManager
  ) {}

  async initiateWithdrawal(
    command: InitiateWithdrawalCommand
  ): Promise<WithdrawalResult> {
    // Check for existing transaction with same idempotency key
    const existing = await this.transactionRepository.findByIdempotencyKey(
      command.idempotencyKey
    );

    if (existing) {
      return {
        transaction: existing,
      };
    }

    // Validate payment method first (before locking account)
    const paymentMethod = await this.paymentMethodRepository.findById(
      command.paymentMethodId as string
    );

    if (!paymentMethod) {
      throw new PaymentMethodNotFoundError(command.paymentMethodId as string);
    }
    if (!paymentMethod.canWithdraw()) {
      throw new InvalidPaymentMethodError(
        `Payment method ${paymentMethod.id} cannot receive withdrawals`
      );
    }
    if (paymentMethod.accountId !== command.accountId) {
      throw new InvalidPaymentMethodError(
        'Payment method does not belong to this account'
      );
    }

    // Execute within transaction to hold funds atomically
    const transaction = await this.transactionManager.executeInTransaction(
      async () => {
        // Lock the account
        const account = await this.accountRepository.findByIdForUpdate(
          command.accountId
        );

        if (!account) {
          throw new AccountNotFoundError(command.accountId);
        }

        if (!account.canInitiateTransfer()) {
          throw new InvalidAccountStateError(
            `Account ${account.id} cannot initiate withdrawals (status: ${account.status})`
          );
        }

        // Create the withdrawal transaction (this validates sufficient balance)
        const withdrawalParams: Parameters<typeof Transaction.createWithdrawal>[0] = {
          idempotencyKey: command.idempotencyKey,
          sourceAccountId: command.accountId,
          amount: command.amount,
          providerCode: paymentMethod.providerCode,
        };
        if (command.description !== undefined) {
          withdrawalParams.description = command.description;
        }
        if (command.metadata !== undefined) {
          withdrawalParams.metadata = command.metadata;
        }
        const txn = Transaction.createWithdrawal(withdrawalParams);

        // Hold the funds (reduces available balance but not total balance)
        account.hold(command.amount);

        // Save transaction and update account
        await this.transactionRepository.save(txn);
        await this.accountRepository.update(account);

        return txn;
      }
    );

    // Initiate transfer with provider (outside the DB transaction)
    const provider = this.providerFactory.getProvider(paymentMethod.providerCode);

    try {
      const transferResult = await provider.initiateTransfer({
        amount: command.amount,
        currency: command.amount.currency,
        destination: {
          type: paymentMethod.type === 'bank_account' ? 'bank_account' :
                paymentMethod.type === 'card' ? 'card' : 'wallet',
          externalId: paymentMethod.externalId,
        },
        metadata: {
          transaction_id: transaction.id,
          account_id: command.accountId as string,
        },
        idempotencyKey: command.idempotencyKey as string,
      });

      // Update transaction with external reference and mark as processing
      transaction.setExternalReference(
        transferResult.id as ReturnType<typeof import('../../domain/value-objects/Identifiers').ExternalReference.from>
      );
      transaction.markProcessing();
      await this.transactionRepository.update(transaction);

      return {
        transaction,
        estimatedCompletion: transferResult.estimatedArrival,
      };
    } catch (error) {
      // If provider call fails, we need to release the hold
      await this.releaseHoldAndFailTransaction(
        transaction,
        error instanceof Error ? error.message : 'Provider error'
      );
      throw error;
    }
  }

  async completeWithdrawal(
    command: CompleteWithdrawalCommand
  ): Promise<Transaction> {
    return await this.transactionManager.executeInTransaction(async () => {
      const transaction = await this.transactionRepository.findById(
        command.transactionId
      );

      if (!transaction) {
        throw new Error(`Transaction ${command.transactionId} not found`);
      }

      if (transaction.status === 'completed') {
        // Already completed, return idempotently
        return transaction;
      }

      if (transaction.status !== 'processing' && transaction.status !== 'pending') {
        throw new InvalidTransactionStateError(
          `Cannot complete withdrawal in ${transaction.status} status`
        );
      }

      // Lock the account
      const account = await this.accountRepository.findByIdForUpdate(
        transaction.sourceAccountId!
      );

      if (!account) {
        throw new AccountNotFoundError(transaction.sourceAccountId!);
      }

      // Complete the held debit (reduce total balance, hold was already taken)
      account.completeHeldDebit(transaction.amount);

      // Create ledger entry
      const entry = LedgerEntry.createDebit({
        transactionId: transaction.id,
        accountId: account.id,
        amount: transaction.amount,
        balanceAfter: account.balance,
      });

      // Update external reference if provided
      if (command.externalReference) {
        transaction.setExternalReference(
          command.externalReference as ReturnType<typeof import('../../domain/value-objects/Identifiers').ExternalReference.from>
        );
      }

      // Complete the transaction
      transaction.complete([entry]);

      // Persist changes
      await this.accountRepository.update(account);
      await this.transactionRepository.update(transaction);
      await this.transactionRepository.saveLedgerEntries([entry]);

      return transaction;
    });
  }

  async failWithdrawal(command: FailWithdrawalCommand): Promise<Transaction> {
    return await this.transactionManager.executeInTransaction(async () => {
      const transaction = await this.transactionRepository.findById(
        command.transactionId
      );

      if (!transaction) {
        throw new Error(`Transaction ${command.transactionId} not found`);
      }

      if (transaction.status === 'failed') {
        // Already failed, return idempotently
        return transaction;
      }

      if (transaction.status === 'completed') {
        throw new InvalidTransactionStateError(
          'Cannot fail a completed withdrawal'
        );
      }

      // Release the held funds
      const account = await this.accountRepository.findByIdForUpdate(
        transaction.sourceAccountId!
      );

      if (account) {
        account.releaseHold(transaction.amount);
        await this.accountRepository.update(account);
      }

      // Mark transaction as failed
      transaction.fail({
        reason: command.reason,
        ...command.errorDetails,
      });

      await this.transactionRepository.update(transaction);

      return transaction;
    });
  }

  async cancelWithdrawal(command: CancelWithdrawalCommand): Promise<Transaction> {
    return await this.transactionManager.executeInTransaction(async () => {
      const transaction = await this.transactionRepository.findById(
        command.transactionId
      );

      if (!transaction) {
        throw new Error(`Transaction ${command.transactionId} not found`);
      }

      if (transaction.status !== 'pending') {
        throw new InvalidTransactionStateError(
          `Cannot cancel withdrawal in ${transaction.status} status. Only pending withdrawals can be cancelled.`
        );
      }

      // Try to cancel with provider if we have an external reference
      if (transaction.externalReference && transaction.providerCode) {
        const provider = this.providerFactory.getProvider(transaction.providerCode);
        try {
          await provider.cancelTransfer(transaction.externalReference as string);
        } catch (error) {
          // Log but don't fail - the withdrawal might already be processing
          console.warn(
            `Failed to cancel transfer with provider: ${error instanceof Error ? error.message : 'Unknown error'}`
          );
        }
      }

      // Release the held funds
      const account = await this.accountRepository.findByIdForUpdate(
        transaction.sourceAccountId!
      );

      if (account) {
        account.releaseHold(transaction.amount);
        await this.accountRepository.update(account);
      }

      // Mark transaction as failed (cancelled)
      transaction.fail({
        reason: 'cancelled_by_user',
      });

      await this.transactionRepository.update(transaction);

      return transaction;
    });
  }

  async getWithdrawal(transactionId: TransactionId): Promise<Transaction | null> {
    const transaction = await this.transactionRepository.findById(transactionId);

    if (transaction && transaction.type !== 'withdrawal') {
      return null;
    }

    return transaction;
  }

  /**
   * Helper to release hold and fail transaction when provider call fails
   */
  private async releaseHoldAndFailTransaction(
    transaction: Transaction,
    reason: string
  ): Promise<void> {
    await this.transactionManager.executeInTransaction(async () => {
      const account = await this.accountRepository.findByIdForUpdate(
        transaction.sourceAccountId!
      );

      if (account) {
        account.releaseHold(transaction.amount);
        await this.accountRepository.update(account);
      }

      transaction.fail({ reason, error: 'provider_error' });
      await this.transactionRepository.update(transaction);
    });
  }
}
