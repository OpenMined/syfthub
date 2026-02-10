/**
 * Account Entity (Aggregate Root)
 *
 * Represents a user's account holding internal credits.
 * Maintains balance integrity through controlled operations.
 */

import { Money } from '../value-objects/Money';
import { AccountId, UserId } from '../value-objects/Identifiers';
import { InsufficientFundsError } from '../errors/InsufficientFundsError';
import { InvalidAccountStateError } from '../errors/InvalidAccountStateError';

export type AccountType = 'user' | 'system' | 'escrow';
export type AccountStatus = 'active' | 'frozen' | 'closed';

export interface AccountProps {
  id: AccountId;
  userId: UserId;
  type: AccountType;
  status: AccountStatus;
  balance: Money;
  availableBalance: Money;
  metadata: Record<string, unknown>;
  createdAt: Date;
  updatedAt: Date;
  version: number;
}

export class Account {
  private constructor(private props: AccountProps) {}

  // Getters
  get id(): AccountId {
    return this.props.id;
  }

  get userId(): UserId {
    return this.props.userId;
  }

  get type(): AccountType {
    return this.props.type;
  }

  get status(): AccountStatus {
    return this.props.status;
  }

  get balance(): Money {
    return this.props.balance;
  }

  get availableBalance(): Money {
    return this.props.availableBalance;
  }

  get metadata(): Record<string, unknown> {
    return { ...this.props.metadata };
  }

  get createdAt(): Date {
    return this.props.createdAt;
  }

  get updatedAt(): Date {
    return this.props.updatedAt;
  }

  get version(): number {
    return this.props.version;
  }

  /**
   * Create a new account
   */
  static create(params: {
    userId: UserId;
    type: AccountType;
    metadata?: Record<string, unknown>;
  }): Account {
    const now = new Date();
    return new Account({
      id: AccountId.generate(),
      userId: params.userId,
      type: params.type,
      status: 'active',
      balance: Money.credits(0n),
      availableBalance: Money.credits(0n),
      metadata: params.metadata ?? {},
      createdAt: now,
      updatedAt: now,
      version: 1,
    });
  }

  /**
   * Reconstitute from persistence
   */
  static fromPersistence(props: AccountProps): Account {
    return new Account(props);
  }

  /**
   * Check if account can accept deposits
   */
  canReceiveDeposit(): boolean {
    return this.props.status === 'active';
  }

  /**
   * Check if account can initiate transfers/withdrawals
   */
  canInitiateTransfer(): boolean {
    return this.props.status === 'active';
  }

  /**
   * Check if account has sufficient available balance
   */
  hasSufficientBalance(amount: Money): boolean {
    return this.props.availableBalance.isGreaterThanOrEqual(amount);
  }

  /**
   * Credit the account (increase balance)
   * Used for deposits and incoming transfers
   */
  credit(amount: Money): void {
    this.assertActive();

    this.props.balance = this.props.balance.add(amount);
    this.props.availableBalance = this.props.availableBalance.add(amount);
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Debit the account (decrease balance)
   * Used for completed withdrawals and outgoing transfers
   */
  debit(amount: Money): void {
    this.assertActive();
    this.assertSufficientBalance(amount);

    this.props.balance = this.props.balance.subtract(amount);
    this.props.availableBalance = this.props.availableBalance.subtract(amount);
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Hold funds (reduce available balance but not total balance)
   * Used for pending withdrawals
   */
  hold(amount: Money): void {
    this.assertActive();
    this.assertSufficientAvailableBalance(amount);

    this.props.availableBalance = this.props.availableBalance.subtract(amount);
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Release held funds (increase available balance)
   * Used when cancelling withdrawals
   */
  releaseHold(amount: Money): void {
    this.props.availableBalance = this.props.availableBalance.add(amount);

    // Ensure available doesn't exceed total
    if (this.props.availableBalance.isGreaterThan(this.props.balance)) {
      this.props.availableBalance = this.props.balance;
    }

    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Complete a held withdrawal (reduce total balance)
   * Funds were already held, now complete the debit
   */
  completeHeldDebit(amount: Money): void {
    this.props.balance = this.props.balance.subtract(amount);
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Freeze the account
   */
  freeze(): void {
    if (this.props.status === 'closed') {
      throw new InvalidAccountStateError('Cannot freeze a closed account');
    }
    this.props.status = 'frozen';
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Unfreeze the account
   */
  unfreeze(): void {
    if (this.props.status !== 'frozen') {
      throw new InvalidAccountStateError('Account is not frozen');
    }
    this.props.status = 'active';
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Close the account
   */
  close(): void {
    if (!this.props.balance.isZero()) {
      throw new InvalidAccountStateError(
        'Cannot close account with non-zero balance'
      );
    }
    this.props.status = 'closed';
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Update metadata
   */
  updateMetadata(metadata: Record<string, unknown>): void {
    this.props.metadata = { ...this.props.metadata, ...metadata };
    this.props.updatedAt = new Date();
    this.props.version++;
  }

  /**
   * Get pending amount (difference between balance and available)
   */
  get pendingAmount(): Money {
    return this.props.balance.subtract(this.props.availableBalance);
  }

  /**
   * Convert to plain object for serialization
   */
  toJSON(): Record<string, unknown> {
    return {
      id: this.props.id,
      userId: this.props.userId,
      type: this.props.type,
      status: this.props.status,
      balance: this.props.balance.toJSON(),
      availableBalance: this.props.availableBalance.toJSON(),
      metadata: this.props.metadata,
      createdAt: this.props.createdAt.toISOString(),
      updatedAt: this.props.updatedAt.toISOString(),
      version: this.props.version,
    };
  }

  private assertActive(): void {
    if (this.props.status !== 'active') {
      throw new InvalidAccountStateError(
        `Account is ${this.props.status}, cannot perform operation`
      );
    }
  }

  private assertSufficientBalance(amount: Money): void {
    if (!this.hasSufficientBalance(amount)) {
      throw new InsufficientFundsError(
        this.props.id,
        amount,
        this.props.availableBalance
      );
    }
  }

  private assertSufficientAvailableBalance(amount: Money): void {
    if (this.props.availableBalance.isLessThan(amount)) {
      throw new InsufficientFundsError(
        this.props.id,
        amount,
        this.props.availableBalance
      );
    }
  }
}
