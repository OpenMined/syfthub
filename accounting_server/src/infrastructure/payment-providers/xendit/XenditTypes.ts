/**
 * Xendit Types and Interfaces
 *
 * Type definitions for Xendit payment platform integration.
 * Supports payments, payouts, invoices, and virtual accounts
 * across Southeast Asia (Indonesia, Philippines, Vietnam, Thailand, Malaysia).
 */

// ============================================
// Configuration
// ============================================

export interface XenditConfig {
  /** Xendit API Key (starts with xnd_) */
  apiKey: string;
  /** Webhook verification token */
  webhookToken: string;
  /** Base URL for API calls */
  baseUrl: string;
  /** Whether to use sandbox/test environment */
  sandbox: boolean;
  /** Business ID for multi-account setups */
  businessId?: string | undefined;
  /** Default country code */
  defaultCountry: XenditCountry;
  /** Default currency */
  defaultCurrency: XenditCurrency;
  /** Success redirect URL for payments */
  successRedirectUrl?: string | undefined;
  /** Failure redirect URL for payments */
  failureRedirectUrl?: string | undefined;
}

// ============================================
// Enums and Constants
// ============================================

export type XenditCountry = 'ID' | 'PH' | 'VN' | 'TH' | 'MY';

export type XenditCurrency = 'IDR' | 'PHP' | 'VND' | 'THB' | 'MYR' | 'USD';

export type XenditPaymentType = 'PAY' | 'REUSABLE_PAYMENT_CODE';

export type XenditCaptureMethod = 'AUTOMATIC' | 'MANUAL';

/**
 * Payment channel codes supported by Xendit
 */
export type XenditChannelCode =
  // Cards
  | 'CARDS'
  // Indonesia Virtual Accounts
  | 'BCA_VIRTUAL_ACCOUNT'
  | 'BNI_VIRTUAL_ACCOUNT'
  | 'BRI_VIRTUAL_ACCOUNT'
  | 'MANDIRI_VIRTUAL_ACCOUNT'
  | 'PERMATA_VIRTUAL_ACCOUNT'
  | 'BSI_VIRTUAL_ACCOUNT'
  | 'CIMB_VIRTUAL_ACCOUNT'
  // Philippines Virtual Accounts
  | 'BDO_VIRTUAL_ACCOUNT'
  | 'BPI_VIRTUAL_ACCOUNT'
  | 'UNIONBANK_VIRTUAL_ACCOUNT'
  // Vietnam Virtual Accounts
  | 'VIETCAPITAL_VIRTUAL_ACCOUNT'
  | 'WOORI_VIRTUAL_ACCOUNT'
  // E-Wallets Indonesia
  | 'OVO'
  | 'DANA'
  | 'SHOPEEPAY'
  | 'LINKAJA'
  | 'GOPAY'
  | 'ASTRAPAY'
  | 'JENIUSPAY'
  // E-Wallets Philippines
  | 'GCASH'
  | 'GRABPAY'
  | 'PAYMAYA'
  // E-Wallets Vietnam
  | 'MOMO'
  | 'ZALOPAY'
  | 'VNPAY'
  // E-Wallets Thailand
  | 'TRUEMONEY'
  | 'SHOPEEPAY_TH'
  // QR Codes
  | 'QRIS'
  | 'PROMPTPAY'
  // Direct Debit
  | 'BPI_DIRECT_DEBIT'
  | 'BCA_DIRECT_DEBIT'
  | 'BRI_DIRECT_DEBIT'
  // Retail Outlets
  | 'ALFAMART'
  | 'INDOMARET'
  | '7ELEVEN'
  | 'CEBUANA'
  | 'ECPAY';

export type XenditPaymentStatus =
  | 'PENDING'
  | 'REQUIRES_ACTION'
  | 'AUTHORIZED'
  | 'CAPTURED'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'VOIDED'
  | 'EXPIRED';

export type XenditPayoutStatus =
  | 'PENDING'
  | 'ACCEPTED'
  | 'LOCKED'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REVERSED'
  | 'REQUESTED';

export type XenditRefundStatus = 'SUCCEEDED' | 'FAILED' | 'PENDING' | 'CANCELLED';

export type XenditRefundReason =
  | 'FRAUDULENT'
  | 'DUPLICATE'
  | 'REQUESTED_BY_CUSTOMER'
  | 'CANCELLATION'
  | 'OTHERS';

