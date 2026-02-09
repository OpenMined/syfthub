/**
 * PIX Types and Domain Models
 *
 * Types for Brazilian PIX instant payment system integration.
 * Based on BCB (Banco Central do Brasil) specifications.
 */

// ============================================
// PIX Key Types
// ============================================

/**
 * Types of PIX keys (Chaves PIX)
 */
export type PixKeyType =
  | 'cpf'        // Brazilian individual taxpayer ID (11 digits)
  | 'cnpj'       // Brazilian company taxpayer ID (14 digits)
  | 'email'      // Email address
  | 'phone'      // Phone number (+55DDDNUMBER)
  | 'evp';       // Random key (UUID format)

/**
 * A PIX key with its associated information
 */
export interface PixKey {
  type: PixKeyType;
  value: string;
  name?: string | undefined;        // Account holder name
  bankIspb?: string | undefined;    // Bank ISPB code
  bankName?: string | undefined;    // Bank name
  agency?: string | undefined;      // Branch number
  accountType?: 'checking' | 'savings' | 'payment' | undefined;
}

/**
 * Result of a DICT (PIX key directory) lookup
 */
export interface PixKeyLookupResult {
  key: PixKey;
  holderName: string;
  holderDocument: string;         // CPF or CNPJ (masked)
  holderDocumentType: 'cpf' | 'cnpj';
  bankIspb: string;
  bankName: string;
  agency: string;
  accountNumber: string;
  accountType: 'checking' | 'savings' | 'payment';
  createdAt: Date;
  verifiedAt?: Date | undefined;
}

// ============================================
// QR Code Types
// ============================================

/**
 * Types of PIX QR codes
 */
export type PixQrCodeType =
  | 'static'    // Can be used multiple times, optional amount
  | 'dynamic';  // Single use, fixed amount, with expiration

/**
 * PIX QR code (for receiving payments)
 */
export interface PixQrCode {
  id: string;
  type: PixQrCodeType;
  payload: string;              // EMV/BR Code payload (the actual QR content)
  qrCodeBase64?: string | undefined;  // Base64 encoded QR image
  qrCodeUrl?: string | undefined;     // URL to QR image
  pixKey: string;               // Receiving PIX key
  merchantName: string;         // Receiver name
  merchantCity: string;         // Receiver city
  amount?: number | undefined;  // Amount in cents (optional for static)
  expiresAt?: Date | undefined; // Expiration (for dynamic)
  txid?: string | undefined;    // Transaction ID (for dynamic)
  description?: string | undefined;
  createdAt: Date;
}

/**
 * Request to create a static QR code
 */
export interface CreateStaticQrCodeRequest {
  pixKey: string;
  merchantName: string;
  merchantCity: string;
  amount?: number | undefined;      // Optional fixed amount in cents
  description?: string | undefined;
}

/**
 * Request to create a dynamic QR code (cobrança imediata)
 */
export interface CreateDynamicQrCodeRequest {
  pixKey: string;
  amount: number;               // Amount in cents (required)
  expiresInSeconds: number;     // Expiration time
  description?: string | undefined;
  payerDocument?: string | undefined;  // CPF/CNPJ of expected payer
  payerName?: string | undefined;
  metadata?: Record<string, string> | undefined;
}

// ============================================
// PIX Charge Types (Cobrança)
// ============================================

/**
 * Status of a PIX charge
 */
export type PixChargeStatus =
  | 'active'        // Waiting for payment
  | 'completed'     // Payment received
  | 'expired'       // Expired without payment
  | 'cancelled'     // Cancelled by merchant
  | 'refunded';     // Payment was refunded

/**
 * PIX charge (cobrança) - represents a payment request
 */
export interface PixCharge {
  id: string;
  txid: string;                 // Transaction ID (alphanumeric, 26-35 chars)
  status: PixChargeStatus;
  pixKey: string;
  amount: number;               // Amount in cents
  description?: string | undefined;
  payerDocument?: string | undefined;
  payerName?: string | undefined;
  qrCode: PixQrCode;
  paidAt?: Date | undefined;
  expiresAt: Date;
  createdAt: Date;
  endToEndId?: string | undefined;  // Unique BCB transaction ID
}

/**
 * Request to create a PIX charge
 */
export interface CreatePixChargeRequest {
  amount: number;
  expiresInSeconds: number;
  description?: string | undefined;
  payerDocument?: string | undefined;
  payerName?: string | undefined;
  metadata?: Record<string, string> | undefined;
  idempotencyKey: string;
}

// ============================================
// PIX Transfer Types (Cash-out)
// ============================================

/**
 * Status of a PIX transfer (payout)
 */
export type PixTransferStatus =
  | 'pending'       // Waiting to be processed
  | 'processing'    // Being processed
  | 'completed'     // Successfully completed
  | 'failed'        // Failed
  | 'returned';     // Returned by receiving bank

/**
 * PIX transfer (for sending money)
 */
export interface PixTransfer {
  id: string;
  status: PixTransferStatus;
  amount: number;               // Amount in cents
  destinationKey: PixKey;
  description?: string | undefined;
  endToEndId?: string | undefined;
  initiatedAt: Date;
  completedAt?: Date | undefined;
  failureReason?: string | undefined;
}

