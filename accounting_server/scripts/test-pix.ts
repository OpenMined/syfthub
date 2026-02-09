#!/usr/bin/env ts-node
/**
 * PIX Integration Test Script (Efí/Gerencianet Sandbox)
 *
 * Quick script to test PIX integration with Efí sandbox credentials.
 *
 * Prerequisites:
 *   1. Create account at https://dev.efipay.com.br
 *   2. Create an application and generate sandbox credentials
 *   3. Download the sandbox certificate (P12 file)
 *   4. Convert P12 to PEM format (see instructions below)
 *
 * Usage:
 *   source .env.test && npx ts-node scripts/test-pix.ts
 *
 * Certificate conversion (P12 to PEM):
 *   openssl pkcs12 -in certificado.p12 -out cert.pem -nodes -clcerts
 *   openssl pkcs12 -in certificado.p12 -out key.pem -nodes -nocerts
 */

import { PixAdapter } from '../src/infrastructure/payment-providers/pix/PixAdapter';
import { PixPspConfig, isValidPixKey, formatPixKey, generatePixTxid } from '../src/infrastructure/payment-providers/pix/PixTypes';
import * as fs from 'fs';
import * as path from 'path';

async function main() {
  console.log('='.repeat(60));
  console.log('PIX INTEGRATION TEST (Efí Sandbox)');
  console.log('='.repeat(60));

  // Check for required environment variables
  const clientId = process.env['PIX_CLIENT_ID'];
  const clientSecret = process.env['PIX_CLIENT_SECRET'];
  const certPath = process.env['PIX_CERTIFICATE_PATH'];
  const keyPath = process.env['PIX_CERTIFICATE_KEY_PATH'];
  const receiverKey = process.env['PIX_RECEIVER_KEY'];

  const missingVars: string[] = [];
  if (!clientId) missingVars.push('PIX_CLIENT_ID');
  if (!clientSecret) missingVars.push('PIX_CLIENT_SECRET');
  if (!certPath) missingVars.push('PIX_CERTIFICATE_PATH');
  if (!keyPath) missingVars.push('PIX_CERTIFICATE_KEY_PATH');
  if (!receiverKey) missingVars.push('PIX_RECEIVER_KEY');

  if (missingVars.length > 0) {
    console.error('\n❌ ERROR: Missing required environment variables:');
    missingVars.forEach(v => console.log(`   - ${v}`));

    console.log('\n📋 To get Efí sandbox credentials:');
    console.log('   1. Sign up at https://dev.efipay.com.br');
    console.log('   2. Go to API > Minhas Aplicações > Nova Aplicação');
    console.log('   3. Select "API Pix" and create the application');
    console.log('   4. Download the sandbox certificate (P12 file)');
    console.log('   5. Convert P12 to PEM format:');
    console.log('      openssl pkcs12 -in cert.p12 -out cert.pem -clcerts -nokeys');
    console.log('      openssl pkcs12 -in cert.p12 -out key.pem -nocerts -nodes');
    console.log('   6. Copy Client ID and Client Secret from the dashboard');
    console.log('   7. Create a PIX key in sandbox (or use a test EVP key)');
    console.log('\n📝 Add to .env.test:');
    console.log('   PIX_CLIENT_ID=Client_Id_xxx');
    console.log('   PIX_CLIENT_SECRET=Client_Secret_xxx');
    console.log('   PIX_CERTIFICATE_PATH=./certs/cert.pem');
    console.log('   PIX_CERTIFICATE_KEY_PATH=./certs/key.pem');
    console.log('   PIX_RECEIVER_KEY=your-pix-key@email.com');
    console.log('   PIX_SANDBOX=true');
    process.exit(1);
  }

  // Read certificate files
  let certificate: string;
  let certificateKey: string;

  try {
    certificate = fs.readFileSync(path.resolve(certPath!), 'utf-8');
    certificateKey = fs.readFileSync(path.resolve(keyPath!), 'utf-8');
  } catch (error) {
    console.error('\n❌ ERROR: Failed to read certificate files');
    console.log(`   Certificate path: ${certPath}`);
    console.log(`   Key path: ${keyPath}`);
    if (error instanceof Error) {
      console.log(`   Error: ${error.message}`);
    }
    process.exit(1);
  }

  const config: PixPspConfig = {
    provider: 'efi',
    clientId: clientId!,
    clientSecret: clientSecret!,
    baseUrl: process.env['PIX_BASE_URL'] ?? 'https://pix-h.api.efipay.com.br',
    receiverPixKey: receiverKey!,
    merchantName: process.env['PIX_MERCHANT_NAME'] ?? 'TEST MERCHANT',
    merchantCity: process.env['PIX_MERCHANT_CITY'] ?? 'SAO PAULO',
    certificate,
    certificateKey,
    webhookUrl: process.env['PIX_WEBHOOK_URL'] ?? 'https://example.com/webhooks/pix',
    webhookSecret: process.env['PIX_WEBHOOK_SECRET'] ?? 'test_secret',
    sandbox: process.env['PIX_SANDBOX'] !== 'false',
  };

  const adapter = new PixAdapter(config);

  console.log('\n✓ PIX adapter initialized');
  console.log(`  Provider: Efí (Gerencianet)`);
  console.log(`  Receiver Key: ${receiverKey}`);
  console.log(`  Merchant: ${config.merchantName}`);
  console.log(`  City: ${config.merchantCity}`);
  console.log(`  Sandbox: ${config.sandbox}`);

  // Test 1: PIX Key Validation
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 1: PIX Key Validation');
  console.log('-'.repeat(60));

  const testKeys = [
    { type: 'cpf' as const, value: '12345678901' },
    { type: 'cnpj' as const, value: '12345678000199' },
    { type: 'email' as const, value: 'test@example.com' },
    { type: 'phone' as const, value: '+5511999999999' },
    { type: 'evp' as const, value: '123e4567-e89b-42d3-a456-426614174000' },
  ];

  for (const key of testKeys) {
    const valid = isValidPixKey(key.type, key.value);
    const formatted = formatPixKey(key.type, key.value);
    console.log(`  ${key.type.toUpperCase().padEnd(6)} ${valid ? '✓' : '✗'} ${formatted}`);
  }

  // Test 2: Transaction ID Generation
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 2: Transaction ID Generation');
  console.log('-'.repeat(60));

  const txid = generatePixTxid();
  console.log(`✓ Generated txid: ${txid}`);
  console.log(`  Length: ${txid.length} characters`);

  // Test 3: Static QR Code Generation
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 3: Static QR Code Generation');
  console.log('-'.repeat(60));

  try {
    const staticQr = await adapter.createStaticQrCode(undefined, 'Test static QR');
    console.log('✓ Static QR code generated!');
    console.log(`  Type: ${staticQr.type}`);
    console.log(`  PIX Key: ${staticQr.pixKey}`);
    console.log(`  Merchant: ${staticQr.merchantName}`);
    console.log(`  City: ${staticQr.merchantCity}`);
    console.log(`  Payload length: ${staticQr.payload.length} chars`);
    console.log(`\n  📱 BR Code payload (copy to test in PIX app):`);
    console.log(`  ${staticQr.payload}`);
  } catch (error) {
    console.error(`✗ Failed: ${error instanceof Error ? error.message : error}`);
  }

  // Test 4: Static QR Code with Amount
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 4: Static QR Code with Fixed Amount');
  console.log('-'.repeat(60));

  try {
    const staticQrWithAmount = await adapter.createStaticQrCode(1000, 'Coffee R$10'); // R$ 10.00
    console.log('✓ Static QR code with amount generated!');
    console.log(`  Amount: R$ 10.00 (1000 cents)`);
    console.log(`\n  📱 BR Code payload:`);
    console.log(`  ${staticQrWithAmount.payload}`);
  } catch (error) {
    console.error(`✗ Failed: ${error instanceof Error ? error.message : error}`);
  }

  // Test 5: Dynamic QR Code (requires API connection)
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 5: Dynamic QR Code (API Call)');
  console.log('-'.repeat(60));

  try {
    const charge = await adapter.createCharge({
      amount: 100, // R$ 1.00
      expiresInSeconds: 3600,
      description: 'Test charge from integration script',
      metadata: {
        source: 'test-script',
        timestamp: new Date().toISOString(),
      },
      idempotencyKey: `test-${Date.now()}`,
    });

    console.log('✓ Dynamic charge created!');
    console.log(`  Txid: ${charge.txid}`);
    console.log(`  Status: ${charge.status}`);
    console.log(`  Amount: R$ ${(charge.amount / 100).toFixed(2)}`);
    console.log(`  Expires: ${charge.expiresAt.toISOString()}`);
    if (charge.qrCode.payload) {
      console.log(`\n  📱 Dynamic QR Code payload:`);
      console.log(`  ${charge.qrCode.payload}`);
    }
    if (charge.qrCode.qrCodeBase64) {
      console.log(`\n  🖼️  QR Code image available (base64)`);
    }
  } catch (error) {
    console.error(`✗ Failed to create dynamic charge: ${error instanceof Error ? error.message : error}`);
    console.log('\n  Note: Dynamic QR codes require valid Efí API credentials.');
    console.log('  Static QR codes (Tests 3-4) work without API calls.');
  }

  // Test 6: Webhook Verification
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 6: Webhook Signature Verification');
  console.log('-'.repeat(60));

  const crypto = require('crypto');
  const testPayload = JSON.stringify({
    evento: 'pix.received',
    endToEndId: 'E12345678202401151000abcdef123456',
    txid: 'test_txid_123',
    valor: 1000,
  });
  const testSignature = crypto
    .createHmac('sha256', config.webhookSecret)
    .update(testPayload)
    .digest('hex');

  const isValid = adapter.verifyWebhookSignature(testPayload, testSignature);
  console.log(`✓ Webhook verification: ${isValid ? 'PASSED' : 'FAILED'}`);

  // Test 7: Webhook Event Parsing
  console.log('\n' + '-'.repeat(60));
  console.log('TEST 7: Webhook Event Parsing');
  console.log('-'.repeat(60));

  const event = adapter.parseWebhookEvent(testPayload);
  console.log(`✓ Parsed webhook event:`);
  console.log(`  Type: ${event.type}`);
  console.log(`  Delivery ID: ${event.deliveryId}`);
  console.log(`  Timestamp: ${event.timestamp.toISOString()}`);
  console.log(`  E2E ID: ${event.data['endToEndId']}`);

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));
  console.log('\n✓ Basic tests completed!');

  console.log('\n📋 PIX Payment Flow:');
  console.log('   1. Generate QR code (static or dynamic)');
  console.log('   2. Customer scans with banking app');
  console.log('   3. Customer confirms payment');
  console.log('   4. Webhook receives pix.received event');
  console.log('   5. Verify and credit user account');

  console.log('\n🔗 Useful links:');
  console.log('   - Efí Dev Portal: https://dev.efipay.com.br');
  console.log('   - API Docs: https://dev.efipay.com.br/docs/api-pix');
  console.log('   - Sandbox Dashboard: https://dev.efipay.com.br/login');

  console.log('\n⚠️  Important notes:');
  console.log('   - PIX requires mTLS (mutual TLS) with certificates');
  console.log('   - Sandbox certificates are different from production');
  console.log('   - In sandbox, you can simulate payments via dashboard');
  console.log('');
}

main().catch((error) => {
  console.error('\n❌ Test script failed:', error);
  process.exit(1);
});
