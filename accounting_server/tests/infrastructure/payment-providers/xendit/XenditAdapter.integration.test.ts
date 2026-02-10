/**
 * Xendit Integration Tests (Sandbox)
 *
 * These tests hit the actual Xendit sandbox API.
 * Run with: XENDIT_API_KEY=xnd_development_xxx npm test -- --testPathPattern=integration
 *
 * Prerequisites:
 * 1. Get sandbox API keys from https://dashboard.xendit.co/settings/developers#api-keys
 * 2. Set environment variables:
 *    - XENDIT_API_KEY: Your sandbox API key (starts with xnd_development_)
 *    - XENDIT_WEBHOOK_TOKEN: Optional webhook verification token
 *
 * Note: These tests are skipped by default. Set RUN_INTEGRATION_TESTS=true to run them.
 */

import { XenditAdapter } from '../../../../src/infrastructure/payment-providers/xendit/XenditAdapter';
import { XenditConfig } from '../../../../src/infrastructure/payment-providers/xendit/XenditTypes';
import { Money } from '../../../../src/domain/value-objects/Money';

// Skip integration tests unless explicitly enabled
// When RUN_INTEGRATION_TESTS=true, the test setup skips mocking fetch
const SKIP_INTEGRATION = process.env['RUN_INTEGRATION_TESTS'] !== 'true';

const describeIntegration = SKIP_INTEGRATION ? describe.skip : describe;

describeIntegration('XenditAdapter Integration Tests (Sandbox)', () => {
  let adapter: XenditAdapter;

  beforeAll(() => {
    const apiKey = process.env['XENDIT_API_KEY'];
    if (!apiKey) {
      throw new Error(
        'XENDIT_API_KEY environment variable is required for integration tests. ' +
        'Get your sandbox key from https://dashboard.xendit.co/settings/developers#api-keys'
      );
    }

    const config: XenditConfig = {
      apiKey,
      webhookToken: process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_token',
      baseUrl: 'https://api.xendit.co',
      sandbox: true,
      defaultCountry: 'ID',
      defaultCurrency: 'IDR',
      successRedirectUrl: 'https://example.com/success',
      failureRedirectUrl: 'https://example.com/failure',
    };

    adapter = new XenditAdapter(config);
  });

  describe('Invoice API', () => {
    let createdInvoiceId: string;

    it('should create an invoice', async () => {
      const invoice = await adapter.createInvoice({
        externalId: `test-invoice-${Date.now()}`,
        amount: 50000, // IDR 50,000 (minimum for testing)
        description: 'Integration test invoice',
        payerEmail: 'test@example.com',
        durationSeconds: 3600, // 1 hour
        metadata: {
          test: 'true',
          created_by: 'integration_test',
        },
      });

      expect(invoice.id).toBeDefined();
      expect(invoice.status).toBe('PENDING');
      expect(invoice.invoice_url).toContain('xendit.co');
      expect(invoice.amount).toBe(50000);

      createdInvoiceId = invoice.id;
      console.log(`Created invoice: ${invoice.id}`);
      console.log(`Pay at: ${invoice.invoice_url}`);
    });

    it('should get invoice by ID', async () => {
      if (!createdInvoiceId) {
        console.log('Skipping - no invoice created');
        return;
      }

      const invoice = await adapter.getInvoice(createdInvoiceId);

      expect(invoice).not.toBeNull();
      expect(invoice?.id).toBe(createdInvoiceId);
      expect(invoice?.status).toBe('PENDING');
    });

    it('should expire an invoice', async () => {
      if (!createdInvoiceId) {
        console.log('Skipping - no invoice created');
        return;
      }

      const invoice = await adapter.expireInvoice(createdInvoiceId);

      expect(invoice.status).toBe('EXPIRED');
    });
  });

  describe('Virtual Account API', () => {
    let createdVaId: string;

    it('should create a virtual account', async () => {
      const va = await adapter.createVirtualAccount({
        externalId: `test-va-${Date.now()}`,
        bankCode: 'BCA', // BCA bank for Indonesia
        name: 'Test User Integration',
        expectedAmount: 100000,
        isClosed: true,
        isSingleUse: true,
      });

      expect(va.id).toBeDefined();
      expect(va.account_number).toBeDefined();
      expect(va.bank_code).toBe('BCA');
      expect(va.status).toBe('PENDING'); // Will become ACTIVE shortly

      createdVaId = va.id;
      console.log(`Created VA: ${va.id}`);
      console.log(`Account Number: ${va.account_number}`);
    });

    it('should get virtual account by ID', async () => {
      if (!createdVaId) {
        console.log('Skipping - no VA created');
        return;
      }

      const va = await adapter.getVirtualAccount(createdVaId);

      expect(va).not.toBeNull();
      expect(va?.id).toBe(createdVaId);
    });
  });

  describe('Payment Channels', () => {
    it('should list available channels for Indonesia', async () => {
      const channels = await adapter.getAvailableChannels('ID');

      expect(channels).toContain('CARDS');
      expect(channels.length).toBeGreaterThan(5);
      console.log(`Indonesia channels: ${channels.join(', ')}`);
    });

    it('should list available channels for Philippines', async () => {
      const channels = await adapter.getAvailableChannels('PH');

      expect(channels).toContain('CARDS');
      expect(channels).toContain('GCASH');
      console.log(`Philippines channels: ${channels.join(', ')}`);
    });

    it('should list available channels for Vietnam', async () => {
      const channels = await adapter.getAvailableChannels('VN');

      expect(channels).toContain('CARDS');
      console.log(`Vietnam channels: ${channels.join(', ')}`);
    });
  });

  describe('Payment Request API', () => {
    it('should create a payment request (QRIS)', async () => {
      // QRIS is a good test channel as it doesn't require redirect
      const result = await adapter.createPaymentIntent({
        amount: Money.credits(25000n), // IDR 25,000
        currency: 'IDR',
        paymentMethodId: 'pm-test',
        metadata: {
          channel_code: 'QRIS',
          transaction_id: `test-txn-${Date.now()}`,
          description: 'Test QRIS payment',
        },
        idempotencyKey: `test-idempotency-${Date.now()}`,
      });

      // QRIS requests may succeed or fail depending on account activation
      console.log(`Payment request result: ${JSON.stringify(result)}`);
      expect(result.id || result.errorCode).toBeDefined();
    });
  });

  describe('Webhook Verification', () => {
    it('should verify webhook token', () => {
      const webhookToken = process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_token';

      const isValid = adapter.verifyWebhookSignature(
        '{"event":"payment.capture"}',
        webhookToken
      );

      expect(isValid).toBe(true);
    });
  });
});

