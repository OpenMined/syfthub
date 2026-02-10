/**
 * Process Deposit Use Case
 *
 * Handles deposits from external payment sources into internal accounts.
 * Implements the DepositService input port.
 */

import { Transaction } from '../../domain/entities/Transaction';
import { LedgerEntry } from '../../domain/entities/LedgerEntry';
import { PaymentMethod } from '../../domain/entities/PaymentMethod';
import {
  DepositService,
  InitiateDepositCommand,
  CompleteDepositCommand,
  FailDepositCommand,
  DepositResult,
} from '../ports/input/DepositService';
import { AccountRepository } from '../ports/output/AccountRepository';
import { TransactionRepository } from '../ports/output/TransactionRepository';
import { PaymentProviderGateway } from '../ports/output/PaymentProviderGateway';
import { AccountNotFoundError } from '../../domain/errors/AccountNotFoundError';
import { InvalidAccountStateError } from '../../domain/errors/InvalidAccountStateError';
import { TransactionId } from '../../domain/value-objects/Identifiers';
import { TransactionManager } from './ExecuteTransfer';

export class PaymentMethodNotFoundError extends Error {
  constructor(id: string) {
    super(`Payment method ${id} not found`);
    this.name = 'PaymentMethodNotFoundError';
  }
}

export class InvalidPaymentMethodError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'InvalidPaymentMethodError';
  }
}

/**
 * Repository for payment methods
 */
export interface PaymentMethodRepository {
  findById(id: string): Promise<PaymentMethod | null>;
  findByAccountId(accountId: string): Promise<PaymentMethod[]>;
  save(paymentMethod: PaymentMethod): Promise<void>;
  update(paymentMethod: PaymentMethod): Promise<void>;
  delete(id: string): Promise<void>;
}

/**
 * Factory to get the appropriate payment provider
 */
export interface PaymentProviderFactory {
  getProvider(providerCode: string): PaymentProviderGateway;
}

export class ProcessDepositUseCase implements DepositService {
  constructor(
    private accountRepository: AccountRepository,
    private transactionRepository: TransactionRepository,
    private paymentMethodRepository: PaymentMethodRepository,
    private providerFactory: PaymentProviderFactory,
    private transactionManager: TransactionManager
  ) {}

  async initiateDeposit(command: InitiateDepositCommand): Promise<DepositResult> {
    // Check for existing transaction with same idempotency key
    const existing = await this.transactionRepository.findByIdempotencyKey(
      command.idempotencyKey
    );

    if (existing) {
      return {
        transaction: existing,
        requiresAction: false,
      };
    }

    // Validate account exists and is active
    const account = await this.accountRepository.findById(command.accountId);
    if (!account) {
      throw new AccountNotFoundError(command.accountId);
    }
    if (!account.canReceiveDeposit()) {
      throw new InvalidAccountStateError(
        `Account ${account.id} cannot receive deposits (status: ${account.status})`
      );
    }

    // Validate payment method
    const paymentMethod = await this.paymentMethodRepository.findById(
      command.paymentMethodId as string
    );
    if (!paymentMethod) {
      throw new PaymentMethodNotFoundError(command.paymentMethodId as string);
    }
    if (!paymentMethod.isUsable()) {
      throw new InvalidPaymentMethodError(
        `Payment method ${paymentMethod.id} is not usable (status: ${paymentMethod.status})`
      );
    }
    if (paymentMethod.accountId !== command.accountId) {
      throw new InvalidPaymentMethodError(
        'Payment method does not belong to this account'
      );
    }

    // Create pending transaction
    const depositParams: Parameters<typeof Transaction.createDeposit>[0] = {
      idempotencyKey: command.idempotencyKey,
      destinationAccountId: command.accountId,
      amount: command.amount,
      providerCode: paymentMethod.providerCode,
    };
    if (command.metadata !== undefined) {
      depositParams.metadata = command.metadata;
    }
    const transaction = Transaction.createDeposit(depositParams);

    // Save the pending transaction
    await this.transactionRepository.save(transaction);

    // Initiate payment with provider
    const provider = this.providerFactory.getProvider(paymentMethod.providerCode);

    try {
      const paymentIntent = await provider.createPaymentIntent({
        amount: command.amount,
        currency: command.amount.currency,
        paymentMethodId: paymentMethod.externalId,
        metadata: {
          transaction_id: transaction.id,
          account_id: command.accountId as string,
        },
        idempotencyKey: command.idempotencyKey as string,
      });

      // Update transaction with external reference
      transaction.setExternalReference(
        paymentIntent.id as ReturnType<typeof import('../../domain/value-objects/Identifiers').ExternalReference.from>
      );
      transaction.markProcessing();
      await this.transactionRepository.update(transaction);

      // Check if additional action is required (e.g., 3D Secure)
      const requiresAction =
        paymentIntent.status === 'requires_confirmation' ||
        paymentIntent.status === 'requires_payment_method';

      return {
        transaction,
        requiresAction,
        clientSecret: paymentIntent.clientSecret,
      };
    } catch (error) {
      // Mark transaction as failed
      transaction.fail({
        error: 'provider_error',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
      await this.transactionRepository.update(transaction);
      throw error;
    }
  }

  async completeDeposit(command: CompleteDepositCommand): Promise<Transaction> {
    return await this.transactionManager.executeInTransaction(async () => {
      // Find the transaction
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

      if (transaction.status !== 'pending' && transaction.status !== 'processing') {
        throw new Error(
          `Cannot complete transaction in ${transaction.status} status`
        );
      }

      // Lock and credit the destination account
      const account = await this.accountRepository.findByIdForUpdate(
        transaction.destinationAccountId!
      );

      if (!account) {
        throw new AccountNotFoundError(transaction.destinationAccountId!);
      }

      // Credit the account with net amount (amount - fee)
      account.credit(transaction.netAmount);

      // Create ledger entry
      const entry = LedgerEntry.createCredit({
        transactionId: transaction.id,
        accountId: account.id,
        amount: transaction.netAmount,
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

  async failDeposit(command: FailDepositCommand): Promise<Transaction> {
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
      throw new Error('Cannot fail a completed transaction');
    }

    // Mark as failed
    transaction.fail({
      reason: command.reason,
      ...command.errorDetails,
    });

    await this.transactionRepository.update(transaction);

    return transaction;
  }

  async getDeposit(transactionId: TransactionId): Promise<Transaction | null> {
    const transaction = await this.transactionRepository.findById(transactionId);

    if (transaction && transaction.type !== 'deposit') {
      return null;
    }

    return transaction;
  }
}
