/**
 * Payment Provider Gateway Port (Output)
 *
 * Defines the interface for external payment provider operations.
 * Each payment provider (Stripe, PayPal, etc.) implements this interface.
 */

import { Money } from '../../../domain/value-objects/Money';
import { ProviderCode } from '../../../domain/entities/Transaction';

// ============================================
// Request Types
// ============================================

export interface CreatePaymentIntentRequest {
  amount: Money;
  currency: string;
  paymentMethodId: string;
  metadata: Record<string, string>;
  idempotencyKey: string;
}

export interface InitiateTransferRequest {
  amount: Money;
  currency: string;
  destination: {
    type: 'bank_account' | 'card' | 'wallet';
    externalId: string;
  };
  metadata: Record<string, string>;
  idempotencyKey: string;
}

export interface TokenizePaymentMethodRequest {
  providerToken: string;
  type: 'card' | 'bank_account' | 'wallet';
  metadata?: Record<string, string>;
}

export interface RefundRequest {
  externalTransactionId: string;
  amount: Money;
  reason?: string;
  metadata?: Record<string, string>;
  idempotencyKey: string;
}

// ============================================
// Response Types
// ============================================

export type PaymentIntentStatus =
  | 'requires_payment_method'
  | 'requires_confirmation'
  | 'processing'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface PaymentIntent {
  id: string;
  status: PaymentIntentStatus;
  clientSecret?: string | undefined;
  errorCode?: string | undefined;
  errorMessage?: string | undefined;
}

export interface PaymentConfirmation {
  id: string;
  status: 'succeeded' | 'failed';
  externalReference: string;
  errorCode?: string | undefined;
  errorMessage?: string | undefined;
}

export type TransferInitiationStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed';

export interface TransferInitiation {
  id: string;
  status: TransferInitiationStatus;
  estimatedArrival?: Date | undefined;
  errorCode?: string | undefined;
  errorMessage?: string | undefined;
}

export interface TransferStatus {
  id: string;
  status: TransferInitiationStatus;
  completedAt?: Date | undefined;
  failureReason?: string | undefined;
}

export interface TokenizedPaymentMethod {
  externalId: string;
  type: 'card' | 'bank_account' | 'wallet';
  displayName: string;
  isWithdrawable: boolean;
  expiresAt?: Date | undefined;
  metadata?: Record<string, unknown> | undefined;
}

export interface VerificationResult {
  verified: boolean;
  errorMessage?: string | undefined;
}

export interface RefundResult {
  id: string;
  status: 'succeeded' | 'pending' | 'failed';
  externalReference: string;
  errorCode?: string | undefined;
  errorMessage?: string | undefined;
}

// ============================================
// Webhook Types
// ============================================

export type WebhookEventType =
  | 'payment_intent.succeeded'
  | 'payment_intent.failed'
  | 'payout.paid'
  | 'payout.failed'
  | 'refund.succeeded'
  | 'refund.failed'
  | 'payment_method.verified';

export interface ProviderWebhookEvent {
  type: WebhookEventType;
  deliveryId: string;
  timestamp: Date;
  data: Record<string, unknown>;
}

// ============================================
// Gateway Interface
// ============================================

export interface PaymentProviderGateway {
  /**
   * The provider code for this gateway
   */
  readonly providerCode: ProviderCode;

  // ==========================================
  // Deposit Flow (External → Internal)
  // ==========================================

  /**
   * Create a payment intent for charging the customer
   */
  createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent>;

  /**
   * Confirm a payment intent (if manual confirmation is needed)
   */
  confirmPaymentIntent(intentId: string): Promise<PaymentConfirmation>;

  /**
   * Cancel a payment intent
   */
  cancelPaymentIntent(intentId: string): Promise<void>;

  // ==========================================
  // Withdrawal Flow (Internal → External)
  // ==========================================

  /**
   * Initiate a transfer/payout to external destination
   */
  initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation>;

  /**
   * Get the current status of a transfer
   */
  getTransferStatus(transferId: string): Promise<TransferStatus>;

  /**
   * Cancel a pending transfer (if supported)
   */
  cancelTransfer(transferId: string): Promise<void>;

  // ==========================================
  // Payment Method Management
  // ==========================================

  /**
   * Tokenize a payment method from provider's client-side token
   */
  tokenizePaymentMethod(request: TokenizePaymentMethodRequest): Promise<TokenizedPaymentMethod>;

  /**
   * Verify a payment method (e.g., micro-deposits for bank accounts)
   */
  verifyPaymentMethod(externalId: string, verificationData: unknown): Promise<VerificationResult>;

  /**
   * Delete/detach a payment method
   */
  deletePaymentMethod(externalId: string): Promise<void>;

  // ==========================================
  // Refunds
  // ==========================================

  /**
   * Create a refund for a previous charge
   */
  createRefund(request: RefundRequest): Promise<RefundResult>;

  // ==========================================
  // Webhooks
  // ==========================================

  /**
   * Verify webhook signature
   * @returns true if signature is valid
   */
  verifyWebhookSignature(payload: string, signature: string): boolean;

  /**
   * Parse webhook event from raw payload
   */
  parseWebhookEvent(payload: string): ProviderWebhookEvent;
}
