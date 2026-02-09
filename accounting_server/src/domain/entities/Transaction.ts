/**
 * Transaction Entity (Aggregate Root)
 *
 * Represents any value movement in the system.
 * Immutable once completed (audit trail requirement).
 */

import { Money } from '../value-objects/Money';
import {
  TransactionId,
  AccountId,
  IdempotencyKey,
  ExternalReference,
} from '../value-objects/Identifiers';
import { LedgerEntry, EntryType } from './LedgerEntry';
import { InvalidTransactionStateError } from '../errors/InvalidTransactionStateError';

export type TransactionType =
  | 'transfer'
  | 'deposit'
  | 'withdrawal'
  | 'refund'
  | 'fee';

export type TransactionStatus =
  | 'pending'
  | 'awaiting_confirmation'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'reversed';

export type ProviderCode = 'stripe' | 'paypal' | 'bank_transfer' | 'pix' | 'xendit' | 'crypto' | 'manual';

export interface TransactionProps {
  id: TransactionId;
  idempotencyKey: IdempotencyKey;
  type: TransactionType;
  status: TransactionStatus;

  sourceAccountId: AccountId | null;
  destinationAccountId: AccountId | null;

  amount: Money;
  fee: Money;

  externalReference: ExternalReference | null;
  providerCode: ProviderCode | null;

  description: string;
  metadata: Record<string, unknown>;
  errorDetails: Record<string, unknown> | null;

  parentTransactionId: TransactionId | null;

  entries: LedgerEntry[];

  // Confirmation flow for transfers
  confirmationToken: string | null;
  confirmationExpiresAt: Date | null;

  createdAt: Date;
  completedAt: Date | null;
}

export class Transaction {
  private constructor(private props: TransactionProps) {}

  // Getters
  get id(): TransactionId {
    return this.props.id;
  }

  get idempotencyKey(): IdempotencyKey {
    return this.props.idempotencyKey;
  }

  get type(): TransactionType {
    return this.props.type;
  }

  get status(): TransactionStatus {
    return this.props.status;
  }

  get sourceAccountId(): AccountId | null {
    return this.props.sourceAccountId;
  }

  get destinationAccountId(): AccountId | null {
    return this.props.destinationAccountId;
  }

  get amount(): Money {
    return this.props.amount;
  }

  get fee(): Money {
    return this.props.fee;
  }

  get externalReference(): ExternalReference | null {
    return this.props.externalReference;
  }

  get providerCode(): ProviderCode | null {
    return this.props.providerCode;
  }

  get description(): string {
    return this.props.description;
  }

  get metadata(): Record<string, unknown> {
    return { ...this.props.metadata };
  }

  get errorDetails(): Record<string, unknown> | null {
    return this.props.errorDetails ? { ...this.props.errorDetails } : null;
  }

  get parentTransactionId(): TransactionId | null {
    return this.props.parentTransactionId;
  }

  get entries(): LedgerEntry[] {
    return [...this.props.entries];
  }

  get createdAt(): Date {
    return this.props.createdAt;
  }

  get completedAt(): Date | null {
    return this.props.completedAt;
  }

  get confirmationToken(): string | null {
    return this.props.confirmationToken;
  }

  get confirmationExpiresAt(): Date | null {
    return this.props.confirmationExpiresAt;
  }

  /**
   * Check if confirmation has expired
   */
  isConfirmationExpired(): boolean {
    if (!this.props.confirmationExpiresAt) return true;
    return new Date() > this.props.confirmationExpiresAt;
  }

  /**
   * Check if transfer is awaiting confirmation
   */
  isAwaitingConfirmation(): boolean {
    return this.props.status === 'awaiting_confirmation';
  }

  /**
   * Create a P2P transfer transaction
   */
  static createTransfer(params: {
    idempotencyKey: IdempotencyKey;
    sourceAccountId: AccountId;
    destinationAccountId: AccountId;
    amount: Money;
    fee?: Money;
    description?: string;
    metadata?: Record<string, unknown>;
    confirmationToken?: string;
    confirmationExpiresAt?: Date;
  }): Transaction {
    return Transaction.createTransferWithId({
      ...params,
      id: TransactionId.generate(),
    });
  }