export type XenditPaymentMethodType = 'CARD' | 'EWALLET' | 'DIRECT_DEBIT' | 'VIRTUAL_ACCOUNT' | 'QR_CODE' | 'OVER_THE_COUNTER';

// ============================================
// Payment Request Types
// ============================================

export interface XenditCreatePaymentRequest {
  reference_id: string;
  type: XenditPaymentType;
  country: XenditCountry;
  currency: XenditCurrency;
  request_amount: number;
  capture_method: XenditCaptureMethod;
  channel_code: XenditChannelCode;
  channel_properties: XenditChannelProperties;
  description?: string | undefined;
  metadata?: Record<string, string> | undefined;
  customer_id?: string | undefined;
}

export interface XenditChannelProperties {
  // Common
  success_return_url?: string | undefined;
  failure_return_url?: string | undefined;
  // Card-specific
  card_details?: XenditCardDetails | undefined;
  skip_three_ds?: boolean | undefined;
  mid_label?: string | undefined;
  // Virtual Account
  display_name?: string | undefined;
  expires_at?: string | undefined;
  suggested_amount?: number | undefined;
  // E-Wallet
  mobile_number?: string | undefined;
  cashtag?: string | undefined;
  // Direct Debit
  account_mobile_number?: string | undefined;
  card_last_four?: string | undefined;
  card_expiry?: string | undefined;
}

export interface XenditCardDetails {
  card_number?: string | undefined;
  expiry_month?: string | undefined;
  expiry_year?: string | undefined;
  cvn?: string | undefined;
  cardholder_first_name?: string | undefined;
  cardholder_last_name?: string | undefined;
  cardholder_email?: string | undefined;
  cardholder_phone_number?: string | undefined;
}

export interface XenditPaymentRequestResponse {
  id: string;
  business_id: string;
  reference_id: string;
  payment_request_id?: string | undefined;
  type: XenditPaymentType;
  country: XenditCountry;
  currency: XenditCurrency;
  request_amount: number;
  captured_amount?: number | undefined;
  status: XenditPaymentStatus;
  capture_method: XenditCaptureMethod;
  channel_code: XenditChannelCode;
  channel_properties?: XenditChannelProperties | undefined;
  actions?: XenditAction[] | undefined;
  description?: string | undefined;
  metadata?: Record<string, string> | undefined;
  failure_code?: string | undefined;
  created: string;
  updated: string;
}

export interface XenditAction {
  type: 'REDIRECT_CUSTOMER' | 'QR_CODE' | 'DEEPLINK' | 'PRESENT_TO_CUSTOMER';
  descriptor: 'WEB_URL' | 'MOBILE_URL' | 'QR_STRING' | 'BARCODE';
  value: string;
}

// ============================================
// Payment (Capture) Types
// ============================================

export interface XenditPayment {
  payment_id: string;
  business_id: string;
  reference_id: string;
  payment_request_id: string;
  request_amount: number;
  captured_amount?: number | undefined;
  status: XenditPaymentStatus;
  country: XenditCountry;
  currency: XenditCurrency;
  channel_code: XenditChannelCode;
  channel_properties?: Record<string, unknown> | undefined;
  description?: string | undefined;
  metadata?: Record<string, string> | undefined;
  failure_code?: string | undefined;
  customer_id?: string | undefined;
  type: string;
  created: string;
  updated: string;
}

// ============================================
// Payout Types
// ============================================

export interface XenditCreatePayoutRequest {
  reference_id: string;
  channel_code: string;
  channel_properties: XenditPayoutChannelProperties;
  amount: number;
  currency: XenditCurrency;
  description?: string | undefined;
  metadata?: Record<string, string> | undefined;
  receipt_notification?: XenditReceiptNotification | undefined;
}

export interface XenditPayoutChannelProperties {
  account_holder_name: string;
  account_number: string;
  account_type?: 'BANK_ACCOUNT' | 'MOBILE_NO' | 'NATIONAL_ID' | 'PASSPORT' | 'BUSINESS_REGISTRATION' | undefined;
}

export interface XenditReceiptNotification {
  email_to?: string[] | undefined;
  email_cc?: string[] | undefined;
  email_bcc?: string[] | undefined;
}

