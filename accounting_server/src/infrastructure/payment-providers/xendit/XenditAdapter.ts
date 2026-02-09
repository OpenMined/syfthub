/**
 * Xendit Payment Provider Adapter
 *
 * Implements the PaymentProviderGateway interface for Xendit.
 * Supports payments, payouts, refunds across Southeast Asia
 * (Indonesia, Philippines, Vietnam, Thailand, Malaysia).
 */

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
} from '../../../application/ports/output/PaymentProviderGateway';
import { ProviderCode } from '../../../domain/entities/Transaction';
import {
  XenditConfig,
  XenditCreatePaymentRequest,
  XenditPaymentRequestResponse,
  XenditPaymentStatus,
  XenditPayoutStatus,
  XenditCreatePayoutRequest,
  XenditPayoutResponse,
  XenditCreateRefundRequest,
  XenditRefundResponse,
  XenditWebhookPayload,
  XenditWebhookEventType,
  XenditChannelCode,
  XenditCreateInvoiceRequest,
  XenditInvoiceResponse,
  XenditCreateVirtualAccountRequest,
  XenditVirtualAccountResponse,
  getCurrencyForCountry,
} from './XenditTypes';

const XENDIT_API_VERSION = '2024-11-11';

export class XenditAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'xendit';

  private readonly config: XenditConfig;
  private readonly authHeader: string;

  constructor(config: XenditConfig) {
    this.config = config;
    // Xendit uses Basic Auth with API key as username and empty password
    this.authHeader = `Basic ${Buffer.from(`${config.apiKey}:`).toString('base64')}`;
  }

  // ==========================================
  // Public Getters
  // ==========================================

  get defaultCountry() {
    return this.config.defaultCountry;
  }

  get defaultCurrency() {
    return this.config.defaultCurrency;
  }

  get successRedirectUrl() {
    return this.config.successRedirectUrl;
  }

  get failureRedirectUrl() {
    return this.config.failureRedirectUrl;
  }

  // ==========================================
  // Deposit Flow (External → Internal)
  // ==========================================

  async createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent> {
    try {
      const channelCode = this.extractChannelCode(request.metadata);

      const xenditRequest: XenditCreatePaymentRequest = {
        reference_id: request.idempotencyKey,
        type: 'PAY',
        country: this.config.defaultCountry,
        currency: this.config.defaultCurrency,
        request_amount: Number(request.amount.amount),
        capture_method: 'AUTOMATIC',
        channel_code: channelCode,
        channel_properties: {
          success_return_url: this.config.successRedirectUrl,
          failure_return_url: this.config.failureRedirectUrl,
        },
        description: request.metadata['description'] ?? undefined,
        metadata: {
          ...request.metadata,
          transaction_id: request.metadata['transaction_id'] ?? request.idempotencyKey,
        },
      };

      const response = await this.makeRequest<XenditPaymentRequestResponse>(
        'POST',
        '/v3/payment_requests',
        xenditRequest,
        request.idempotencyKey
      );

      return {
        id: response.id,
        status: this.mapPaymentStatus(response.status),
        clientSecret: response.actions?.[0]?.value,
      };
    } catch (error) {
      return this.handlePaymentError(error);
    }
  }

  async confirmPaymentIntent(intentId: string): Promise<PaymentConfirmation> {
    try {
      // Xendit's v3 Payment Request API uses automatic capture by default
      // For manual capture, we would call POST /v3/payment_requests/{id}/capture
      const response = await this.makeRequest<XenditPaymentRequestResponse>(
        'GET',
        `/v3/payment_requests/${intentId}`
      );

      return {
        id: response.id,
        status: response.status === 'SUCCEEDED' || response.status === 'CAPTURED' ? 'succeeded' : 'failed',
        externalReference: response.id,
        errorCode: response.failure_code,
      };
    } catch (error) {
      return {
        id: intentId,
        status: 'failed',
        externalReference: intentId,
        errorCode: error instanceof Error ? error.message : 'unknown',
      };
    }
  }

  async cancelPaymentIntent(intentId: string): Promise<void> {
    // Xendit doesn't have a direct cancel endpoint for payment requests
    // We can void authorized payments
    try {
      await this.makeRequest<void>(
        'POST',
        `/v3/payment_requests/${intentId}/void`
      );
    } catch {
      // If void fails, the payment will eventually expire
    }
  }

  // ==========================================
  // Withdrawal Flow (Internal → External)
  // ==========================================

  async initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation> {
    try {
      const destinationInfo = this.parseDestinationInfo(request.destination);

      const xenditRequest: XenditCreatePayoutRequest = {
        reference_id: request.idempotencyKey,
        channel_code: destinationInfo.channelCode,
        channel_properties: {
          account_holder_name: destinationInfo.accountHolderName,
          account_number: destinationInfo.accountNumber,
          account_type: destinationInfo.accountType,
        },
        amount: Number(request.amount.amount),
        currency: this.config.defaultCurrency,
        description: request.metadata['description'] ?? undefined,
        metadata: {
          ...request.metadata,
          transaction_id: request.metadata['transaction_id'] ?? request.idempotencyKey,
        },
      };

      const response = await this.makeRequest<XenditPayoutResponse>(
        'POST',
        '/v2/payouts',
        xenditRequest,
        request.idempotencyKey
      );

      return {
        id: response.id,
        status: this.mapPayoutStatus(response.status),
        estimatedArrival: response.estimated_arrival_time
          ? new Date(response.estimated_arrival_time)
          : undefined,
      };
    } catch (error) {
      return {
        id: '',
        status: 'failed',
        errorCode: error instanceof Error ? error.message : 'unknown',
        errorMessage: error instanceof Error ? error.message : 'Payout failed',
      };
    }
  }

  async getTransferStatus(transferId: string): Promise<TransferStatus> {
    const response = await this.makeRequest<XenditPayoutResponse>(
      'GET',
      `/v2/payouts/${transferId}`
    );

    return {
      id: response.id,
      status: this.mapPayoutStatus(response.status),
      completedAt: response.status === 'SUCCEEDED' ? new Date(response.updated) : undefined,
      failureReason: response.failure_code,
    };
  }

  async cancelTransfer(transferId: string): Promise<void> {
    await this.makeRequest<void>(
      'POST',
      `/v2/payouts/${transferId}/cancel`
    );
  }

  // ==========================================
  // Payment Method Management
  // ==========================================

  async tokenizePaymentMethod(
    request: TokenizePaymentMethodRequest
  ): Promise<TokenizedPaymentMethod> {
    // Xendit uses Payment Tokens for recurring payments
    // For one-time payments, payment method details are sent directly
    // This implementation stores the channel info for future use

    const channelCode = request.metadata?.['channel_code'] as XenditChannelCode ?? 'CARDS';
    const methodType = this.mapChannelToMethodType(channelCode);

    return {
      externalId: request.providerToken,
      type: methodType,
      displayName: this.getChannelDisplayName(channelCode),
      isWithdrawable: this.isChannelWithdrawable(channelCode),
      metadata: {
        channel_code: channelCode,
        country: this.config.defaultCountry,
      },
    };
  }

  async verifyPaymentMethod(
    _externalId: string,
    _verificationData: unknown
  ): Promise<VerificationResult> {
    // Xendit payment methods are typically verified during the payment flow
    // No separate verification step is required for most channels
    return { verified: true };
  }

  async deletePaymentMethod(_externalId: string): Promise<void> {
    // Xendit payment tokens can be expired/deactivated via the dashboard
    // or through the Payment Token API
    // For now, this is a no-op as tokens expire automatically
  }

  // ==========================================
  // Refunds
  // ==========================================

  async createRefund(request: RefundRequest): Promise<RefundResult> {
    try {
      const xenditRequest: XenditCreateRefundRequest = {
        payment_id: request.externalTransactionId,
        reference_id: request.idempotencyKey,
        amount: Number(request.amount.amount),
        reason: this.mapRefundReason(request.reason),
        metadata: request.metadata,
      };

      const response = await this.makeRequest<XenditRefundResponse>(
        'POST',
        '/refunds',
        xenditRequest,
        request.idempotencyKey
      );

      return {
        id: response.id,
        status: response.status === 'SUCCEEDED' ? 'succeeded' : response.status === 'PENDING' ? 'pending' : 'failed',
        externalReference: response.id,
        errorCode: response.failure_code,
      };
    } catch (error) {
      return {
        id: '',
        status: 'failed',
        externalReference: '',
        errorCode: error instanceof Error ? error.message : 'unknown',
        errorMessage: error instanceof Error ? error.message : 'Refund failed',
      };
    }
  }

  // ==========================================
  // Webhooks
  // ==========================================

  verifyWebhookSignature(_payload: string, signature: string): boolean {
    // Xendit uses x-callback-token header for webhook verification
    // The token should match the configured webhook token
    return signature === this.config.webhookToken;
  }

  parseWebhookEvent(payload: string): ProviderWebhookEvent {
    const event = JSON.parse(payload) as XenditWebhookPayload;

    return {
      type: this.mapWebhookEventType(event.event),
      deliveryId: this.extractDeliveryId(event),
      timestamp: new Date(event.created),
      data: event.data as Record<string, unknown>,
    };
  }

  // ==========================================
  // Xendit-Specific Methods
  // ==========================================

  /**
   * Create an invoice (payment link)
   */
  async createInvoice(params: {
    externalId: string;
    amount: number;
    currency?: string | undefined;
    payerEmail?: string | undefined;
    description?: string | undefined;
    durationSeconds?: number | undefined;
    paymentMethods?: string[] | undefined;
    metadata?: Record<string, string> | undefined;
  }): Promise<XenditInvoiceResponse> {
    const request: XenditCreateInvoiceRequest = {
      external_id: params.externalId,
      amount: params.amount,
      currency: (params.currency as XenditInvoiceResponse['currency']) ?? this.config.defaultCurrency,
      payer_email: params.payerEmail,
      description: params.description,
      invoice_duration: params.durationSeconds,
      success_redirect_url: this.config.successRedirectUrl,
      failure_redirect_url: this.config.failureRedirectUrl,
      payment_methods: params.paymentMethods,
      metadata: params.metadata,
    };

    return this.makeRequest<XenditInvoiceResponse>(
      'POST',
      '/v2/invoices',
      request,
      params.externalId
    );
  }

  /**
   * Get invoice by ID
   */
  async getInvoice(invoiceId: string): Promise<XenditInvoiceResponse | null> {
    try {
      return await this.makeRequest<XenditInvoiceResponse>(
        'GET',
        `/v2/invoices/${invoiceId}`
      );
    } catch {
      return null;
    }
  }

  /**
   * Expire an invoice
   */
  async expireInvoice(invoiceId: string): Promise<XenditInvoiceResponse> {
    return this.makeRequest<XenditInvoiceResponse>(
      'POST',
      `/invoices/${invoiceId}/expire!`
    );
  }

  /**
   * Create a virtual account for receiving payments
   */
  async createVirtualAccount(params: {
    externalId: string;
    bankCode: string;
    name: string;
    expectedAmount?: number | undefined;
    expirationDate?: Date | undefined;
    isClosed?: boolean | undefined;
    isSingleUse?: boolean | undefined;
  }): Promise<XenditVirtualAccountResponse> {
    const request: XenditCreateVirtualAccountRequest = {
      external_id: params.externalId,
      bank_code: params.bankCode,
      name: params.name,
      expected_amount: params.expectedAmount,
      expiration_date: params.expirationDate?.toISOString(),
      is_closed: params.isClosed ?? false,
      is_single_use: params.isSingleUse ?? false,
      country: this.config.defaultCountry,
      currency: getCurrencyForCountry(this.config.defaultCountry),
    };

    return this.makeRequest<XenditVirtualAccountResponse>(
      'POST',
      '/callback_virtual_accounts',
      request,
      params.externalId
    );
  }

  /**
   * Get virtual account by ID
   */
  async getVirtualAccount(vaId: string): Promise<XenditVirtualAccountResponse | null> {
    try {
      return await this.makeRequest<XenditVirtualAccountResponse>(
        'GET',
        `/callback_virtual_accounts/${vaId}`
      );
    } catch {
      return null;
    }
  }

  /**
   * Get available payment channels for a country
   */
  async getAvailableChannels(country?: string): Promise<XenditChannelCode[]> {
    const targetCountry = country ?? this.config.defaultCountry;

    // Return pre-configured channel list based on country
    const channelsByCountry: Record<string, XenditChannelCode[]> = {
      ID: [
        'CARDS',
        'BCA_VIRTUAL_ACCOUNT',
        'BNI_VIRTUAL_ACCOUNT',
        'BRI_VIRTUAL_ACCOUNT',
        'MANDIRI_VIRTUAL_ACCOUNT',
        'OVO',
        'DANA',
        'SHOPEEPAY',
        'LINKAJA',
        'GOPAY',
        'QRIS',
      ],
      PH: [
        'CARDS',
        'GCASH',
        'GRABPAY',
        'PAYMAYA',
        'BPI_VIRTUAL_ACCOUNT',
        'BDO_VIRTUAL_ACCOUNT',
      ],
      VN: ['CARDS', 'MOMO', 'ZALOPAY', 'VNPAY'],
      TH: ['CARDS', 'TRUEMONEY', 'PROMPTPAY'],
      MY: ['CARDS'],
    };

    return channelsByCountry[targetCountry] ?? ['CARDS'];
  }

  // ==========================================
  // Private Helper Methods
  // ==========================================

  private async makeRequest<T>(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    body?: unknown,
    idempotencyKey?: string
  ): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;

    const headers: Record<string, string> = {
      Authorization: this.authHeader,
      'Content-Type': 'application/json',
      'api-version': XENDIT_API_VERSION,
    };

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    if (this.config.businessId) {
      headers['for-user-id'] = this.config.businessId;
    }

    const fetchOptions: RequestInit = {
      method,
      headers,
    };

    if (body) {
      fetchOptions.body = JSON.stringify(body);
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error_code: 'UNKNOWN', message: response.statusText })) as { error_code?: string; message?: string };
      throw new XenditApiError(errorData.error_code ?? 'UNKNOWN', errorData.message ?? 'Request failed', response.status);
    }

    // Handle empty responses (204 No Content)
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  private extractChannelCode(metadata: Record<string, string>): XenditChannelCode {
    const channelCode = metadata['channel_code'];
    if (channelCode) {
      return channelCode as XenditChannelCode;
    }
    // Default to cards if no channel specified
    return 'CARDS';
  }

  private parseDestinationInfo(destination: {
    type: 'bank_account' | 'card' | 'wallet';
    externalId: string;
  }): {
    channelCode: string;
    accountHolderName: string;
    accountNumber: string;
    accountType: 'BANK_ACCOUNT' | 'MOBILE_NO' | undefined;
  } {
    // externalId format: "CHANNEL_CODE:ACCOUNT_NUMBER:ACCOUNT_HOLDER_NAME"
    const parts = destination.externalId.split(':');

    if (parts.length >= 3) {
      return {
        channelCode: parts[0] ?? '',
        accountNumber: parts[1] ?? '',
        accountHolderName: parts.slice(2).join(':'),
        accountType: destination.type === 'bank_account' ? 'BANK_ACCOUNT' : 'MOBILE_NO',
      };
    }

    // Fallback: treat externalId as account number
    return {
      channelCode: this.getDefaultPayoutChannel(),
      accountNumber: destination.externalId,
      accountHolderName: 'Unknown',
      accountType: destination.type === 'bank_account' ? 'BANK_ACCOUNT' : undefined,
    };
  }

  private getDefaultPayoutChannel(): string {
    const channelByCountry: Record<string, string> = {
      ID: 'ID_BCA',
      PH: 'PH_BPI',
      VN: 'VN_VIETCOMBANK',
      TH: 'TH_SCB',
      MY: 'MY_MAYBANK',
    };
    return channelByCountry[this.config.defaultCountry] ?? 'ID_BCA';
  }

  private mapPaymentStatus(status: XenditPaymentStatus): PaymentIntentStatus {
    const mapping: Record<XenditPaymentStatus, PaymentIntentStatus> = {
      PENDING: 'processing',
      REQUIRES_ACTION: 'requires_confirmation',
      AUTHORIZED: 'requires_confirmation',
      CAPTURED: 'succeeded',
      SUCCEEDED: 'succeeded',
      FAILED: 'failed',
      VOIDED: 'cancelled',
      EXPIRED: 'failed',
    };
    return mapping[status] ?? 'failed';
  }

  private mapPayoutStatus(status: XenditPayoutStatus): TransferInitiationStatus {
    const mapping: Record<XenditPayoutStatus, TransferInitiationStatus> = {
      PENDING: 'pending',
      ACCEPTED: 'pending',
      LOCKED: 'processing',
      REQUESTED: 'processing',
      SUCCEEDED: 'completed',
      FAILED: 'failed',
      CANCELLED: 'failed',
      REVERSED: 'failed',
    };
    return mapping[status] ?? 'pending';
  }

  private mapRefundReason(reason?: string): 'FRAUDULENT' | 'DUPLICATE' | 'REQUESTED_BY_CUSTOMER' | 'CANCELLATION' | 'OTHERS' {
    if (!reason) return 'OTHERS';

    const mapping: Record<string, 'FRAUDULENT' | 'DUPLICATE' | 'REQUESTED_BY_CUSTOMER' | 'CANCELLATION' | 'OTHERS'> = {
      fraudulent: 'FRAUDULENT',
      duplicate: 'DUPLICATE',
      customer_request: 'REQUESTED_BY_CUSTOMER',
      cancellation: 'CANCELLATION',
    };
    return mapping[reason.toLowerCase()] ?? 'OTHERS';
  }

  private mapWebhookEventType(xenditEvent: XenditWebhookEventType): WebhookEventType {
    const mapping: Record<XenditWebhookEventType, WebhookEventType> = {
      'payment.capture': 'payment_intent.succeeded',
      'payment.authorization': 'payment_intent.succeeded',
      'payment.failure': 'payment_intent.failed',
      'payment_token.activation': 'payment_method.verified',
      'payment_token.failure': 'payment_intent.failed',
      'payment_token.expiry': 'payment_intent.failed',
      'payout.succeeded': 'payout.paid',
      'payout.failed': 'payout.failed',
      'refund.succeeded': 'refund.succeeded',
      'refund.failed': 'refund.failed',
      'invoice.paid': 'payment_intent.succeeded',
      'invoice.expired': 'payment_intent.failed',
      'fva.created': 'payment_method.verified',
      'fva.paid': 'payment_intent.succeeded',
      'fva.expired': 'payment_intent.failed',
    };
    return mapping[xenditEvent] ?? 'payment_intent.succeeded';
  }

  private extractDeliveryId(event: XenditWebhookPayload): string {
    // Xendit doesn't provide a unique delivery ID in webhooks
    // Generate one from the event data
    const data = event.data as Record<string, unknown>;
    const id = data['payment_id'] ?? data['id'] ?? data['payment_request_id'];
    return `${event.event}-${id}-${Date.now()}`;
  }

  private mapChannelToMethodType(channelCode: XenditChannelCode): 'card' | 'bank_account' | 'wallet' {
    if (channelCode === 'CARDS') return 'card';

    if (channelCode.includes('VIRTUAL_ACCOUNT') || channelCode.includes('DIRECT_DEBIT')) {
      return 'bank_account';
    }

    // E-wallets and QR codes
    return 'wallet';
  }

  private getChannelDisplayName(channelCode: XenditChannelCode): string {
    const displayNames: Partial<Record<XenditChannelCode, string>> = {
      CARDS: 'Credit/Debit Card',
      BCA_VIRTUAL_ACCOUNT: 'BCA Virtual Account',
      BNI_VIRTUAL_ACCOUNT: 'BNI Virtual Account',
      BRI_VIRTUAL_ACCOUNT: 'BRI Virtual Account',
      MANDIRI_VIRTUAL_ACCOUNT: 'Mandiri Virtual Account',
      OVO: 'OVO',
      DANA: 'DANA',
      SHOPEEPAY: 'ShopeePay',
      LINKAJA: 'LinkAja',
      GOPAY: 'GoPay',
      GCASH: 'GCash',
      GRABPAY: 'GrabPay',
      PAYMAYA: 'Maya',
      MOMO: 'MoMo',
      ZALOPAY: 'ZaloPay',
      VNPAY: 'VNPay',
      TRUEMONEY: 'TrueMoney',
      QRIS: 'QRIS',
      PROMPTPAY: 'PromptPay',
    };
    return displayNames[channelCode] ?? channelCode;
  }

  private isChannelWithdrawable(channelCode: XenditChannelCode): boolean {
    // Bank accounts and some e-wallets support payouts
    const withdrawableChannels: XenditChannelCode[] = [
      'BCA_VIRTUAL_ACCOUNT',
      'BNI_VIRTUAL_ACCOUNT',
      'BRI_VIRTUAL_ACCOUNT',
      'MANDIRI_VIRTUAL_ACCOUNT',
      'BDO_VIRTUAL_ACCOUNT',
      'BPI_VIRTUAL_ACCOUNT',
      'UNIONBANK_VIRTUAL_ACCOUNT',
      'OVO',
      'DANA',
      'GOPAY',
      'GCASH',
      'PAYMAYA',
    ];
    return withdrawableChannels.includes(channelCode);
  }

  private handlePaymentError(error: unknown): PaymentIntent {
    if (error instanceof XenditApiError) {
      return {
        id: '',
        status: 'failed',
        errorCode: error.code,
        errorMessage: error.message,
      };
    }

    return {
      id: '',
      status: 'failed',
      errorCode: 'unknown',
      errorMessage: error instanceof Error ? error.message : 'Payment failed',
    };
  }
}

/**
 * Custom error class for Xendit API errors
 */
export class XenditApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly httpStatus: number
  ) {
    super(message);
    this.name = 'XenditApiError';
  }
}