  /**
   * Create a transfer transaction with a specified ID (used when ID needs to be known
   * before transaction creation, e.g., for confirmation token generation)
   */
  static createTransferWithId(params: {
    id: TransactionId;
    idempotencyKey: IdempotencyKey;
    sourceAccountId: AccountId;
    destinationAccountId: AccountId;
    amount: Money;
    fee?: Money;
    description?: string;
    metadata?: Record<string, unknown>;
    confirmationToken?: string;
    confirmationExpiresAt?: Date;
  }): Transaction {
    if (params.sourceAccountId === params.destinationAccountId) {
      throw new Error('Cannot transfer to the same account');
    }

    // If confirmation is required, set status to awaiting_confirmation
    const requiresConfirmation = !!params.confirmationToken;

    return new Transaction({
      id: params.id,
      idempotencyKey: params.idempotencyKey,
      type: 'transfer',
      status: requiresConfirmation ? 'awaiting_confirmation' : 'pending',
      sourceAccountId: params.sourceAccountId,
      destinationAccountId: params.destinationAccountId,
      amount: params.amount,
      fee: params.fee ?? Money.credits(0n),
      externalReference: null,
      providerCode: null,
      description: params.description ?? '',
      metadata: params.metadata ?? {},
      errorDetails: null,
      parentTransactionId: null,
      entries: [],
      confirmationToken: params.confirmationToken ?? null,
      confirmationExpiresAt: params.confirmationExpiresAt ?? null,
      createdAt: new Date(),
      completedAt: null,
    });
  }

  /**
   * Create a deposit transaction
   */
  static createDeposit(params: {
    idempotencyKey: IdempotencyKey;
    destinationAccountId: AccountId;
    amount: Money;
    providerCode: ProviderCode;
    fee?: Money;
    metadata?: Record<string, unknown>;
  }): Transaction {
    return new Transaction({
      id: TransactionId.generate(),
      idempotencyKey: params.idempotencyKey,
      type: 'deposit',
      status: 'pending',
      sourceAccountId: null,
      destinationAccountId: params.destinationAccountId,
      amount: params.amount,
      fee: params.fee ?? Money.credits(0n),
      externalReference: null,
      providerCode: params.providerCode,
      description: 'Deposit',
      metadata: params.metadata ?? {},
      errorDetails: null,
      parentTransactionId: null,
      entries: [],
      confirmationToken: null,
      confirmationExpiresAt: null,
      createdAt: new Date(),
      completedAt: null,
    });
  }

  /**
   * Create a withdrawal transaction
   */
  static createWithdrawal(params: {
    idempotencyKey: IdempotencyKey;
    sourceAccountId: AccountId;
    amount: Money;
    providerCode: ProviderCode;
    fee?: Money;
    description?: string;
    metadata?: Record<string, unknown>;
  }): Transaction {
    return new Transaction({
      id: TransactionId.generate(),
      idempotencyKey: params.idempotencyKey,
      type: 'withdrawal',
      status: 'pending',
      sourceAccountId: params.sourceAccountId,
      destinationAccountId: null,
      amount: params.amount,
      fee: params.fee ?? Money.credits(0n),
      externalReference: null,
      providerCode: params.providerCode,
      description: params.description ?? 'Withdrawal',
      metadata: params.metadata ?? {},
      errorDetails: null,
      parentTransactionId: null,
      entries: [],
      confirmationToken: null,
      confirmationExpiresAt: null,
      createdAt: new Date(),
      completedAt: null,
    });
  }

  /**
   * Create a refund transaction
   */
  static createRefund(params: {
    idempotencyKey: IdempotencyKey;
    originalTransaction: Transaction;
    amount: Money;
    description?: string;
  }): Transaction {
    if (params.amount.isGreaterThan(params.originalTransaction.amount)) {
      throw new Error('Refund amount cannot exceed original transaction amount');
    }

    // Reverse the accounts
    const sourceAccountId = params.originalTransaction.destinationAccountId;
    const destinationAccountId = params.originalTransaction.sourceAccountId;

    return new Transaction({
      id: TransactionId.generate(),
      idempotencyKey: params.idempotencyKey,
      type: 'refund',
      status: 'pending',
      sourceAccountId,
      destinationAccountId,
      amount: params.amount,
      fee: Money.credits(0n),
      externalReference: null,
      providerCode: params.originalTransaction.providerCode,
      description: params.description ?? 'Refund',
      metadata: {},
      errorDetails: null,
      parentTransactionId: params.originalTransaction.id,
      entries: [],
      confirmationToken: null,
      confirmationExpiresAt: null,
      createdAt: new Date(),
      completedAt: null,
    });
  }

  /**
   * Reconstitute from persistence
   */
  static fromPersistence(props: TransactionProps): Transaction {
    return new Transaction(props);
  }

  /**
   * Check if transaction can be modified
   */
  isModifiable(): boolean {
    return (
      this.props.status === 'pending' ||
      this.props.status === 'processing' ||
      this.props.status === 'awaiting_confirmation'
    );
  }

  /**
   * Check if transaction is in terminal state
   */
  isTerminal(): boolean {
    return (
      this.props.status === 'completed' ||
      this.props.status === 'failed' ||
      this.props.status === 'cancelled' ||
      this.props.status === 'reversed'
    );
  }

  /**
   * Check if transfer can be confirmed by recipient
   */
  canBeConfirmed(): boolean {
    return (
      this.props.type === 'transfer' &&
      this.props.status === 'awaiting_confirmation' &&
      !this.isConfirmationExpired()
    );
  }

