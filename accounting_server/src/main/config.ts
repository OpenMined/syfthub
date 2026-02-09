/**
 * Application Configuration
 *
 * Loads and validates configuration from environment variables.
 */

import { z } from 'zod';

const ConfigSchema = z.object({
  // Server
  PORT: z.coerce.number().default(3000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),

  // Database
  DATABASE_URL: z.string().url(),
  DATABASE_POOL_SIZE: z.coerce.number().default(10),

  // Redis (for caching, rate limiting, idempotency)
  REDIS_URL: z.string().url().optional(),

  // JWT Authentication
  JWT_SECRET: z.string().min(32),
  JWT_ISSUER: z.string().default('ledger-api'),
  JWT_AUDIENCE: z.string().default('ledger-api'),
  JWT_EXPIRES_IN_SECONDS: z.coerce.number().default(3600), // 1 hour

  // Payment Providers
  STRIPE_API_KEY: z.string().optional(),
  STRIPE_WEBHOOK_SECRET: z.string().optional(),

  PAYPAL_CLIENT_ID: z.string().optional(),
  PAYPAL_CLIENT_SECRET: z.string().optional(),
  PAYPAL_WEBHOOK_ID: z.string().optional(),
  PAYPAL_SANDBOX: z.coerce.boolean().default(true),

  // PIX (Brazilian Instant Payment)
  PIX_ENABLED: z.coerce.boolean().default(false),
  PIX_PROVIDER: z.enum(['efi', 'itau', 'bradesco', 'bb', 'nubank', 'mercadopago', 'pagseguro', 'generic']).default('generic'),
  PIX_CLIENT_ID: z.string().optional(),
  PIX_CLIENT_SECRET: z.string().optional(),
  PIX_BASE_URL: z.string().url().optional(),
  PIX_RECEIVER_KEY: z.string().optional(),
  PIX_MERCHANT_NAME: z.string().default('ACCOUNTING SERVER'),
  PIX_MERCHANT_CITY: z.string().default('SAO PAULO'),
  PIX_CERTIFICATE_PATH: z.string().optional(),
  PIX_CERTIFICATE_KEY_PATH: z.string().optional(),
  PIX_WEBHOOK_URL: z.string().url().optional(),
  PIX_WEBHOOK_SECRET: z.string().optional(),
  PIX_SANDBOX: z.coerce.boolean().default(true),

  // Xendit (Southeast Asia)
  XENDIT_ENABLED: z.coerce.boolean().default(false),
  XENDIT_API_KEY: z.string().optional(),
  XENDIT_WEBHOOK_TOKEN: z.string().optional(),
  XENDIT_BASE_URL: z.string().url().default('https://api.xendit.co'),
  XENDIT_BUSINESS_ID: z.string().optional(),
  XENDIT_DEFAULT_COUNTRY: z.enum(['ID', 'PH', 'VN', 'TH', 'MY']).default('ID'),
  XENDIT_DEFAULT_CURRENCY: z.enum(['IDR', 'PHP', 'VND', 'THB', 'MYR', 'USD']).default('IDR'),
  XENDIT_SUCCESS_REDIRECT_URL: z.string().url().optional(),
  XENDIT_FAILURE_REDIRECT_URL: z.string().url().optional(),
  XENDIT_SANDBOX: z.coerce.boolean().default(true),

  // Transfer Confirmation
  TRANSFER_CONFIRMATION_SECRET: z.string().min(32),
  TRANSFER_CONFIRMATION_EXPIRATION_HOURS: z.coerce.number().default(24),

  // Rate Limiting
  RATE_LIMIT_WINDOW_MS: z.coerce.number().default(60000),
  RATE_LIMIT_MAX_REQUESTS: z.coerce.number().default(1000),

  // Logging
  LOG_LEVEL: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
});

export type Config = z.infer<typeof ConfigSchema>;

export function loadConfig(): Config {
  const result = ConfigSchema.safeParse(process.env);

  if (!result.success) {
    console.error('Configuration validation failed:');
    for (const error of result.error.errors) {
      console.error(`  ${error.path.join('.')}: ${error.message}`);
    }
    process.exit(1);
  }

  return result.data;
}

/**
 * Get development configuration template.
 *
 * SECURITY NOTE: This function does NOT return actual secrets.
 * Developers must set environment variables themselves.
 * Hardcoding secrets (even for development) creates security risks:
 * - Secrets end up in version control
 * - Developers may accidentally use them in production
 * - Security scanners flag the repository
 *
 * @returns Configuration template with placeholders (for documentation only)
 */
export function getDevConfigTemplate(): Record<string, string> {
  return {
    PORT: '3000',
    NODE_ENV: 'development',
    DATABASE_URL: 'postgresql://postgres:postgres@localhost:5432/ledger',
    JWT_SECRET: '<generate-random-32-char-string>',
    JWT_ISSUER: 'ledger-api-dev',
    JWT_AUDIENCE: 'ledger-api-dev',
    TRANSFER_CONFIRMATION_SECRET: '<generate-random-32-char-string>',
  };
}

/**
 * Print development configuration template to console.
 * Useful for first-time setup.
 */
export function printDevConfigTemplate(): void {
  console.log('\n=== Development Configuration Template ===\n');
  console.log('Copy these to your .env file and replace secret placeholders:\n');
  const template = getDevConfigTemplate();
  for (const [key, value] of Object.entries(template)) {
    console.log(`${key}=${value}`);
  }
  console.log('\nTo generate random secrets, run:');
  console.log('  node -e "console.log(require(\'crypto\').randomBytes(32).toString(\'hex\'))"');
  console.log('');
}