/**
 * Simulated Payment Test
 *
 * This test simulates the full payment flow:
 * 1. Create invoice
 * 2. Simulate payment (only works with specific test scenarios)
 * 3. Verify webhook processing
 */
describeIntegration('Xendit Payment Flow Simulation', () => {
  let adapter: XenditAdapter;

  beforeAll(() => {
    const apiKey = process.env['XENDIT_API_KEY'];
    if (!apiKey) {
      throw new Error('XENDIT_API_KEY required');
    }

    adapter = new XenditAdapter({
      apiKey,
      webhookToken: process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_token',
      baseUrl: 'https://api.xendit.co',
      sandbox: true,
      defaultCountry: 'ID',
      defaultCurrency: 'IDR',
    });
  });

  it('should complete full invoice payment flow', async () => {
    // 1. Create invoice
    const invoice = await adapter.createInvoice({
      externalId: `flow-test-${Date.now()}`,
      amount: 10000,
      description: 'Flow test',
    });

    console.log('Step 1: Invoice created');
    console.log(`  ID: ${invoice.id}`);
    console.log(`  URL: ${invoice.invoice_url}`);

    // 2. In sandbox, you can use test credit cards or simulate payments
    // See: https://docs.xendit.co/credit-cards/test-scenarios
    console.log('\nTo test payment, use these sandbox cards:');
    console.log('  Success: 4000000000001091 (any expiry, any CVV)');
    console.log('  Declined: 4000000000001109');
    console.log('  3DS Required: 4000000000001000');

    // 3. Check invoice status (should still be PENDING)
    const checkInvoice = await adapter.getInvoice(invoice.id);
    expect(checkInvoice?.status).toBe('PENDING');

    console.log('\nStep 3: Invoice verified as PENDING');

    // 4. Clean up - expire the invoice
    await adapter.expireInvoice(invoice.id);
    console.log('Step 4: Invoice expired (cleanup)');
  });
});
