/**
 * XenditAdapter Unit Tests
 *
 * Tests the Xendit payment provider adapter with mocked HTTP responses.
 */

import { XenditAdapter, XenditApiError } from '../../../../src/infrastructure/payment-providers/xendit/XenditAdapter';
import { XenditConfig } from '../../../../src/infrastructure/payment-providers/xendit/XenditTypes';
import { Money } from '../../../../src/domain/value-objects/Money';

describe('XenditAdapter', () => {
  let adapter: XenditAdapter;
  let mockFetch: jest.Mock;

  const testConfig: XenditConfig = {
    apiKey: 'xnd_development_test_key',
    webhookToken: 'test_webhook_token_123',
    baseUrl: 'https://api.xendit.co',
    sandbox: true,
    defaultCountry: 'ID',
    defaultCurrency: 'IDR',
    successRedirectUrl: 'https://example.com/success',
    failureRedirectUrl: 'https://example.com/failure',
  };

  beforeEach(() => {
    adapter = new XenditAdapter(testConfig);
    mockFetch = jest.fn();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('createPaymentIntent', () => {
    it('should create a payment request successfully', async () => {
      const mockResponse = {
        id: 'pr-123456',
        business_id: 'biz-123',
        reference_id: 'idempotency-key-123',
        type: 'PAY',
        country: 'ID',
        currency: 'IDR',
        request_amount: 100000,
        status: 'PENDING',
        capture_method: 'AUTOMATIC',
        channel_code: 'DANA',
        actions: [
          {
            type: 'REDIRECT_CUSTOMER',
            descriptor: 'WEB_URL',
            value: 'https://payment.xendit.co/redirect/123',
          },
        ],
        created: '2024-01-15T10:00:00Z',
        updated: '2024-01-15T10:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await adapter.createPaymentIntent({
        amount: Money.credits(100000n),
        currency: 'IDR',
        paymentMethodId: 'pm-123',
        metadata: {
          channel_code: 'DANA',
          transaction_id: 'txn-123',
        },
        idempotencyKey: 'idempotency-key-123',
      });

      expect(result.id).toBe('pr-123456');
      expect(result.status).toBe('processing');
      expect(result.clientSecret).toBe('https://payment.xendit.co/redirect/123');
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('should handle payment request failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({
          error_code: 'CHANNEL_NOT_ACTIVATED',
          message: 'The requested channel is not activated',
        }),
      });

      const result = await adapter.createPaymentIntent({
        amount: Money.credits(100000n),
        currency: 'IDR',
        paymentMethodId: 'pm-123',
        metadata: { channel_code: 'INVALID_CHANNEL' },
        idempotencyKey: 'idempotency-key-456',
      });

      expect(result.status).toBe('failed');
      expect(result.errorCode).toBe('CHANNEL_NOT_ACTIVATED');
    });
  });

  describe('initiateTransfer (Payout)', () => {
    it('should create a payout successfully', async () => {
      const mockResponse = {
        id: 'payout-123456',
        business_id: 'biz-123',
        reference_id: 'withdrawal-key-123',
        channel_code: 'ID_BCA',
        channel_properties: {
          account_holder_name: 'John Doe',
          account_number: '1234567890',
          account_type: 'BANK_ACCOUNT',
        },
        amount: 500000,
        currency: 'IDR',
        status: 'PENDING',
        created: '2024-01-15T10:00:00Z',
        updated: '2024-01-15T10:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await adapter.initiateTransfer({
        amount: Money.credits(500000n),
        currency: 'IDR',
        destination: {
          type: 'bank_account',
          externalId: 'ID_BCA:1234567890:John Doe',
        },
        metadata: { transaction_id: 'txn-withdrawal-123' },
        idempotencyKey: 'withdrawal-key-123',
      });

      expect(result.id).toBe('payout-123456');
      expect(result.status).toBe('pending');
    });

    it('should handle payout failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({
          error_code: 'INVALID_DESTINATION',
          message: 'Invalid destination account',
        }),
      });

      const result = await adapter.initiateTransfer({
        amount: Money.credits(500000n),
        currency: 'IDR',
        destination: {
          type: 'bank_account',
          externalId: 'INVALID:999:Unknown',
        },
        metadata: {},
        idempotencyKey: 'withdrawal-key-456',
      });

      expect(result.status).toBe('failed');
      expect(result.errorMessage).toContain('Invalid destination');
    });
  });

  describe('createRefund', () => {
    it('should create a refund successfully', async () => {
      const mockResponse = {
        id: 'refund-123456',
        payment_id: 'payment-123',
        amount: 50000,
        payment_method_type: 'EWALLET',
        channel_code: 'DANA',
        currency: 'IDR',
        status: 'SUCCEEDED',
        reason: 'REQUESTED_BY_CUSTOMER',
        reference_id: 'refund-key-123',
        created: '2024-01-15T10:00:00Z',
        updated: '2024-01-15T10:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await adapter.createRefund({
        externalTransactionId: 'payment-123',
        amount: Money.credits(50000n),
        reason: 'customer_request',
        idempotencyKey: 'refund-key-123',
      });

      expect(result.id).toBe('refund-123456');
      expect(result.status).toBe('succeeded');
      expect(result.externalReference).toBe('refund-123456');
    });
  });

  describe('verifyWebhookSignature', () => {
    it('should verify valid webhook token', () => {
      const isValid = adapter.verifyWebhookSignature(
        '{"event":"payment.capture"}',
        'test_webhook_token_123'
      );

      expect(isValid).toBe(true);
    });

    it('should reject invalid webhook token', () => {
      const isValid = adapter.verifyWebhookSignature(
        '{"event":"payment.capture"}',
        'wrong_token'
      );

      expect(isValid).toBe(false);
    });
  });

  describe('parseWebhookEvent', () => {
    it('should parse payment.capture event', () => {
      const payload = JSON.stringify({
        event: 'payment.capture',
        business_id: 'biz-123',
        created: '2024-01-15T10:00:00Z',
        data: {
          payment_id: 'payment-123',
          status: 'SUCCEEDED',
          request_amount: 100000,
          currency: 'IDR',
          reference_id: 'order-123',
        },
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payment_intent.succeeded');
      expect(event.timestamp).toEqual(new Date('2024-01-15T10:00:00Z'));
      expect(event.data['payment_id']).toBe('payment-123');
    });

    it('should parse payment.failure event', () => {
      const payload = JSON.stringify({
        event: 'payment.failure',
        business_id: 'biz-123',
        created: '2024-01-15T10:00:00Z',
        data: {
          payment_id: 'payment-456',
          status: 'FAILED',
          failure_code: 'INSUFFICIENT_BALANCE',
        },
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payment_intent.failed');
    });

    it('should parse payout.succeeded event', () => {
      const payload = JSON.stringify({
        event: 'payout.succeeded',
        business_id: 'biz-123',
        created: '2024-01-15T10:00:00Z',
        data: {
          id: 'payout-123',
          status: 'SUCCEEDED',
          amount: 500000,
        },
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payout.paid');
    });
  });

  describe('createInvoice', () => {
    it('should create an invoice successfully', async () => {
      const mockResponse = {
        id: 'inv-123456',
        external_id: 'order-123',
        user_id: 'user-123',
        status: 'PENDING',
        merchant_name: 'Test Merchant',
        amount: 100000,
        invoice_url: 'https://checkout.xendit.co/web/inv-123456',
        currency: 'IDR',
        created: '2024-01-15T10:00:00Z',
        updated: '2024-01-15T10:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await adapter.createInvoice({
        externalId: 'order-123',
        amount: 100000,
        description: 'Test order',
        payerEmail: 'customer@example.com',
      });

      expect(result.id).toBe('inv-123456');
      expect(result.status).toBe('PENDING');
      expect(result.invoice_url).toBe('https://checkout.xendit.co/web/inv-123456');
    });
  });

  describe('createVirtualAccount', () => {
    it('should create a virtual account successfully', async () => {
      const mockResponse = {
        id: 'va-123456',
        owner_id: 'owner-123',
        external_id: 'deposit-123',
        bank_code: 'BCA',
        merchant_code: '12345',
        name: 'John Doe',
        account_number: '123456789012',
        is_closed: false,
        is_single_use: false,
        expected_amount: 100000,
        expiration_date: '2024-01-20T10:00:00Z',
        status: 'ACTIVE',
        currency: 'IDR',
        country: 'ID',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await adapter.createVirtualAccount({
        externalId: 'deposit-123',
        bankCode: 'BCA',
        name: 'John Doe',
        expectedAmount: 100000,
      });

      expect(result.id).toBe('va-123456');
      expect(result.account_number).toBe('123456789012');
      expect(result.status).toBe('ACTIVE');
    });
  });

  describe('getAvailableChannels', () => {
    it('should return Indonesia channels', async () => {
      const channels = await adapter.getAvailableChannels('ID');

      expect(channels).toContain('CARDS');
      expect(channels).toContain('BCA_VIRTUAL_ACCOUNT');
      expect(channels).toContain('OVO');
      expect(channels).toContain('DANA');
      expect(channels).toContain('QRIS');
    });

    it('should return Philippines channels', async () => {
      const channels = await adapter.getAvailableChannels('PH');

      expect(channels).toContain('CARDS');
      expect(channels).toContain('GCASH');
      expect(channels).toContain('GRABPAY');
      expect(channels).toContain('PAYMAYA');
    });

    it('should return default country channels when not specified', async () => {
      const channels = await adapter.getAvailableChannels();

      // Default is ID
      expect(channels).toContain('BCA_VIRTUAL_ACCOUNT');
    });
  });

  describe('configuration getters', () => {
    it('should expose default country', () => {
      expect(adapter.defaultCountry).toBe('ID');
    });

    it('should expose default currency', () => {
      expect(adapter.defaultCurrency).toBe('IDR');
    });

    it('should expose redirect URLs', () => {
      expect(adapter.successRedirectUrl).toBe('https://example.com/success');
      expect(adapter.failureRedirectUrl).toBe('https://example.com/failure');
    });
  });
});

describe('XenditApiError', () => {
  it('should create error with correct properties', () => {
    const error = new XenditApiError('CHANNEL_NOT_ACTIVATED', 'Channel not activated', 400);

    expect(error.name).toBe('XenditApiError');
    expect(error.code).toBe('CHANNEL_NOT_ACTIVATED');
    expect(error.message).toBe('Channel not activated');
    expect(error.httpStatus).toBe(400);
  });
});
