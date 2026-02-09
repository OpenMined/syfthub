/**
 * Dependency Injection Container
 *
 * Creates and wires all application dependencies.
 */

import { Pool } from 'pg';
import fs from 'fs';
import { Config } from './config';

// Repositories
import {
  PostgresAccountRepository,
  PostgresTransactionRepository,
  PostgresApiTokenRepository,
  PostgresUserRepository,
  PostgresTransactionManager,
} from '../infrastructure/persistence';
import { PostgresPaymentMethodRepository } from '../infrastructure/persistence/PostgresPaymentMethodRepository';

// Payment Providers
import {
  PaymentProviderFactory,
  ProviderConfig,
} from '../infrastructure/payment-providers/PaymentProviderFactory';

// Use Cases
import { ExecuteTransferUseCase } from '../application/use-cases/ExecuteTransfer';
import { ProcessDepositUseCase } from '../application/use-cases/ProcessDeposit';
import { InitiateWithdrawalUseCase } from '../application/use-cases/InitiateWithdrawal';
import { ManageApiTokensUseCase } from '../application/use-cases/ManageApiTokens';
import { AuthenticateUserUseCase } from '../application/use-cases/AuthenticateUser';

// Middleware stores
import { InMemoryIdempotencyStore, IdempotencyStore } from '../infrastructure/http/middleware/idempotency';
import { InMemoryRateLimitStore, RateLimitStore } from '../infrastructure/http/middleware/rateLimiting';
import {
  createRedisClient,
  RedisIdempotencyStore,
  RedisRateLimitStore,
} from '../infrastructure/cache/RedisStores';
import { RedisClientType } from 'redis';

export interface Container {
  // Infrastructure
  pool: Pool;
  redisClient: RedisClientType | null;
  transactionManager: PostgresTransactionManager;

  // Repositories
  accountRepository: PostgresAccountRepository;
  transactionRepository: PostgresTransactionRepository;
  paymentMethodRepository: PostgresPaymentMethodRepository;
  apiTokenRepository: PostgresApiTokenRepository;
  userRepository: PostgresUserRepository;

  // Payment Providers
  paymentProviderFactory: PaymentProviderFactory;

  // Use Cases
  executeTransfer: ExecuteTransferUseCase;
  processDeposit: ProcessDepositUseCase;
  initiateWithdrawal: InitiateWithdrawalUseCase;
  manageApiTokens: ManageApiTokensUseCase;
  authenticateUser: AuthenticateUserUseCase;

  // Middleware stores
  idempotencyStore: IdempotencyStore;
  rateLimitStore: RateLimitStore;

  // Cleanup
  shutdown(): Promise<void>;
}