/**
 * Request to initiate a PIX transfer
 */
export interface InitiatePixTransferRequest {
  destinationKeyType: PixKeyType;
  destinationKeyValue: string;
  amount: number;               // Amount in cents
  description?: string | undefined;
  idempotencyKey: string;
}

// ============================================
// PIX Refund Types (Devolução)
// ============================================

/**
 * Status of a PIX refund
 */
export type PixRefundStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed';

/**
 * PIX refund (devolução)
 */
export interface PixRefund {
  id: string;
  originalEndToEndId: string;   // Original transaction's E2E ID
  status: PixRefundStatus;
  amount: number;               // Refund amount in cents
  reason: string;
  createdAt: Date;
  completedAt?: Date | undefined;
}

// ============================================
// Webhook Types
// ============================================

/**
 * Types of PIX webhook events
 */
export type PixWebhookEventType =
  | 'pix.received'          // Incoming PIX payment received
  | 'pix.sent'              // Outgoing PIX completed
  | 'pix.failed'            // PIX transfer failed
  | 'pix.returned'          // PIX was returned
  | 'charge.paid'           // Charge was paid
  | 'charge.expired'        // Charge expired
  | 'refund.completed'      // Refund completed
  | 'refund.failed';        // Refund failed

/**
 * PIX webhook payload
 */
export interface PixWebhookPayload {
  eventType: PixWebhookEventType;
  timestamp: Date;
  data: {
    endToEndId?: string | undefined;
    txid?: string | undefined;
    amount: number;
    payerDocument?: string | undefined;
    payerName?: string | undefined;
    receiverKey?: string | undefined;
    description?: string | undefined;
    metadata?: Record<string, unknown> | undefined;
  };
}

// ============================================
// API Error Types
// ============================================

/**
 * PIX API error codes (based on BCB specification)
 */
export type PixErrorCode =
  | 'INVALID_KEY'               // PIX key not found or invalid
  | 'INACTIVE_KEY'              // PIX key is inactive
  | 'KEY_BLOCKED'               // PIX key is blocked
  | 'INSUFFICIENT_FUNDS'        // Payer has insufficient funds
  | 'DAILY_LIMIT_EXCEEDED'      // Daily transfer limit exceeded
  | 'TRANSACTION_LIMIT_EXCEEDED'// Per-transaction limit exceeded
  | 'TIMEOUT'                   // Transaction timed out
  | 'RECIPIENT_UNAVAILABLE'     // Receiving bank unavailable
  | 'DUPLICATE_TRANSACTION'     // Transaction already processed
  | 'INVALID_AMOUNT'            // Invalid amount
  | 'FRAUD_SUSPECTED'           // Possible fraud detected
  | 'ACCOUNT_BLOCKED'           // Account is blocked
  | 'UNKNOWN_ERROR';            // Unknown error

/**
 * PIX API error
 */
export interface PixApiError {
  code: PixErrorCode;
  message: string;
  details?: Record<string, unknown> | undefined;
}

// ============================================
// PSP Configuration
// ============================================

/**
 * Configuration for PIX PSP (Payment Service Provider)
 */
export interface PixPspConfig {
  /** PSP name/identifier */
  provider: 'efi' | 'itau' | 'bradesco' | 'bb' | 'nubank' | 'mercadopago' | 'pagseguro' | 'generic';

  /** OAuth2 client ID */
  clientId: string;

  /** OAuth2 client secret */
  clientSecret: string;

  /** API base URL */
  baseUrl: string;

  /** PIX key to receive payments */
  receiverPixKey: string;

  /** Merchant information */
  merchantName: string;
  merchantCity: string;

  /** Certificate for mTLS (required by BCB) */
  certificate: string;
  certificateKey: string;

  /** Webhook configuration */
  webhookUrl: string;
  webhookSecret: string;

  /** Environment */
  sandbox: boolean;
}

// ============================================
// Utility Types
// ============================================

/**
 * Validate a PIX key format
 */
export function isValidPixKey(type: PixKeyType, value: string): boolean {
  switch (type) {
    case 'cpf':
      return /^\d{11}$/.test(value.replace(/\D/g, ''));
    case 'cnpj':
      return /^\d{14}$/.test(value.replace(/\D/g, ''));
    case 'email':
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    case 'phone':
      // Brazilian phone: +55 + DDD (2 digits) + number (8-9 digits)
      return /^\+55\d{10,11}$/.test(value.replace(/\D/g, '').replace(/^(\d)/, '+$1'));
    case 'evp':
      // UUID v4 format
      return /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
    default:
      return false;
  }
}

/**
 * Format a PIX key for display
 */
export function formatPixKey(type: PixKeyType, value: string): string {
  switch (type) {
    case 'cpf':
      return value.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
    case 'cnpj':
      return value.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
    case 'phone':
      return value.replace(/(\+55)(\d{2})(\d{4,5})(\d{4})/, '$1 ($2) $3-$4');
    default:
      return value;
  }
}

/**
 * Generate a transaction ID (txid) for PIX
 * Must be alphanumeric, 26-35 characters
 */
export function generatePixTxid(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const length = 32;
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}