export interface XenditPayoutResponse {
  id: string;
  business_id: string;
  reference_id: string;
  channel_code: string;
  channel_properties: XenditPayoutChannelProperties;
  amount: number;
  currency: XenditCurrency;
  description?: string | undefined;
  status: XenditPayoutStatus;
  failure_code?: string | undefined;
  estimated_arrival_time?: string | undefined;
  created: string;
  updated: string;
  metadata?: Record<string, string> | undefined;
}

// ============================================
// Refund Types
// ============================================

export interface XenditCreateRefundRequest {
  payment_id: string;
  reference_id: string;
  amount?: number | undefined;
  reason: XenditRefundReason;
  metadata?: Record<string, string> | undefined;
}

export interface XenditRefundResponse {
  id: string;
  payment_id: string;
  invoice_id?: string | undefined;
  amount: number;
  payment_method_type: XenditPaymentMethodType;
  channel_code: string;
  currency: XenditCurrency;
  status: XenditRefundStatus;
  reason: XenditRefundReason;
  reference_id: string;
  failure_code?: string | undefined;
  refund_fee_amount?: number | undefined;
  created: string;
  updated: string;
  metadata?: Record<string, string> | undefined;
}

// ============================================
// Invoice Types
// ============================================

export interface XenditCreateInvoiceRequest {
  external_id: string;
  amount: number;
  currency?: XenditCurrency | undefined;
  payer_email?: string | undefined;
  description?: string | undefined;
  invoice_duration?: number | undefined;
  success_redirect_url?: string | undefined;
  failure_redirect_url?: string | undefined;
  payment_methods?: string[] | undefined;
  customer?: XenditCustomer | undefined;
  customer_notification_preference?: XenditNotificationPreference | undefined;
  metadata?: Record<string, string> | undefined;
}

export interface XenditCustomer {
  given_names?: string | undefined;
  surname?: string | undefined;
  email?: string | undefined;
  mobile_number?: string | undefined;
  addresses?: XenditAddress[] | undefined;
}

export interface XenditAddress {
  country: string;
  street_line1?: string | undefined;
  street_line2?: string | undefined;
  city?: string | undefined;
  province_state?: string | undefined;
  postal_code?: string | undefined;
}

export interface XenditNotificationPreference {
  invoice_created?: ('email' | 'whatsapp' | 'sms')[] | undefined;
  invoice_reminder?: ('email' | 'whatsapp' | 'sms')[] | undefined;
  invoice_paid?: ('email' | 'whatsapp' | 'sms')[] | undefined;
  invoice_expired?: ('email' | 'whatsapp' | 'sms')[] | undefined;
}

export interface XenditInvoiceResponse {
  id: string;
  external_id: string;
  user_id: string;
  status: 'PENDING' | 'PAID' | 'SETTLED' | 'EXPIRED';
  merchant_name: string;
  merchant_profile_picture_url?: string | undefined;
  amount: number;
  fees_paid_amount?: number | undefined;
  adjusted_received_amount?: number | undefined;
  bank_code?: string | undefined;
  retail_outlet_name?: string | undefined;
  ewallet_type?: string | undefined;
  on_demand_link?: string | undefined;
  recurring_payment_id?: string | undefined;
  payer_email?: string | undefined;
  description?: string | undefined;
  invoice_url: string;
  available_banks?: XenditAvailableBank[] | undefined;
  available_retail_outlets?: XenditAvailableRetailOutlet[] | undefined;
  available_ewallets?: XenditAvailableEwallet[] | undefined;
  should_exclude_credit_card?: boolean | undefined;
  should_send_email?: boolean | undefined;
  success_redirect_url?: string | undefined;
  failure_redirect_url?: string | undefined;
  created: string;
  updated: string;
  currency: XenditCurrency;
  items?: XenditInvoiceItem[] | undefined;
  customer?: XenditCustomer | undefined;
  metadata?: Record<string, string> | undefined;
}

export interface XenditAvailableBank {
  bank_code: string;
  collection_type: string;
  transfer_amount: number;
  bank_branch: string;
  account_holder_name: string;
  identity_amount: number;
}

export interface XenditAvailableRetailOutlet {
  retail_outlet_name: string;
  payment_code: string;
  transfer_amount: number;
  merchant_name?: string | undefined;
}

export interface XenditAvailableEwallet {
  ewallet_type: string;
}

