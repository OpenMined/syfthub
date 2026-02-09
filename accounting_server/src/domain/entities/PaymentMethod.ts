/**
 * Payment Method Entity
 *
 * Represents a linked external payment source or destination.
 * Stores tokenized references to provider payment methods.
 */

import {
  PaymentMethodId,
  AccountId,
} from '../value-objects/Identifiers';
import { ProviderCode } from './Transaction';

export type PaymentMethodType = 'card' | 'bank_account' | 'wallet' | 'crypto';
export type PaymentMethodStatus = 'pending_verification' | 'verified' | 'disabled';

export interface PaymentMethodProps {
  id: PaymentMethodId;
  accountId: AccountId;
  providerCode: ProviderCode;
  type: PaymentMethodType;
  status: PaymentMethodStatus;
  externalId: string;
  displayName: string;
  isDefault: boolean;
  isWithdrawable: boolean;
  metadata: Record<string, unknown>;
  expiresAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}

export class PaymentMethod {
  private constructor(private props: PaymentMethodProps) {}

  // Getters
  get id(): PaymentMethodId {
    return this.props.id;
  }

  get accountId(): AccountId {
    return this.props.accountId;
  }

  get providerCode(): ProviderCode {
    return this.props.providerCode;
  }

  get type(): PaymentMethodType {
    return this.props.type;
  }

  get status(): PaymentMethodStatus {
    return this.props.status;
  }

  get externalId(): string {
    return this.props.externalId;
  }

  get displayName(): string {
    return this.props.displayName;
  }

  get isDefault(): boolean {
    return this.props.isDefault;
  }

  get isWithdrawable(): boolean {
    return this.props.isWithdrawable;
  }

  get metadata(): Record<string, unknown> {
    return { ...this.props.metadata };
  }

  get expiresAt(): Date | null {
    return this.props.expiresAt;
  }

  get createdAt(): Date {
    return this.props.createdAt;
  }

  get updatedAt(): Date {
    return this.props.updatedAt;
  }

  /**
   * Create a new payment method
   */
  static create(params: {
    accountId: AccountId;
    providerCode: ProviderCode;
    type: PaymentMethodType;
    externalId: string;
    displayName: string;
    isWithdrawable?: boolean | undefined;
    expiresAt?: Date | undefined;
    metadata?: Record<string, unknown> | undefined;
  }): PaymentMethod {
    const now = new Date();
    return new PaymentMethod({
      id: PaymentMethodId.generate(),
      accountId: params.accountId,
      providerCode: params.providerCode,
      type: params.type,
      status: 'pending_verification',
      externalId: params.externalId,
      displayName: params.displayName,
      isDefault: false,
      isWithdrawable: params.isWithdrawable ?? false,
      metadata: params.metadata ?? {},
      expiresAt: params.expiresAt ?? null,
      createdAt: now,
      updatedAt: now,
    });
  }

  /**
   * Reconstitute from persistence
   */
  static fromPersistence(props: PaymentMethodProps): PaymentMethod {
    return new PaymentMethod(props);
  }

  /**
   * Check if payment method is usable
   */
  isUsable(): boolean {
    if (this.props.status !== 'verified') {
      return false;
    }

    if (this.props.expiresAt && this.props.expiresAt < new Date()) {
      return false;
    }

    return true;
  }

  /**
   * Check if can be used for withdrawals
   */
  canWithdraw(): boolean {
    return this.isUsable() && this.props.isWithdrawable;
  }

  /**
   * Mark as verified
   */
  verify(): void {
    this.props.status = 'verified';
    this.props.updatedAt = new Date();
  }

  /**
   * Disable the payment method
   */
  disable(): void {
    this.props.status = 'disabled';
    this.props.updatedAt = new Date();
  }

  /**
   * Set as default
   */
  setDefault(isDefault: boolean): void {
    this.props.isDefault = isDefault;
    this.props.updatedAt = new Date();
  }

  /**
   * Update display name
   */
  updateDisplayName(displayName: string): void {
    this.props.displayName = displayName;
    this.props.updatedAt = new Date();
  }

  /**
   * Convert to plain object
   */
  toJSON(): Record<string, unknown> {
    return {
      id: this.props.id,
      accountId: this.props.accountId,
      providerCode: this.props.providerCode,
      type: this.props.type,
      status: this.props.status,
      displayName: this.props.displayName,
      isDefault: this.props.isDefault,
      isWithdrawable: this.props.isWithdrawable,
      metadata: this.props.metadata,
      expiresAt: this.props.expiresAt?.toISOString() ?? null,
      createdAt: this.props.createdAt.toISOString(),
      updatedAt: this.props.updatedAt.toISOString(),
    };
  }
}
