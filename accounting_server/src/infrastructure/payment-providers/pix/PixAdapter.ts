/**
 * PIX Payment Provider Adapter
 *
 * Implements the PaymentProviderGateway interface for Brazilian PIX.
 * Supports deposits via QR codes, withdrawals via PIX keys, and refunds.
 *
 * This is a generic implementation that can work with different PSPs.
 * The actual API calls are abstracted through the PixApiClient.
 */

import https from 'https';
import crypto from 'crypto';
import {
  PaymentProviderGateway,
  CreatePaymentIntentRequest,
  InitiateTransferRequest,
  TokenizePaymentMethodRequest,
  RefundRequest,
  PaymentIntent,
  PaymentConfirmation,
  TransferInitiation,
  TransferStatus,
  TokenizedPaymentMethod,
  VerificationResult,
  RefundResult,
  ProviderWebhookEvent,
  WebhookEventType,
} from '../../../application/ports/output/PaymentProviderGateway';
import { ProviderCode } from '../../../domain/entities/Transaction';
import {
  PixPspConfig,
  PixCharge,
  PixChargeStatus,
  PixTransfer,
  PixTransferStatus,
  PixKeyType,
  PixKeyLookupResult,
  PixQrCode,
  CreateDynamicQrCodeRequest,
  generatePixTxid,
  isValidPixKey,
  PixWebhookEventType,
} from './PixTypes';

/**
 * PIX API Client interface
 * Abstract interface for different PSP implementations
 */
interface PixApiClient {
  // Authentication
  getAccessToken(): Promise<string>;

  // Charges (Cobranças)
  createCharge(txid: string, amount: number, expiresInSeconds: number, description?: string): Promise<PixCharge>;
  getCharge(txid: string): Promise<PixCharge | null>;
  cancelCharge(txid: string): Promise<void>;

  // Transfers (Cash-out)
  initiateTransfer(keyType: PixKeyType, keyValue: string, amount: number, description?: string, idempotencyKey?: string): Promise<PixTransfer>;
  getTransferStatus(transferId: string): Promise<PixTransfer | null>;

  // Key lookup
  lookupPixKey(keyType: PixKeyType, keyValue: string): Promise<PixKeyLookupResult | null>;

  // Refunds
  createRefund(endToEndId: string, amount: number, refundId: string): Promise<{ id: string; status: string }>;

  // QR Code generation
  generateQrCode(charge: PixCharge): Promise<PixQrCode>;
}

/**
 * PIX Adapter implementing PaymentProviderGateway
 */