  /**
   * Check if transfer can be cancelled by sender
   */
  canBeCancelled(): boolean {
    return (
      this.props.type === 'transfer' &&
      this.props.status === 'awaiting_confirmation'
    );
  }

  /**
   * Mark as processing
   */
  markProcessing(): void {
    this.assertModifiable();
    this.props.status = 'processing';
  }

  /**
   * Complete the transaction
   */
  complete(entries: LedgerEntry[]): void {
    this.assertModifiable();
    this.validateEntries(entries);

    this.props.status = 'completed';
    this.props.entries = entries;
    this.props.completedAt = new Date();
  }

  /**
   * Fail the transaction
   */
  fail(errorDetails: Record<string, unknown>): void {
    this.assertModifiable();
    this.props.status = 'failed';
    this.props.errorDetails = errorDetails;
    this.props.completedAt = new Date();
  }

  /**
   * Cancel a pending transfer (by sender)
   */
  cancel(reason?: string): void {
    if (!this.canBeCancelled()) {
      throw new InvalidTransactionStateError(
        `Cannot cancel transaction in ${this.props.status} status`
      );
    }
    this.props.status = 'cancelled';
    this.props.errorDetails = { reason: reason ?? 'cancelled_by_sender' };
    this.props.completedAt = new Date();
  }

  /**
   * Mark transfer as confirmed and move to processing (for completion)
   */
  confirm(): void {
    if (!this.canBeConfirmed()) {
      throw new InvalidTransactionStateError(
        `Cannot confirm transaction in ${this.props.status} status`
      );
    }
    this.props.status = 'processing';
    // Clear confirmation token after use
    this.props.confirmationToken = null;
  }

  /**
   * Reverse a completed transaction
   */
  reverse(): void {
    if (this.props.status !== 'completed') {
      throw new InvalidTransactionStateError(
        'Only completed transactions can be reversed'
      );
    }
    this.props.status = 'reversed';
  }

  /**
   * Set external reference (from provider)
   */
  setExternalReference(ref: ExternalReference): void {
    this.props.externalReference = ref;
  }

  /**
   * Update metadata
   */
  updateMetadata(metadata: Record<string, unknown>): void {
    this.props.metadata = { ...this.props.metadata, ...metadata };
  }

  /**
   * Get net amount after fees
   */
  get netAmount(): Money {
    return this.props.amount.subtract(this.props.fee);
  }

  /**
   * Convert to plain object
   */
  toJSON(): Record<string, unknown> {
    return {
      id: this.props.id,
      idempotencyKey: this.props.idempotencyKey,
      type: this.props.type,
      status: this.props.status,
      sourceAccountId: this.props.sourceAccountId,
      destinationAccountId: this.props.destinationAccountId,
      amount: this.props.amount.toJSON(),
      fee: this.props.fee.toJSON(),
      externalReference: this.props.externalReference,
      providerCode: this.props.providerCode,
      description: this.props.description,
      metadata: this.props.metadata,
      errorDetails: this.props.errorDetails,
      parentTransactionId: this.props.parentTransactionId,
      entries: this.props.entries.map((e) => e.toJSON()),
      confirmationExpiresAt: this.props.confirmationExpiresAt?.toISOString() ?? null,
      createdAt: this.props.createdAt.toISOString(),
      completedAt: this.props.completedAt?.toISOString() ?? null,
    };
  }

  private assertModifiable(): void {
    if (!this.isModifiable()) {
      throw new InvalidTransactionStateError(
        `Transaction is ${this.props.status}, cannot modify`
      );
    }
  }

  private validateEntries(entries: LedgerEntry[]): void {
    // For withdrawals and deposits, we only track one side of the entry
    // (the other side is external to our system - bank accounts, etc.)
    // Only enforce balanced entries for internal transfers
    if (this.props.type !== 'transfer') {
      // For deposits: expect only credit entries
      // For withdrawals: expect only debit entries
      if (this.props.type === 'withdrawal') {
        const hasOnlyDebits = entries.every((e) => e.entryType === 'debit');
        if (!hasOnlyDebits) {
          throw new Error('Withdrawal transactions should only have debit entries');
        }
      } else if (this.props.type === 'deposit') {
        const hasOnlyCredits = entries.every((e) => e.entryType === 'credit');
        if (!hasOnlyCredits) {
          throw new Error('Deposit transactions should only have credit entries');
        }
      }
      return;
    }

    // For transfers: validate double-entry (sum of debits = sum of credits)
    let totalDebits = Money.credits(0n);
    let totalCredits = Money.credits(0n);

    for (const entry of entries) {
      if (entry.entryType === 'debit') {
        totalDebits = totalDebits.add(entry.amount);
      } else {
        totalCredits = totalCredits.add(entry.amount);
      }
    }

    if (!totalDebits.equals(totalCredits)) {
      throw new Error(
        `Ledger entries are not balanced: debits=${totalDebits}, credits=${totalCredits}`
      );
    }
  }
}
