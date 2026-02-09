/**
 * PixAdapter Unit Tests
 *
 * Tests the PIX payment provider adapter with mocked HTTP responses.
 */

import { PixAdapter } from '../../../../src/infrastructure/payment-providers/pix/PixAdapter';
import { PixPspConfig } from '../../../../src/infrastructure/payment-providers/pix/PixTypes';

describe('PixAdapter', () => {
  let adapter: PixAdapter;

  const testConfig: PixPspConfig = {
    provider: 'efi',
    clientId: 'test_client_id',
    clientSecret: 'test_client_secret',
    baseUrl: 'https://pix-h.api.efipay.com.br',
    receiverPixKey: 'test@example.com',
    merchantName: 'TEST MERCHANT',
    merchantCity: 'SAO PAULO',
    certificate: '-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----',
    certificateKey: '-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----',
    webhookUrl: 'https://example.com/webhooks/pix',
    webhookSecret: 'test_webhook_secret',
    sandbox: true,
  };

  beforeEach(() => {
    adapter = new PixAdapter(testConfig);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('configuration getters', () => {
    it('should expose receiver PIX key', () => {
      expect(adapter.receiverPixKey).toBe('test@example.com');
    });

    it('should expose merchant info', () => {
      expect(adapter.merchantInfo).toEqual({
        name: 'TEST MERCHANT',
        city: 'SAO PAULO',
      });
    });
  });

  describe('createStaticQrCode', () => {
    it('should generate a static QR code without amount', async () => {
      const qrCode = await adapter.createStaticQrCode();

      expect(qrCode.type).toBe('static');
      expect(qrCode.pixKey).toBe('test@example.com');
      expect(qrCode.merchantName).toBe('TEST MERCHANT');
      expect(qrCode.merchantCity).toBe('SAO PAULO');
      expect(qrCode.payload).toContain('br.gov.bcb.pix');
      expect(qrCode.amount).toBeUndefined();
    });

    it('should generate a static QR code with amount', async () => {
      const qrCode = await adapter.createStaticQrCode(10000, 'Test payment');

      expect(qrCode.type).toBe('static');
      expect(qrCode.amount).toBe(10000);
      expect(qrCode.description).toBe('Test payment');
      expect(qrCode.payload).toContain('100.00'); // 10000 cents = 100.00 BRL
    });

    it('should include CRC16 in the payload', async () => {
      const qrCode = await adapter.createStaticQrCode();

      // BR Code always ends with CRC16 (4 hex digits after '63' tag)
      expect(qrCode.payload).toMatch(/6304[A-F0-9]{4}$/);
    });
  });

  describe('verifyWebhookSignature', () => {
    it('should verify valid HMAC signature', () => {
      const payload = '{"event":"pix.received","amount":10000}';
      // Pre-computed HMAC-SHA256 of payload with test_webhook_secret
      const crypto = require('crypto');
      const validSignature = crypto
        .createHmac('sha256', 'test_webhook_secret')
        .update(payload)
        .digest('hex');

      const isValid = adapter.verifyWebhookSignature(payload, validSignature);

      expect(isValid).toBe(true);
    });

    it('should reject invalid signature', () => {
      const payload = '{"event":"pix.received","amount":10000}';
      const invalidSignature = 'invalid_signature_that_is_64_chars_long_for_hex_comparison_test';

      // This will throw due to buffer length mismatch, which is expected
      expect(() => adapter.verifyWebhookSignature(payload, invalidSignature)).toThrow();
    });
  });

  describe('parseWebhookEvent', () => {
    it('should parse pix.received event', () => {
      const payload = JSON.stringify({
        evento: 'pix.received',
        id: 'webhook-123',
        timestamp: '2024-01-15T10:00:00Z',
        endToEndId: 'E12345678202401151000abcdef123456',
        txid: 'test_txid_123',
        valor: 10000,
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payment_intent.succeeded');
      expect(event.deliveryId).toBe('webhook-123');
      expect(event.timestamp).toEqual(new Date('2024-01-15T10:00:00Z'));
      expect(event.data['endToEndId']).toBe('E12345678202401151000abcdef123456');
    });

    it('should parse charge.paid event', () => {
      const payload = JSON.stringify({
        evento: 'charge.paid',
        id: 'webhook-456',
        horario: '2024-01-15T10:00:00Z',
        txid: 'charge_txid_123',
        valor: 50000,
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payment_intent.succeeded');
      expect(event.data['txid']).toBe('charge_txid_123');
    });

    it('should parse pix.sent event', () => {
      const payload = JSON.stringify({
        evento: 'pix.sent',
        id: 'webhook-789',
        timestamp: '2024-01-15T10:00:00Z',
        endToEndId: 'E12345678202401151000transfer123',
        valor: 25000,
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payout.paid');
    });

    it('should parse charge.expired event', () => {
      const payload = JSON.stringify({
        evento: 'charge.expired',
        id: 'webhook-expired',
        timestamp: '2024-01-15T11:00:00Z',
        txid: 'expired_txid',
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('payment_intent.failed');
    });

    it('should parse refund.completed event', () => {
      const payload = JSON.stringify({
        evento: 'refund.completed',
        id: 'webhook-refund',
        timestamp: '2024-01-15T12:00:00Z',
        endToEndId: 'E12345678202401151000refund123',
        valor: 5000,
      });

      const event = adapter.parseWebhookEvent(payload);

      expect(event.type).toBe('refund.succeeded');
    });
  });

  describe('BR Code generation', () => {
    it('should generate valid BR Code payload format', async () => {
      const qrCode = await adapter.createStaticQrCode(15000, 'Coffee');

      // Check EMV QR Code structure
      expect(qrCode.payload).toContain('000201'); // Payload Format Indicator
      expect(qrCode.payload).toContain('br.gov.bcb.pix'); // PIX GUI
      expect(qrCode.payload).toContain('test@example.com'); // PIX key
      expect(qrCode.payload).toContain('5303986'); // Currency (BRL = 986)
      expect(qrCode.payload).toContain('5802BR'); // Country Code
      expect(qrCode.payload).toContain('TEST MERCHANT'); // Merchant Name
      expect(qrCode.payload).toContain('SAO PAULO'); // Merchant City
    });
  });
});

describe('PIX Key Validation', () => {
  const { isValidPixKey, formatPixKey, generatePixTxid } = require('../../../../src/infrastructure/payment-providers/pix/PixTypes');

  describe('isValidPixKey', () => {
    it('should validate CPF format', () => {
      expect(isValidPixKey('cpf', '12345678901')).toBe(true);
      expect(isValidPixKey('cpf', '123.456.789-01')).toBe(true);
      expect(isValidPixKey('cpf', '1234567890')).toBe(false); // 10 digits
      expect(isValidPixKey('cpf', '123456789012')).toBe(false); // 12 digits
    });

    it('should validate CNPJ format', () => {
      expect(isValidPixKey('cnpj', '12345678000199')).toBe(true);
      expect(isValidPixKey('cnpj', '12.345.678/0001-99')).toBe(true);
      expect(isValidPixKey('cnpj', '1234567800019')).toBe(false); // 13 digits
    });

    it('should validate email format', () => {
      expect(isValidPixKey('email', 'test@example.com')).toBe(true);
      expect(isValidPixKey('email', 'user.name+tag@domain.co.br')).toBe(true);
      expect(isValidPixKey('email', 'invalid-email')).toBe(false);
      expect(isValidPixKey('email', '@nodomain.com')).toBe(false);
    });

    it('should validate phone format', () => {
      expect(isValidPixKey('phone', '+5511999999999')).toBe(true);
      expect(isValidPixKey('phone', '+551199999999')).toBe(true); // 8 digit number
      expect(isValidPixKey('phone', '11999999999')).toBe(false); // missing +55
    });

    it('should validate EVP (random key) format', () => {
      expect(isValidPixKey('evp', '123e4567-e89b-42d3-a456-426614174000')).toBe(true);
      expect(isValidPixKey('evp', 'not-a-uuid')).toBe(false);
    });
  });

  describe('formatPixKey', () => {
    it('should format CPF', () => {
      expect(formatPixKey('cpf', '12345678901')).toBe('123.456.789-01');
    });

    it('should format CNPJ', () => {
      expect(formatPixKey('cnpj', '12345678000199')).toBe('12.345.678/0001-99');
    });

    it('should format phone', () => {
      expect(formatPixKey('phone', '+5511999999999')).toBe('+55 (11) 99999-9999');
    });

    it('should return email unchanged', () => {
      expect(formatPixKey('email', 'test@example.com')).toBe('test@example.com');
    });
  });

  describe('generatePixTxid', () => {
    it('should generate 32 character alphanumeric txid', () => {
      const txid = generatePixTxid();

      expect(txid).toHaveLength(32);
      expect(txid).toMatch(/^[A-Za-z0-9]+$/);
    });

    it('should generate unique txids', () => {
      const txids = new Set<string>();
      for (let i = 0; i < 100; i++) {
        txids.add(generatePixTxid());
      }
      expect(txids.size).toBe(100);
    });
  });
});
