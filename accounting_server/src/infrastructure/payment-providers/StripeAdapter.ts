/**
 * Stripe Payment Provider Adapter
 *
 * Implements the PaymentProviderGateway interface for Stripe.
 * Handles deposits (charges), withdrawals (payouts), and payment method management.
 */

import Stripe from 'stripe';
import {
  PaymentProviderGateway,
  CreatePaymentIntentRequest,
  InitiateTransferRequest,
  TokenizePaymentMethodRequest,
  RefundRequest,
  PaymentIntent,
  PaymentIntentStatus,
  PaymentConfirmation,
  TransferInitiation,
  TransferInitiationStatus,
  TransferStatus,
  TokenizedPaymentMethod,
  VerificationResult,
  RefundResult,
  ProviderWebhookEvent,
  WebhookEventType,
} from '../../application/ports/output/PaymentProviderGateway';
import { ProviderCode } from '../../domain/entities/Transaction';

interface StripeAdapterConfig {
  apiKey: string;
  webhookSecret: string;
  apiVersion?: string;
}

export class StripeAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'stripe';

  private stripe: Stripe;
  private webhookSecret: string;

  constructor(config: StripeAdapterConfig) {
    this.stripe = new Stripe(config.apiKey, {
      // @ts-expect-error - API version may be newer than types
      apiVersion: config.apiVersion ?? '2024-12-18.acacia',
      typescript: true,
    });
    this.webhookSecret = config.webhookSecret;
  }

  // ==========================================
  // Deposit Flow (External → Internal)
  // ==========================================

  async createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent> {
    try {
      const intent = await this.stripe.paymentIntents.create(
        {
          amount: Number(request.amount.amount),
          currency: request.currency.toLowerCase(),
          payment_method: request.paymentMethodId,
          confirm: true,
          automatic_payment_methods: {
            enabled: true,
            allow_redirects: 'never',
          },
          metadata: request.metadata,
        },
        {
          idempotencyKey: request.idempotencyKey,
        }
      );

      return {
        id: intent.id,
        status: this.mapPaymentIntentStatus(intent.status),
        clientSecret: intent.client_secret ?? undefined,
      };
    } catch (error) {
      if (error instanceof Stripe.errors.StripeError) {
        return {
          id: '',
          status: 'failed',
          errorCode: error.code ?? 'unknown',
          errorMessage: error.message,
        };
      }
      throw error;
    }
  }

  async confirmPaymentIntent(intentId: string): Promise<PaymentConfirmation> {
    try {
      const intent = await this.stripe.paymentIntents.confirm(intentId);

      return {
        id: intent.id,
        status: intent.status === 'succeeded' ? 'succeeded' : 'failed',
        externalReference: intent.id,
        errorCode: intent.last_payment_error?.code ?? undefined,
        errorMessage: intent.last_payment_error?.message ?? undefined,
      };
    } catch (error) {
      if (error instanceof Stripe.errors.StripeError) {
        return {
          id: intentId,
          status: 'failed',
          externalReference: intentId,
          errorCode: error.code ?? 'unknown',
          errorMessage: error.message,
        };
      }
      throw error;
    }
  }

  async cancelPaymentIntent(intentId: string): Promise<void> {
    await this.stripe.paymentIntents.cancel(intentId);
  }

  // ==========================================
  // Withdrawal Flow (Internal → External)
  // ==========================================

  async initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation> {
    try {
      // Stripe uses Payouts for sending money to connected accounts or bank accounts
      const payout = await this.stripe.payouts.create(
        {
          amount: Number(request.amount.amount),
          currency: request.currency.toLowerCase(),
          destination: request.destination.externalId,
          metadata: request.metadata,
        },
        {
          idempotencyKey: request.idempotencyKey,
        }
      );

      return {
        id: payout.id,
        status: this.mapPayoutStatus(payout.status),
        estimatedArrival: payout.arrival_date
          ? new Date(payout.arrival_date * 1000)
          : undefined,
      };
    } catch (error) {
      if (error instanceof Stripe.errors.StripeError) {
        return {
          id: '',
          status: 'failed',
          errorCode: error.code ?? 'unknown',
          errorMessage: error.message,
        };
      }
      throw error;
    }
  }

  async getTransferStatus(transferId: string): Promise<TransferStatus> {
    const payout = await this.stripe.payouts.retrieve(transferId);

    return {
      id: payout.id,
      status: this.mapPayoutStatus(payout.status),
      completedAt: payout.arrival_date
        ? new Date(payout.arrival_date * 1000)
        : undefined,
      failureReason: payout.failure_message ?? undefined,
    };
  }

  async cancelTransfer(transferId: string): Promise<void> {
    await this.stripe.payouts.cancel(transferId);
  }

  // ==========================================
  // Payment Method Management
  // ==========================================

  async tokenizePaymentMethod(
    request: TokenizePaymentMethodRequest
  ): Promise<TokenizedPaymentMethod> {
    // Attach the payment method to a customer (assumes customer exists)
    // In practice, you'd create/retrieve the customer first
    const paymentMethod = await this.stripe.paymentMethods.retrieve(
      request.providerToken
    );

    let displayName: string;
    let expiresAt: Date | undefined;
    let isWithdrawable = false;

    if (paymentMethod.type === 'card' && paymentMethod.card) {
      displayName = `${this.capitalizeFirst(paymentMethod.card.brand)} •••• ${paymentMethod.card.last4}`;
      if (paymentMethod.card.exp_year && paymentMethod.card.exp_month) {
        expiresAt = new Date(
          paymentMethod.card.exp_year,
          paymentMethod.card.exp_month - 1
        );
      }
    } else if (paymentMethod.type === 'us_bank_account' && paymentMethod.us_bank_account) {
      displayName = `${paymentMethod.us_bank_account.bank_name} •••• ${paymentMethod.us_bank_account.last4}`;
      isWithdrawable = true; // Bank accounts can receive payouts
    } else {
      displayName = `${paymentMethod.type} payment method`;
    }

    return {
      externalId: paymentMethod.id,
      type: this.mapPaymentMethodType(paymentMethod.type),
      displayName,
      isWithdrawable,
      expiresAt,
      metadata: paymentMethod.metadata ?? undefined,
    };
  }

  async verifyPaymentMethod(
    externalId: string,
    verificationData: unknown
  ): Promise<VerificationResult> {
    try {
      // For bank accounts, Stripe uses micro-deposit verification
      const data = verificationData as { amounts: number[] };

      // Use the setupIntents API for micro-deposit verification
      // The payment method verification is typically done through SetupIntents
      await this.stripe.setupIntents.verifyMicrodeposits(externalId, {
        amounts: data.amounts,
      });

      return { verified: true };
    } catch (error) {
      if (error instanceof Stripe.errors.StripeError) {
        return {
          verified: false,
          errorMessage: error.message,
        };
      }
      throw error;
    }
  }

  async deletePaymentMethod(externalId: string): Promise<void> {
    await this.stripe.paymentMethods.detach(externalId);
  }

  // ==========================================
  // Refunds
  // ==========================================

  async createRefund(request: RefundRequest): Promise<RefundResult> {
    try {
      const refundParams: Stripe.RefundCreateParams = {
        payment_intent: request.externalTransactionId,
        amount: Number(request.amount.amount),
      };

      const reason = this.mapRefundReason(request.reason);
      if (reason) {
        refundParams.reason = reason;
      }

      if (request.metadata) {
        refundParams.metadata = request.metadata;
      }

      const refund = await this.stripe.refunds.create(
        refundParams,
        {
          idempotencyKey: request.idempotencyKey,
        }
      );

      return {
        id: refund.id,
        status: refund.status === 'succeeded' ? 'succeeded' : 'pending',
        externalReference: refund.id,
      };
    } catch (error) {
      if (error instanceof Stripe.errors.StripeError) {
        return {
          id: '',
          status: 'failed',
          externalReference: '',
          errorCode: error.code ?? 'unknown',
          errorMessage: error.message,
        };
      }
      throw error;
    }
  }

  // ==========================================
  // Webhooks
  // ==========================================

  verifyWebhookSignature(payload: string, signature: string): boolean {
    try {
      this.stripe.webhooks.constructEvent(payload, signature, this.webhookSecret);
      return true;
    } catch {
      return false;
    }
  }

  parseWebhookEvent(payload: string): ProviderWebhookEvent {
    const event = JSON.parse(payload) as Stripe.Event;

    return {
      type: this.mapWebhookEventType(event.type),
      deliveryId: event.id,
      timestamp: new Date(event.created * 1000),
      data: event.data.object as Record<string, unknown>,
    };
  }

  // ==========================================
  // Private Helper Methods
  // ==========================================

  private mapPaymentIntentStatus(status: Stripe.PaymentIntent.Status): PaymentIntentStatus {
    const mapping: Record<Stripe.PaymentIntent.Status, PaymentIntentStatus> = {
      requires_payment_method: 'requires_payment_method',
      requires_confirmation: 'requires_confirmation',
      requires_action: 'requires_confirmation',
      processing: 'processing',
      requires_capture: 'processing',
      canceled: 'cancelled',
      succeeded: 'succeeded',
    };
    return mapping[status] ?? 'failed';
  }

  private mapPayoutStatus(status: string): TransferInitiationStatus {
    const mapping: Record<string, TransferInitiationStatus> = {
      pending: 'pending',
      in_transit: 'processing',
      paid: 'completed',
      failed: 'failed',
      canceled: 'failed',
    };
    return mapping[status] ?? 'pending';
  }

  private mapPaymentMethodType(
    type: string
  ): 'card' | 'bank_account' | 'wallet' {
    if (type === 'card') return 'card';
    if (type === 'us_bank_account' || type === 'sepa_debit' || type === 'bacs_debit') {
      return 'bank_account';
    }
    if (type === 'apple_pay' || type === 'google_pay' || type === 'paypal') {
      return 'wallet';
    }
    return 'card'; // Default
  }

  private mapRefundReason(
    reason?: string
  ): 'duplicate' | 'fraudulent' | 'requested_by_customer' | undefined {
    if (!reason) return undefined;
    const mapping: Record<string, 'duplicate' | 'fraudulent' | 'requested_by_customer'> = {
      duplicate: 'duplicate',
      fraudulent: 'fraudulent',
      customer_request: 'requested_by_customer',
    };
    return mapping[reason];
  }

  private mapWebhookEventType(stripeType: string): WebhookEventType {
    const mapping: Record<string, WebhookEventType> = {
      'payment_intent.succeeded': 'payment_intent.succeeded',
      'payment_intent.payment_failed': 'payment_intent.failed',
      'payout.paid': 'payout.paid',
      'payout.failed': 'payout.failed',
      'charge.refunded': 'refund.succeeded',
      'refund.failed': 'refund.failed',
      'payment_method.attached': 'payment_method.verified',
    };
    return mapping[stripeType] ?? 'payment_intent.succeeded';
  }

  private capitalizeFirst(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}