export class PixAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'pix';

  private _config: PixPspConfig;
  private apiClient: PixApiClient;
  private accessToken: string | null = null;
  private tokenExpiresAt: Date | null = null;

  constructor(config: PixPspConfig) {
    this._config = config;
    this.apiClient = this.createApiClient(config);
  }

  /**
   * Get the PIX receiver key configured for this adapter
   */
  get receiverPixKey(): string {
    return this._config.receiverPixKey;
  }

  /**
   * Get merchant information
   */
  get merchantInfo(): { name: string; city: string } {
    return {
      name: this._config.merchantName,
      city: this._config.merchantCity,
    };
  }

  // ==========================================
  // Deposit Flow (PIX Cash-in via QR Code)
  // ==========================================

  async createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent> {
    try {
      // Generate unique transaction ID
      const txid = generatePixTxid();

      // Create PIX charge (cobrança imediata)
      const charge = await this.apiClient.createCharge(
        txid,
        Number(request.amount.amount),
        3600, // 1 hour expiration
        request.metadata['description'] as string
      );

      // Generate QR code
      const qrCode = await this.apiClient.generateQrCode(charge);

      // The "client_secret" for PIX is the QR code payload that the payer scans
      return {
        id: charge.txid,
        status: this.mapChargeStatusToPaymentIntent(charge.status),
        clientSecret: qrCode.payload,
        // Store QR code info in a way the client can use
        // errorMessage is repurposed to carry QR code URL for the client
        errorMessage: qrCode.qrCodeUrl ?? qrCode.qrCodeBase64,
      };
    } catch (error) {
      return {
        id: '',
        status: 'failed',
        errorCode: 'pix_error',
        errorMessage: error instanceof Error ? error.message : 'Failed to create PIX charge',
      };
    }
  }

  async confirmPaymentIntent(intentId: string): Promise<PaymentConfirmation> {
    try {
      // For PIX, we check if the charge has been paid
      const charge = await this.apiClient.getCharge(intentId);

      if (!charge) {
        return {
          id: intentId,
          status: 'failed',
          externalReference: intentId,
          errorCode: 'charge_not_found',
          errorMessage: 'PIX charge not found',
        };
      }

      return {
        id: charge.txid,
        status: charge.status === 'completed' ? 'succeeded' : 'failed',
        externalReference: charge.endToEndId ?? charge.txid,
        errorCode: charge.status !== 'completed' ? 'not_paid' : undefined,
        errorMessage: charge.status !== 'completed' ? `Charge status: ${charge.status}` : undefined,
      };
    } catch (error) {
      return {
        id: intentId,
        status: 'failed',
        externalReference: intentId,
        errorCode: 'pix_error',
        errorMessage: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  async cancelPaymentIntent(intentId: string): Promise<void> {
    await this.apiClient.cancelCharge(intentId);
  }

  // ==========================================
  // Withdrawal Flow (PIX Cash-out)
  // ==========================================

  async initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation> {
    try {
      // Extract PIX key info from destination
      // The destination.externalId should contain: "keyType:keyValue"
      const [keyType, keyValue] = this.parsePixKeyFromDestination(request.destination.externalId);

      if (!keyType || !keyValue) {
        return {
          id: '',
          status: 'failed',
          errorCode: 'invalid_destination',
          errorMessage: 'Invalid PIX key format. Expected "type:value"',
        };
      }

      // Validate PIX key format
      if (!isValidPixKey(keyType, keyValue)) {
        return {
          id: '',
          status: 'failed',
          errorCode: 'invalid_pix_key',
          errorMessage: `Invalid ${keyType} PIX key format`,
        };
      }

      // Initiate PIX transfer
      const transfer = await this.apiClient.initiateTransfer(
        keyType,
        keyValue,
        Number(request.amount.amount),
        request.metadata['description'] as string,
        request.idempotencyKey
      );

      return {
        id: transfer.id,
        status: this.mapPixTransferStatus(transfer.status),
        // PIX is instant, so estimated arrival is now
        estimatedArrival: new Date(),
        errorCode: transfer.status === 'failed' ? 'transfer_failed' : undefined,
        errorMessage: transfer.failureReason,
      };
    } catch (error) {
      return {
        id: '',
        status: 'failed',
        errorCode: 'pix_error',
        errorMessage: error instanceof Error ? error.message : 'Failed to initiate PIX transfer',
      };
    }
  }

  async getTransferStatus(transferId: string): Promise<TransferStatus> {
    const transfer = await this.apiClient.getTransferStatus(transferId);

    if (!transfer) {
      return {
        id: transferId,
        status: 'failed',
        failureReason: 'Transfer not found',
      };
    }

    return {
      id: transfer.id,
      status: this.mapPixTransferStatus(transfer.status),
      completedAt: transfer.completedAt,
      failureReason: transfer.failureReason,
    };
  }

  async cancelTransfer(transferId: string): Promise<void> {
    // PIX transfers are instant and cannot be cancelled once initiated
    // We can only attempt a refund request
    throw new Error('PIX transfers cannot be cancelled. They are processed instantly.');
  }

  // ==========================================
  // Payment Method Management (PIX Keys)
  // ==========================================

  async tokenizePaymentMethod(request: TokenizePaymentMethodRequest): Promise<TokenizedPaymentMethod> {
    // For PIX, the "token" is the PIX key in format "type:value"
    const [keyType, keyValue] = request.providerToken.split(':') as [PixKeyType | undefined, string | undefined];

    if (!keyType || !keyValue) {
      throw new Error('Invalid PIX key format. Expected "type:value" (e.g., "cpf:12345678901")');
    }

    if (!isValidPixKey(keyType, keyValue)) {
      throw new Error(`Invalid ${keyType} PIX key format`);
    }

    // Lookup the PIX key in DICT to verify it exists
    const keyInfo = await this.apiClient.lookupPixKey(keyType, keyValue);

    if (!keyInfo) {
      throw new Error('PIX key not found in DICT');
    }

    // Mask sensitive information
    const maskedValue = this.maskPixKey(keyType, keyValue);

    return {
      externalId: `${keyType}:${keyValue}`,
      type: 'bank_account', // PIX keys are associated with bank accounts
      displayName: `PIX ${keyType.toUpperCase()} •••• ${maskedValue}`,
      isWithdrawable: true, // PIX keys can receive transfers
      metadata: {
        keyType,
        holderName: keyInfo.holderName,
        bankName: keyInfo.bankName,
        verifiedAt: keyInfo.verifiedAt?.toISOString(),
      },
    };
  }

  async verifyPaymentMethod(
    externalId: string,
    verificationData: unknown
  ): Promise<VerificationResult> {
    // PIX key verification is done during tokenization via DICT lookup
    // Additional verification could include micro-deposit or document verification

    const [keyType, keyValue] = externalId.split(':') as [PixKeyType | undefined, string | undefined];

    if (!keyType || !keyValue) {
      return {
        verified: false,
        errorMessage: 'Invalid PIX key format',
      };
    }

    // Verify key exists in DICT
    const keyInfo = await this.apiClient.lookupPixKey(keyType, keyValue);

    if (!keyInfo) {
      return {
        verified: false,
        errorMessage: 'PIX key not found',
      };
    }

    return { verified: true };
  }

  async deletePaymentMethod(externalId: string): Promise<void> {
    // PIX keys are registered with banks, not with our platform
    // We just remove our reference to it
    // No actual API call needed
  }

  // ==========================================
  // Refunds (Devolução PIX)
  // ==========================================

  async createRefund(request: RefundRequest): Promise<RefundResult> {
    try {
      const refundId = generatePixTxid();

      const result = await this.apiClient.createRefund(
        request.externalTransactionId,
        Number(request.amount.amount),
        refundId
      );

      return {
        id: result.id,
        status: result.status === 'completed' ? 'succeeded' : 'pending',
        externalReference: result.id,
      };
    } catch (error) {
      return {
        id: '',
        status: 'failed',
        externalReference: '',
        errorCode: 'refund_failed',
        errorMessage: error instanceof Error ? error.message : 'Failed to create PIX refund',
      };
    }
  }

  // ==========================================
  // Webhooks
  // ==========================================

  verifyWebhookSignature(payload: string, signature: string): boolean {
    // PIX webhooks use HMAC-SHA256 or certificate-based verification
    // depending on the PSP
    const expectedSignature = crypto
      .createHmac('sha256', this._config.webhookSecret)
      .update(payload)
      .digest('hex');

    return crypto.timingSafeEqual(
      Buffer.from(signature),
      Buffer.from(expectedSignature)
    );
  }

  parseWebhookEvent(payload: string): ProviderWebhookEvent {
    const data = JSON.parse(payload);

    // Map PIX webhook event types to our standard types
    const eventTypeMap: Record<PixWebhookEventType, WebhookEventType> = {
      'pix.received': 'payment_intent.succeeded',
      'charge.paid': 'payment_intent.succeeded',
      'pix.sent': 'payout.paid',
      'pix.failed': 'payout.failed',
      'pix.returned': 'payout.failed',
      'charge.expired': 'payment_intent.failed',
      'refund.completed': 'refund.succeeded',
      'refund.failed': 'refund.failed',
    };

    const pixEventType = data.evento || data.event_type || 'pix.received';
    const mappedType = eventTypeMap[pixEventType as PixWebhookEventType] ?? 'payment_intent.succeeded';

    return {
      type: mappedType,
      deliveryId: data.id || data.delivery_id || crypto.randomUUID(),
      timestamp: new Date(data.timestamp || data.horario || Date.now()),
      data: {
        endToEndId: data.endToEndId || data.e2e_id,
        txid: data.txid,
        amount: data.valor || data.amount,
        transaction_id: data.metadata?.transaction_id,
        ...data,
      },
    };
  }

  // ==========================================
  // PIX-Specific Public Methods
  // ==========================================

  /**
   * Create a static QR code for receiving multiple payments
   */
  async createStaticQrCode(
    amount?: number,
    description?: string
  ): Promise<PixQrCode> {
    // Static QR codes use the BR Code standard
    const payload = this.generateBrCode({
      pixKey: this._config.receiverPixKey,
      merchantName: this._config.merchantName,
      merchantCity: this._config.merchantCity,
      amount,
      description,
    });

    return {
      id: crypto.randomUUID(),
      type: 'static',
      payload,
      pixKey: this._config.receiverPixKey,
      merchantName: this._config.merchantName,
      merchantCity: this._config.merchantCity,
      amount,
      description,
      createdAt: new Date(),
    };
  }

  /**
   * Create a dynamic QR code for a single payment
   */
  async createDynamicQrCode(request: CreateDynamicQrCodeRequest): Promise<PixQrCode> {
    const txid = generatePixTxid();

    const charge = await this.apiClient.createCharge(
      txid,
      request.amount,
      request.expiresInSeconds,
      request.description
    );

    return this.apiClient.generateQrCode(charge);
  }

  /**
   * Lookup a PIX key in the DICT directory
   */
  async lookupPixKey(keyType: PixKeyType, keyValue: string): Promise<PixKeyLookupResult | null> {
    return this.apiClient.lookupPixKey(keyType, keyValue);
  }

  /**
   * Create a PIX charge (cobranca)
   */
  async createCharge(params: {
    amount: number;
    expiresInSeconds: number;
    description?: string | undefined;
    payerDocument?: string | undefined;
    payerName?: string | undefined;
    metadata?: Record<string, string> | undefined;
    idempotencyKey?: string | undefined;
  }): Promise<PixCharge> {
    const txid = generatePixTxid();

    const charge = await this.apiClient.createCharge(
      txid,
      params.amount,
      params.expiresInSeconds,
      params.description
    );

    // Generate QR code
    const qrCode = await this.apiClient.generateQrCode(charge);

    return {
      ...charge,
      payerDocument: params.payerDocument,
      payerName: params.payerName,
      qrCode,
    };
  }

  /**
   * Get a PIX charge by txid
   */
  async getCharge(txid: string): Promise<PixCharge | null> {
    return this.apiClient.getCharge(txid);
  }

  // ==========================================
  // Private Helper Methods
  // ==========================================

  private createApiClient(config: PixPspConfig): PixApiClient {
    // Create PSP-specific API client
    // This is a generic implementation - in production, you'd have
    // specific implementations for each PSP (Efí, Itaú, etc.)
    return new GenericPixApiClient(config);
  }

  private parsePixKeyFromDestination(externalId: string): [PixKeyType | undefined, string | undefined] {
    const parts = externalId.split(':');
    if (parts.length !== 2) {
      return [undefined, undefined];
    }
    return [parts[0] as PixKeyType, parts[1]];
  }

  private maskPixKey(type: PixKeyType, value: string): string {
    switch (type) {
      case 'cpf':
        return value.slice(-4);
      case 'cnpj':
        return value.slice(-4);
      case 'email':
        const [local, domain] = value.split('@');
        return `${local?.slice(0, 2)}***@${domain}`;
      case 'phone':
        return value.slice(-4);
      case 'evp':
        return value.slice(-8);
      default:
        return '****';
    }
  }

  private mapChargeStatusToPaymentIntent(status: PixChargeStatus): 'processing' | 'succeeded' | 'failed' | 'requires_confirmation' {
    switch (status) {
      case 'active':
        return 'requires_confirmation';
      case 'completed':
        return 'succeeded';
      case 'expired':
      case 'cancelled':
      case 'refunded':
        return 'failed';
      default:
        return 'processing';
    }
  }

  private mapPixTransferStatus(status: PixTransferStatus): 'pending' | 'processing' | 'completed' | 'failed' {
    switch (status) {
      case 'pending':
        return 'pending';
      case 'processing':
        return 'processing';
      case 'completed':
        return 'completed';
      case 'failed':
      case 'returned':
        return 'failed';
      default:
        return 'pending';
    }
  }

  /**
   * Generate BR Code payload (EMV standard)
   * Based on BCB specification for PIX QR codes
   */
  private generateBrCode(params: {
    pixKey: string;
    merchantName: string;
    merchantCity: string;
    amount?: number | undefined;
    description?: string | undefined;
    txid?: string | undefined;
  }): string {
    const tlv = (id: string, value: string): string => {
      const length = value.length.toString().padStart(2, '0');
      return `${id}${length}${value}`;
    };

    // Build the payload
    let payload = '';

    // Payload Format Indicator
    payload += tlv('00', '01');

    // Merchant Account Information (PIX)
    let merchantAccount = '';
    merchantAccount += tlv('00', 'br.gov.bcb.pix'); // GUI
    merchantAccount += tlv('01', params.pixKey); // PIX Key
    if (params.description) {
      merchantAccount += tlv('02', params.description.slice(0, 25)); // Description
    }
    payload += tlv('26', merchantAccount);

    // Merchant Category Code
    payload += tlv('52', '0000');

    // Transaction Currency (986 = BRL)
    payload += tlv('53', '986');

    // Transaction Amount (optional for static)
    if (params.amount) {
      const amountStr = (params.amount / 100).toFixed(2);
      payload += tlv('54', amountStr);
    }

    // Country Code
    payload += tlv('58', 'BR');

    // Merchant Name
    payload += tlv('59', params.merchantName.slice(0, 25));

    // Merchant City
    payload += tlv('60', params.merchantCity.slice(0, 15));

    // Additional Data (txid)
    if (params.txid) {
      const additionalData = tlv('05', params.txid);
      payload += tlv('62', additionalData);
    }

    // CRC16 placeholder
    payload += '6304';

    // Calculate CRC16
    const crc = this.calculateCRC16(payload);
    payload = payload.slice(0, -4) + tlv('63', crc);

    return payload;
  }

  /**
   * Calculate CRC16-CCITT for BR Code
   */
  private calculateCRC16(payload: string): string {
    let crc = 0xFFFF;
    const polynomial = 0x1021;

    for (let i = 0; i < payload.length; i++) {
      crc ^= payload.charCodeAt(i) << 8;
      for (let j = 0; j < 8; j++) {
        if (crc & 0x8000) {
          crc = (crc << 1) ^ polynomial;
        } else {
          crc <<= 1;
        }
        crc &= 0xFFFF;
      }
    }

    return crc.toString(16).toUpperCase().padStart(4, '0');
  }
}

/**
 * Generic PIX API Client implementation
 * This can be extended for specific PSPs
 */
class GenericPixApiClient implements PixApiClient {
  private config: PixPspConfig;
  private accessToken: string | null = null;
  private tokenExpiresAt: Date | null = null;

  constructor(config: PixPspConfig) {
    this.config = config;
  }

  async getAccessToken(): Promise<string> {
    // Check if we have a valid cached token
    if (this.accessToken && this.tokenExpiresAt && this.tokenExpiresAt > new Date()) {
      return this.accessToken;
    }

    // Request new token using OAuth2 client credentials
    const credentials = Buffer.from(`${this.config.clientId}:${this.config.clientSecret}`).toString('base64');

    const response = await this.request<{ access_token: string; expires_in: number }>(
      'POST',
      '/oauth/token',
      { grant_type: 'client_credentials' },
      { Authorization: `Basic ${credentials}` }
    );

    this.accessToken = response.access_token;
    this.tokenExpiresAt = new Date(Date.now() + (response.expires_in - 60) * 1000);

    return this.accessToken;
  }

  async createCharge(
    txid: string,
    amount: number,
    expiresInSeconds: number,
    description?: string
  ): Promise<PixCharge> {
    const token = await this.getAccessToken();

    const response = await this.request<{
      txid: string;
      status: string;
      calendario: { expiracao: number };
      valor: { original: string };
      chave: string;
      loc?: { id: number; location: string };
    }>(
      'PUT',
      `/v2/cob/${txid}`,
      {
        calendario: { expiracao: expiresInSeconds },
        valor: { original: (amount / 100).toFixed(2) },
        chave: this.config.receiverPixKey,
        infoAdicionais: description ? [{ nome: 'descricao', valor: description }] : undefined,
      },
      { Authorization: `Bearer ${token}` }
    );

    return {
      id: response.txid,
      txid: response.txid,
      status: response.status as PixChargeStatus,
      pixKey: response.chave,
      amount,
      description,
      expiresAt: new Date(Date.now() + expiresInSeconds * 1000),
      createdAt: new Date(),
      qrCode: {
        id: response.loc?.id.toString() ?? response.txid,
        type: 'dynamic',
        payload: '', // Will be filled by generateQrCode
        pixKey: response.chave,
        merchantName: this.config.merchantName,
        merchantCity: this.config.merchantCity,
        amount,
        txid: response.txid,
        createdAt: new Date(),
      },
    };
  }

  async getCharge(txid: string): Promise<PixCharge | null> {
    const token = await this.getAccessToken();

    try {
      const response = await this.request<{
        txid: string;
        status: string;
        valor: { original: string };
        chave: string;
        pix?: Array<{ endToEndId: string; horario: string }>;
      }>(
        'GET',
        `/v2/cob/${txid}`,
        undefined,
        { Authorization: `Bearer ${token}` }
      );

      const pix = response.pix?.[0];

      return {
        id: response.txid,
        txid: response.txid,
        status: response.status as PixChargeStatus,
        pixKey: response.chave,
        amount: Math.round(parseFloat(response.valor.original) * 100),
        expiresAt: new Date(),
        createdAt: new Date(),
        endToEndId: pix?.endToEndId,
        paidAt: pix ? new Date(pix.horario) : undefined,
        qrCode: {
          id: response.txid,
          type: 'dynamic',
          payload: '',
          pixKey: response.chave,
          merchantName: this.config.merchantName,
          merchantCity: this.config.merchantCity,
          createdAt: new Date(),
        },
      };
    } catch {
      return null;
    }
  }

  async cancelCharge(txid: string): Promise<void> {
    const token = await this.getAccessToken();

    await this.request(
      'PATCH',
      `/v2/cob/${txid}`,
      { status: 'REMOVIDA_PELO_USUARIO_RECEBEDOR' },
      { Authorization: `Bearer ${token}` }
    );
  }

  async initiateTransfer(
    keyType: PixKeyType,
    keyValue: string,
    amount: number,
    description?: string,
    idempotencyKey?: string
  ): Promise<PixTransfer> {
    const token = await this.getAccessToken();

    const response = await this.request<{
      id: string;
      status: string;
      endToEndId?: string;
    }>(
      'POST',
      '/v2/pix',
      {
        valor: (amount / 100).toFixed(2),
        pagador: {
          chave: this.config.receiverPixKey,
        },
        favorecido: {
          chave: keyValue,
        },
        descricao: description,
      },
      {
        Authorization: `Bearer ${token}`,
        'X-Idempotency-Key': idempotencyKey,
      }
    );

    return {
      id: response.id,
      status: this.mapApiTransferStatus(response.status),
      amount,
      destinationKey: { type: keyType, value: keyValue },
      description,
      endToEndId: response.endToEndId,
      initiatedAt: new Date(),
      completedAt: response.status === 'REALIZADO' ? new Date() : undefined,
    };
  }

  async getTransferStatus(transferId: string): Promise<PixTransfer | null> {
    const token = await this.getAccessToken();

    try {
      const response = await this.request<{
        id: string;
        status: string;
        valor: string;
        endToEndId?: string;
        horario?: string;
      }>(
        'GET',
        `/v2/pix/${transferId}`,
        undefined,
        { Authorization: `Bearer ${token}` }
      );

      return {
        id: response.id,
        status: this.mapApiTransferStatus(response.status),
        amount: Math.round(parseFloat(response.valor) * 100),
        destinationKey: { type: 'evp', value: '' },
        endToEndId: response.endToEndId,
        initiatedAt: new Date(),
        completedAt: response.horario ? new Date(response.horario) : undefined,
      };
    } catch {
      return null;
    }
  }

  async lookupPixKey(keyType: PixKeyType, keyValue: string): Promise<PixKeyLookupResult | null> {
    const token = await this.getAccessToken();

    try {
      const response = await this.request<{
        chave: string;
        tipoChave: string;
        nome: string;
        cpf?: string;
        cnpj?: string;
        banco: { nome: string; ispb: string };
        agencia: string;
        conta: string;
        tipoConta: string;
        dataCriacao: string;
      }>(
        'GET',
        `/v2/gn/pix/consulta/${encodeURIComponent(keyValue)}`,
        undefined,
        { Authorization: `Bearer ${token}` }
      );

      return {
        key: { type: keyType, value: keyValue },
        holderName: response.nome,
        holderDocument: response.cpf ?? response.cnpj ?? '',
        holderDocumentType: response.cpf ? 'cpf' : 'cnpj',
        bankIspb: response.banco.ispb,
        bankName: response.banco.nome,
        agency: response.agencia,
        accountNumber: response.conta,
        accountType: response.tipoConta as 'checking' | 'savings' | 'payment',
        createdAt: new Date(response.dataCriacao),
      };
    } catch {
      return null;
    }
  }

  async createRefund(
    endToEndId: string,
    amount: number,
    refundId: string
  ): Promise<{ id: string; status: string }> {
    const token = await this.getAccessToken();

    const response = await this.request<{
      id: string;
      status: string;
    }>(
      'PUT',
      `/v2/pix/${endToEndId}/devolucao/${refundId}`,
      {
        valor: (amount / 100).toFixed(2),
      },
      { Authorization: `Bearer ${token}` }
    );

    return {
      id: response.id ?? refundId,
      status: response.status === 'DEVOLVIDO' ? 'completed' : 'pending',
    };
  }

  async generateQrCode(charge: PixCharge): Promise<PixQrCode> {
    const token = await this.getAccessToken();

    // Get the location/QR code for the charge
    const response = await this.request<{
      qrcode: string;
      imagemQrcode: string;
    }>(
      'GET',
      `/v2/loc/${charge.qrCode.id}/qrcode`,
      undefined,
      { Authorization: `Bearer ${token}` }
    );

    return {
      ...charge.qrCode,
      payload: response.qrcode,
      qrCodeBase64: response.imagemQrcode,
    };
  }

  private mapApiTransferStatus(status: string): PixTransferStatus {
    const statusMap: Record<string, PixTransferStatus> = {
      'REALIZADO': 'completed',
      'NAO_REALIZADO': 'failed',
      'EM_PROCESSAMENTO': 'processing',
      'PENDENTE': 'pending',
      'DEVOLVIDO': 'returned',
    };
    return statusMap[status] ?? 'pending';
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    headers?: Record<string, string | undefined>
  ): Promise<T> {
    const url = new URL(path, this.config.baseUrl);

    return new Promise((resolve, reject) => {
      const options: https.RequestOptions = {
        method,
        hostname: url.hostname,
        port: url.port || 443,
        path: url.pathname + url.search,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        // mTLS configuration
        cert: this.config.certificate,
        key: this.config.certificateKey,
        rejectUnauthorized: !this.config.sandbox,
      };

      const req = https.request(options, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve(JSON.parse(data) as T);
          } else {
            reject(new Error(`PIX API error: ${res.statusCode} - ${data}`));
          }
        });
      });

      req.on('error', reject);

      if (body) {
        req.write(JSON.stringify(body));
      }

      req.end();
    });
  }
}