export interface XenditInvoiceItem {
  name: string;
  quantity: number;
  price: number;
  category?: string | undefined;
  url?: string | undefined;
}

// ============================================
// Virtual Account Types
// ============================================

export interface XenditCreateVirtualAccountRequest {
  external_id: string;
  bank_code: string;
  name: string;
  expected_amount?: number | undefined;
  suggested_amount?: number | undefined;
  expiration_date?: string | undefined;
  is_closed?: boolean | undefined;
  is_single_use?: boolean | undefined;
  virtual_account_number?: string | undefined;
  currency?: XenditCurrency | undefined;
  description?: string | undefined;
  country?: XenditCountry | undefined;
}

export interface XenditVirtualAccountResponse {
  id: string;
  owner_id: string;
  external_id: string;
  bank_code: string;
  merchant_code: string;
  name: string;
  account_number: string;
  is_closed: boolean;
  is_single_use: boolean;
  expected_amount?: number | undefined;
  suggested_amount?: number | undefined;
  expiration_date: string;
  status: 'PENDING' | 'INACTIVE' | 'ACTIVE';
  currency: XenditCurrency;
  country: XenditCountry;
  description?: string | undefined;
  created?: string | undefined;
  updated?: string | undefined;
}

// ============================================
// Webhook Types
// ============================================

export type XenditWebhookEventType =
  | 'payment.capture'
  | 'payment.authorization'
  | 'payment.failure'
  | 'payment_token.activation'
  | 'payment_token.failure'
  | 'payment_token.expiry'
  | 'payout.succeeded'
  | 'payout.failed'
  | 'refund.succeeded'
  | 'refund.failed'
  | 'invoice.paid'
  | 'invoice.expired'
  | 'fva.created'
  | 'fva.paid'
  | 'fva.expired';

export interface XenditWebhookPayload<T = Record<string, unknown>> {
  event: XenditWebhookEventType;
  business_id: string;
  created: string;
  data: T;
  api_version?: string | undefined;
}

export interface XenditPaymentWebhookData {
  payment_id: string;
  business_id: string;
  status: XenditPaymentStatus;
  payment_request_id: string;
  request_amount: number;
  captured_amount?: number | undefined;
  customer_id?: string | undefined;
  channel_code: XenditChannelCode;
  country: XenditCountry;
  currency: XenditCurrency;
  reference_id: string;
  description?: string | undefined;
  failure_code?: string | undefined;
  channel_properties?: Record<string, unknown> | undefined;
  type: string;
  created: string;
  updated: string;
  metadata?: Record<string, string> | undefined;
}

export interface XenditPayoutWebhookData {
  id: string;
  business_id: string;
  reference_id: string;
  channel_code: string;
  amount: number;
  currency: XenditCurrency;
  status: XenditPayoutStatus;
  failure_code?: string | undefined;
  estimated_arrival_time?: string | undefined;
  created: string;
  updated: string;
  metadata?: Record<string, string> | undefined;
}

export interface XenditRefundWebhookData {
  id: string;
  payment_id: string;
  invoice_id?: string | undefined;
  amount: number;
  payment_method_type: XenditPaymentMethodType;
  channel_code: string;
  currency: XenditCurrency;
  status: XenditRefundStatus;
  reason: XenditRefundReason;
  reference_id: string;
  failure_code?: string | undefined;
  created: string;
  updated: string;
  metadata?: Record<string, string> | undefined;
}

// ============================================
// Error Types
// ============================================

export interface XenditError {
  error_code: string;
  message: string;
}

export const XENDIT_ERROR_CODES = {
  // General
  API_VALIDATION_ERROR: 'API_VALIDATION_ERROR',
  INVALID_API_KEY: 'INVALID_API_KEY',
  REQUEST_FORBIDDEN_ERROR: 'REQUEST_FORBIDDEN_ERROR',

  // Payment
  CHANNEL_NOT_ACTIVATED: 'CHANNEL_NOT_ACTIVATED',
  INSUFFICIENT_BALANCE: 'INSUFFICIENT_BALANCE',
  PAYMENT_FAILED: 'PAYMENT_FAILED',
  EXPIRED_PAYMENT: 'EXPIRED_PAYMENT',
  DUPLICATE_PAYMENT_REQUEST_ERROR: 'DUPLICATE_PAYMENT_REQUEST_ERROR',

  // Payout
  PAYOUT_FAILED: 'PAYOUT_FAILED',
  DESTINATION_NOT_FOUND: 'DESTINATION_NOT_FOUND',
  INVALID_DESTINATION: 'INVALID_DESTINATION',

  // Refund
  REFUND_FAILED: 'REFUND_FAILED',
  ACCOUNT_ACCESS_BLOCKED: 'ACCOUNT_ACCESS_BLOCKED',
  ACCOUNT_NOT_FOUND: 'ACCOUNT_NOT_FOUND',
  DUPLICATE_ERROR: 'DUPLICATE_ERROR',
} as const;