export async function createContainer(config: Config): Promise<Container> {
  // Create database pool
  const pool = new Pool({
    connectionString: config.DATABASE_URL,
    max: config.DATABASE_POOL_SIZE,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
  });

  // Test database connection
  try {
    await pool.query('SELECT 1');
    console.log('Database connection established');
  } catch (error) {
    console.error('Failed to connect to database:', error);
    throw error;
  }

  // Create transaction manager
  const transactionManager = new PostgresTransactionManager(pool);

  // Create repositories
  const accountRepository = new PostgresAccountRepository(pool);
  const transactionRepository = new PostgresTransactionRepository(pool);
  const paymentMethodRepository = new PostgresPaymentMethodRepository(pool);
  const apiTokenRepository = new PostgresApiTokenRepository(pool);
  const userRepository = new PostgresUserRepository(pool);

  // Create Redis client if configured
  let redisClient: RedisClientType | null = null;
  if (config.REDIS_URL) {
    try {
      redisClient = await createRedisClient(config.REDIS_URL);
      console.log('Redis connection established');
    } catch (error) {
      console.warn('Failed to connect to Redis, using in-memory stores:', error);
    }
  }

  // Create payment provider factory
  const providerConfig: ProviderConfig = {};

  if (config.STRIPE_API_KEY) {
    providerConfig.stripe = {
      enabled: true,
      apiKey: config.STRIPE_API_KEY,
      webhookSecret: config.STRIPE_WEBHOOK_SECRET ?? '',
    };
  }

  if (config.PAYPAL_CLIENT_ID) {
    providerConfig.paypal = {
      enabled: true,
      clientId: config.PAYPAL_CLIENT_ID,
      clientSecret: config.PAYPAL_CLIENT_SECRET ?? '',
      webhookId: config.PAYPAL_WEBHOOK_ID ?? '',
      sandbox: config.PAYPAL_SANDBOX,
    };
  }

  if (config.PIX_ENABLED && config.PIX_CLIENT_ID) {
    providerConfig.pix = {
      enabled: true,
      config: {
        provider: config.PIX_PROVIDER,
        clientId: config.PIX_CLIENT_ID,
        clientSecret: config.PIX_CLIENT_SECRET ?? '',
        baseUrl: config.PIX_BASE_URL ?? 'https://pix.example.com/api',
        receiverPixKey: config.PIX_RECEIVER_KEY ?? '',
        merchantName: config.PIX_MERCHANT_NAME,
        merchantCity: config.PIX_MERCHANT_CITY,
        certificate: config.PIX_CERTIFICATE_PATH
          ? fs.readFileSync(config.PIX_CERTIFICATE_PATH, 'utf-8')
          : '',
        certificateKey: config.PIX_CERTIFICATE_KEY_PATH
          ? fs.readFileSync(config.PIX_CERTIFICATE_KEY_PATH, 'utf-8')
          : '',
        webhookUrl: config.PIX_WEBHOOK_URL ?? '',
        webhookSecret: config.PIX_WEBHOOK_SECRET ?? '',
        sandbox: config.PIX_SANDBOX,
      },
    };
  }

  if (config.XENDIT_ENABLED && config.XENDIT_API_KEY) {
    providerConfig.xendit = {
      enabled: true,
      config: {
        apiKey: config.XENDIT_API_KEY,
        webhookToken: config.XENDIT_WEBHOOK_TOKEN ?? '',
        baseUrl: config.XENDIT_BASE_URL,
        sandbox: config.XENDIT_SANDBOX,
        businessId: config.XENDIT_BUSINESS_ID,
        defaultCountry: config.XENDIT_DEFAULT_COUNTRY,
        defaultCurrency: config.XENDIT_DEFAULT_CURRENCY,
        successRedirectUrl: config.XENDIT_SUCCESS_REDIRECT_URL,
        failureRedirectUrl: config.XENDIT_FAILURE_REDIRECT_URL,
      },
    };
  }

  const paymentProviderFactory = new PaymentProviderFactory(providerConfig);

  // Create middleware stores
  // Use Redis-based stores in production, in-memory for development
  const idempotencyStore: IdempotencyStore = redisClient
    ? new RedisIdempotencyStore(redisClient)
    : new InMemoryIdempotencyStore();
  const rateLimitStore: RateLimitStore = redisClient
    ? new RedisRateLimitStore(redisClient)
    : new InMemoryRateLimitStore();

  // Create use cases
  const executeTransfer = new ExecuteTransferUseCase(
    accountRepository,
    transactionRepository,
    transactionManager,
    {
      confirmationTokenSecret: config.TRANSFER_CONFIRMATION_SECRET,
      confirmationExpirationHours: config.TRANSFER_CONFIRMATION_EXPIRATION_HOURS,
    }
  );

  const processDeposit = new ProcessDepositUseCase(
    accountRepository,
    transactionRepository,
    paymentMethodRepository,
    paymentProviderFactory,
    transactionManager
  );

  const initiateWithdrawal = new InitiateWithdrawalUseCase(
    accountRepository,
    transactionRepository,
    paymentMethodRepository,
    paymentProviderFactory,
    transactionManager
  );

  const manageApiTokens = new ManageApiTokensUseCase(
    apiTokenRepository,
    { maxTokensPerUser: 25 }
  );

  const authenticateUser = new AuthenticateUserUseCase(
    userRepository,
    accountRepository,
    manageApiTokens,
    {
      jwtSecret: config.JWT_SECRET,
      jwtIssuer: config.JWT_ISSUER,
      jwtAudience: config.JWT_AUDIENCE,
      jwtExpiresInSeconds: config.JWT_EXPIRES_IN_SECONDS,
    }
  );

  return {
    pool,
    redisClient,
    transactionManager,
    accountRepository,
    transactionRepository,
    paymentMethodRepository,
    apiTokenRepository,
    userRepository,
    paymentProviderFactory,
    executeTransfer,
    processDeposit,
    initiateWithdrawal,
    manageApiTokens,
    authenticateUser,
    idempotencyStore,
    rateLimitStore,

    async shutdown() {
      console.log('Shutting down container...');
      if (redisClient) {
        await redisClient.quit();
        console.log('Redis connection closed');
      }
      await pool.end();
      console.log('Database pool closed');
    },
  };
}
