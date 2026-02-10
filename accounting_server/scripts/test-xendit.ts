#!/usr/bin/env ts-node
/**
 * Xendit Integration Test Script
 *
 * Quick script to test Xendit integration with sandbox credentials.
 *
 * Usage:
 *   XENDIT_API_KEY=xnd_development_xxx npx ts-node scripts/test-xendit.ts
 *
 * Or with environment file:
 *   source .env.test && npx ts-node scripts/test-xendit.ts
 */

import { XenditAdapter } from '../src/infrastructure/payment-providers/xendit/XenditAdapter';
import { XenditConfig } from '../src/infrastructure/payment-providers/xendit/XenditTypes';
import { Money } from '../src/domain/value-objects/Money';

async function main() {
  console.log('='.repeat(60));
  console.log('XENDIT INTEGRATION TEST');
  console.log('='.repeat(60));

  // Check for API key
  const apiKey = process.env['XENDIT_API_KEY'];
  if (!apiKey) {
    console.error('\n❌ ERROR: XENDIT_API_KEY environment variable is required');
    console.log('\nTo get a sandbox API key:');
    console.log('1. Sign up at https://dashboard.xendit.co');
    console.log('2. Go to Settings > Developers > API Keys');
    console.log('3. Copy your Development/Sandbox API key (starts with xnd_development_)');
    console.log('\nThen run:');
    console.log('  XENDIT_API_KEY=xnd_development_xxx npx ts-node scripts/test-xendit.ts');
    process.exit(1);
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

  const adapter = new XenditAdapter(config);

  console.log('\n✓ Xendit adapter initialized');
  console.log(`  Default Country: ${adapter.defaultCountry}`);
  console.log(`  Default Currency: ${adapter.defaultCurrency}`);

  // Test 1: List available channels
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 1: List Available Payment Channels');
  console.log('-'.repeat(60));

  try {
    const channels = await adapter.getAvailableChannels('ID');
    console.log(`✓ Available channels for Indonesia (${channels.length}):`);

    const channelTypes = {
      'Virtual Accounts': channels.filter(c => c.includes('VIRTUAL_ACCOUNT')),
      'E-Wallets': channels.filter(c => ['OVO', 'DANA', 'SHOPEEPAY', 'LINKAJA', 'GOPAY'].includes(c)),
      'QR Codes': channels.filter(c => c === 'QRIS'),
      'Cards': channels.filter(c => c === 'CARDS'),
    };

    for (const [type, chs] of Object.entries(channelTypes)) {
      if (chs.length > 0) {
        console.log(`  ${type}: ${chs.join(', ')}`);
      }
    }
  } catch (error) {
    console.error(`✗ Failed to list channels: ${error}`);
  }

  // Test 2: Create Invoice
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 2: Create Invoice (Payment Link)');
  console.log('-'.repeat(60));

  let invoiceId: string | null = null;

  try {
    const invoice = await adapter.createInvoice({
      externalId: `test-${Date.now()}`,
      amount: 50000, // IDR 50,000
      description: 'Test invoice from integration script',
      payerEmail: 'test@example.com',
      durationSeconds: 3600,
      metadata: {
        source: 'test-script',
        timestamp: new Date().toISOString(),
      },
    });

    invoiceId = invoice.id;
    console.log('✓ Invoice created successfully!');
    console.log(`  Invoice ID: ${invoice.id}`);
    console.log(`  Status: ${invoice.status}`);
    console.log(`  Amount: ${invoice.currency} ${invoice.amount.toLocaleString()}`);
    console.log(`  \n  🔗 Pay at: ${invoice.invoice_url}`);
    console.log('\n  Test Card Numbers (sandbox):');
    console.log('    - Success: 4000000000001091');
    console.log('    - Declined: 4000000000001109');
    console.log('    - 3DS Required: 4000000000001000');
    console.log('    (Use any future expiry date and any 3-digit CVV)');
  } catch (error) {
    console.error(`✗ Failed to create invoice: ${error}`);
  }

  // Test 3: Get Invoice Status
  if (invoiceId) {
    console.log('\n' + '-'.repeat(60));
    console.log('TEST 3: Get Invoice Status');
    console.log('-'.repeat(60));

    try {
      const invoice = await adapter.getInvoice(invoiceId);
      if (invoice) {
        console.log('✓ Invoice retrieved successfully!');
        console.log(`  Status: ${invoice.status}`);
        console.log(`  Created: ${invoice.created}`);
      }
    } catch (error) {
      console.error(`✗ Failed to get invoice: ${error}`);
    }
  }

  // Test 4: Create Virtual Account
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 4: Create Virtual Account');
  console.log('-'.repeat(60));

  let vaId: string | null = null;

  try {
    const va = await adapter.createVirtualAccount({
      externalId: `va-test-${Date.now()}`,
      bankCode: 'BCA',
      name: 'Test Customer',
      expectedAmount: 100000,
      isClosed: true,
      isSingleUse: true,
    });

    vaId = va.id;
    console.log('✓ Virtual Account created successfully!');
    console.log(`  VA ID: ${va.id}`);
    console.log(`  Bank: ${va.bank_code}`);
    console.log(`  Account Number: ${va.account_number}`);
    console.log(`  Status: ${va.status}`);
    console.log(`  Expected Amount: IDR ${va.expected_amount?.toLocaleString()}`);
    console.log(`  Expires: ${va.expiration_date}`);
  } catch (error) {
    console.error(`✗ Failed to create VA: ${error}`);
    if (error instanceof Error) {
      console.log(`  Error details: ${error.message}`);
    }
  }

  // Test 5: Webhook Verification
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 5: Webhook Signature Verification');
  console.log('-'.repeat(60));

  const testPayload = JSON.stringify({
    event: 'payment.capture',
    business_id: 'test-business-id',
    created: new Date().toISOString(),
    data: { payment_id: 'test-payment' },
  });

  const webhookToken = process.env['XENDIT_WEBHOOK_TOKEN'] ?? 'test_token';
  const isValid = adapter.verifyWebhookSignature(testPayload, webhookToken);
  console.log(`✓ Webhook verification test: ${isValid ? 'PASSED' : 'FAILED'}`);

  // Cleanup
  console.log('\n' + '-'.repeat(60));
  console.log('CLEANUP');
  console.log('-'.repeat(60));

  if (invoiceId) {
    try {
      await adapter.expireInvoice(invoiceId);
      console.log(`✓ Invoice ${invoiceId} expired`);
    } catch {
      console.log(`  Note: Invoice may already be expired or paid`);
    }
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));
  console.log('\n✓ All basic tests completed!');
  console.log('\nNext steps:');
  console.log('1. Run unit tests: npm test');
  console.log('2. Run integration tests: RUN_INTEGRATION_TESTS=true npm test -- --testPathPattern=integration');
  console.log('3. Test webhooks using https://dashboard.xendit.co/settings/developers#webhooks');
  console.log('4. Configure production keys when ready to go live');
  console.log('');
}

main().catch((error) => {
  console.error('\n❌ Test script failed:', error);
  process.exit(1);
});