// ============================================
// Bank/Channel Codes by Country
// ============================================

export const XENDIT_INDONESIA_BANKS = [
  'BCA',
  'BNI',
  'BRI',
  'MANDIRI',
  'PERMATA',
  'BSI',
  'CIMB',
  'DANAMON',
  'SAHABAT_SAMPOERNA',
] as const;

export const XENDIT_PHILIPPINES_BANKS = [
  'BDO',
  'BPI',
  'CHINABANK',
  'INSTAPAY',
  'LANDBANK',
  'METROBANK',
  'PNB',
  'RCBC',
  'UNIONBANK',
] as const;

export const XENDIT_VIETNAM_BANKS = [
  'VIETCAPITAL',
  'WOORI',
  'TPBANK',
  'TECHCOMBANK',
  'VIETCOMBANK',
] as const;

export const XENDIT_EWALLETS_INDONESIA = ['OVO', 'DANA', 'SHOPEEPAY', 'LINKAJA', 'GOPAY', 'ASTRAPAY', 'JENIUSPAY'] as const;
export const XENDIT_EWALLETS_PHILIPPINES = ['GCASH', 'GRABPAY', 'PAYMAYA'] as const;
export const XENDIT_EWALLETS_VIETNAM = ['MOMO', 'ZALOPAY', 'VNPAY'] as const;
export const XENDIT_EWALLETS_THAILAND = ['TRUEMONEY', 'SHOPEEPAY_TH'] as const;

// ============================================
// Helper Types
// ============================================

export interface XenditPaymentChannelInfo {
  code: XenditChannelCode;
  name: string;
  country: XenditCountry;
  type: XenditPaymentMethodType;
  currencies: XenditCurrency[];
  minAmount?: number | undefined;
  maxAmount?: number | undefined;
}

/**
 * Get available payment channels for a country
 */
export function getAvailableChannels(country: XenditCountry): XenditChannelCode[] {
  const channelsByCountry: Record<XenditCountry, XenditChannelCode[]> = {
    ID: [
      'CARDS',
      'BCA_VIRTUAL_ACCOUNT',
      'BNI_VIRTUAL_ACCOUNT',
      'BRI_VIRTUAL_ACCOUNT',
      'MANDIRI_VIRTUAL_ACCOUNT',
      'PERMATA_VIRTUAL_ACCOUNT',
      'OVO',
      'DANA',
      'SHOPEEPAY',
      'LINKAJA',
      'GOPAY',
      'QRIS',
      'ALFAMART',
      'INDOMARET',
    ],
    PH: [
      'CARDS',
      'GCASH',
      'GRABPAY',
      'PAYMAYA',
      'BPI_VIRTUAL_ACCOUNT',
      'BDO_VIRTUAL_ACCOUNT',
      'UNIONBANK_VIRTUAL_ACCOUNT',
      '7ELEVEN',
      'CEBUANA',
      'ECPAY',
    ],
    VN: [
      'CARDS',
      'MOMO',
      'ZALOPAY',
      'VNPAY',
      'VIETCAPITAL_VIRTUAL_ACCOUNT',
      'WOORI_VIRTUAL_ACCOUNT',
    ],
    TH: ['CARDS', 'TRUEMONEY', 'SHOPEEPAY_TH', 'PROMPTPAY'],
    MY: ['CARDS'],
  };

  return channelsByCountry[country] ?? [];
}

/**
 * Get currency for country
 */
export function getCurrencyForCountry(country: XenditCountry): XenditCurrency {
  const currencyMap: Record<XenditCountry, XenditCurrency> = {
    ID: 'IDR',
    PH: 'PHP',
    VN: 'VND',
    TH: 'THB',
    MY: 'MYR',
  };
  return currencyMap[country];
}
