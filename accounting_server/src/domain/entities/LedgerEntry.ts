/**
 * Ledger Entry Entity
 *
 * Represents a single debit or credit entry in the double-entry ledger.
 * Immutable once created (audit requirement).
 */

import { Money } from '../value-objects/Money';
import {
  LedgerEntryId,
  TransactionId,
  AccountId,
} from '../value-objects/Identifiers';

export type EntryType = 'debit' | 'credit';

export interface LedgerEntryProps {
  id: LedgerEntryId;
  transactionId: TransactionId;
  accountId: AccountId;
  entryType: EntryType;
  amount: Money;
  balanceAfter: Money;
  createdAt: Date;
}

export class LedgerEntry {
  private constructor(private readonly props: LedgerEntryProps) {}

  // Getters (all readonly)
  get id(): LedgerEntryId {
    return this.props.id;
  }

  get transactionId(): TransactionId {
    return this.props.transactionId;
  }

  get accountId(): AccountId {
    return this.props.accountId;
  }

  get entryType(): EntryType {
    return this.props.entryType;
  }

  get amount(): Money {
    return this.props.amount;
  }

  get balanceAfter(): Money {
    return this.props.balanceAfter;
  }

  get createdAt(): Date {
    return this.props.createdAt;
  }

  /**
   * Create a debit entry
   */
  static createDebit(params: {
    transactionId: TransactionId;
    accountId: AccountId;
    amount: Money;
    balanceAfter: Money;
  }): LedgerEntry {
    return new LedgerEntry({
      id: LedgerEntryId.generate(),
      transactionId: params.transactionId,
      accountId: params.accountId,
      entryType: 'debit',
      amount: params.amount,
      balanceAfter: params.balanceAfter,
      createdAt: new Date(),
    });
  }

  /**
   * Create a credit entry
   */
  static createCredit(params: {
    transactionId: TransactionId;
    accountId: AccountId;
    amount: Money;
    balanceAfter: Money;
  }): LedgerEntry {
    return new LedgerEntry({
      id: LedgerEntryId.generate(),
      transactionId: params.transactionId,
      accountId: params.accountId,
      entryType: 'credit',
      amount: params.amount,
      balanceAfter: params.balanceAfter,
      createdAt: new Date(),
    });
  }

  /**
   * Reconstitute from persistence
   */
  static fromPersistence(props: LedgerEntryProps): LedgerEntry {
    return new LedgerEntry(props);
  }

  /**
   * Check if this is a debit entry
   */
  isDebit(): boolean {
    return this.props.entryType === 'debit';
  }

  /**
   * Check if this is a credit entry
   */
  isCredit(): boolean {
    return this.props.entryType === 'credit';
  }

  /**
   * Convert to plain object
   */
  toJSON(): Record<string, unknown> {
    return {
      id: this.props.id,
      transactionId: this.props.transactionId,
      accountId: this.props.accountId,
      entryType: this.props.entryType,
      amount: this.props.amount.toJSON(),
      balanceAfter: this.props.balanceAfter.toJSON(),
      createdAt: this.props.createdAt.toISOString(),
    };
  }
}
