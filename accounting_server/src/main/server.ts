/**
 * Main Server Entry Point
 *
 * Creates and starts the Express application.
 */

import express, { Express, Request, Response } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import morgan from 'morgan';

import { loadConfig, Config } from './config';
import { createContainer, Container } from './container';

/**
 * Extend Express Request to include rawBody for webhook signature verification
 */
declare global {
  namespace Express {
    interface Request {
      rawBody?: Buffer;
    }
  }
}

// Controllers
import { createAccountController } from '../infrastructure/http/controllers/AccountController';
import { createTransferController } from '../infrastructure/http/controllers/TransferController';
import { createDepositController } from '../infrastructure/http/controllers/DepositController';
import { createWithdrawalController } from '../infrastructure/http/controllers/WithdrawalController';
import { createPaymentMethodController } from '../infrastructure/http/controllers/PaymentMethodController';
import { createWebhookController } from '../infrastructure/http/controllers/WebhookController';
import { createPixController } from '../infrastructure/http/controllers/PixController';
import { createXenditController } from '../infrastructure/http/controllers/XenditController';
import { createApiTokenController } from '../infrastructure/http/controllers/ApiTokenController';
import { createAuthController } from '../infrastructure/http/controllers/AuthController';

// Middleware
import { createAuthMiddleware } from '../infrastructure/http/middleware/authentication';
import { createIdempotencyMiddleware } from '../infrastructure/http/middleware/idempotency';
import { createRateLimiters } from '../infrastructure/http/middleware/rateLimiting';
import { errorHandler, notFoundHandler } from '../infrastructure/http/middleware/errorHandler';

/**
 * Get CORS origin configuration.
 * In production, CORS_ORIGIN must be explicitly set.
 * In development, allows '*' as fallback.
 */
function getCorsOrigin(config: Config): string | string[] | boolean {
  const corsOrigin = process.env.CORS_ORIGIN;

  if (corsOrigin) {
    // Support comma-separated origins
    if (corsOrigin.includes(',')) {
      return corsOrigin.split(',').map(o => o.trim());
    }
    return corsOrigin;
  }

  // In production, reject cross-origin requests by default (same-origin only)
  if (config.NODE_ENV === 'production') {
    console.warn('[SECURITY] CORS_ORIGIN not set in production. Cross-origin requests will be rejected.');
    return false;
  }

  // In development, allow all origins with a warning
  console.warn('[SECURITY] CORS_ORIGIN not set. Allowing all origins (development mode only).');
  return '*';
}

/**
 * Get trusted proxy configuration.
 * Returns the number of trusted proxies or specific IP addresses.
 */
function getTrustedProxies(): boolean | string | string[] | number {
  const trustedProxies = process.env.TRUSTED_PROXIES;

  if (!trustedProxies) {
    // Default: trust loopback and private networks (common Docker/K8s setup)
    return 'loopback';
  }

  if (trustedProxies === 'true') {
    return true;
  }

  if (trustedProxies === 'false') {
    return false;
  }

  // Check if it's a number (hop count)
  const hopCount = parseInt(trustedProxies, 10);
  if (!isNaN(hopCount)) {
    return hopCount;
  }

  // Otherwise, treat as comma-separated IP addresses
  return trustedProxies.split(',').map(ip => ip.trim());
}

async function createApp(container: Container, config: Config): Promise<Express> {
  const app = express();

  // Configure trusted proxies for accurate IP detection
  // This is critical for rate limiting and audit logging
  const trustedProxies = getTrustedProxies();
  app.set('trust proxy', trustedProxies);

  // Security middleware
  app.use(helmet());
  app.use(cors({
    origin: getCorsOrigin(config),
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Idempotency-Key'],
    exposedHeaders: ['X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset', 'Retry-After'],
    credentials: true,
  }));

  // Body parsing with raw body capture for webhook signature verification
  // The 'verify' callback stores the raw buffer before JSON parsing
  app.use(express.json({
    limit: '1mb',
    verify: (req: Request, _res: Response, buf: Buffer) => {
      // Store raw body for webhook signature verification
      // Only store for webhook routes to minimize memory overhead
      if (req.originalUrl?.startsWith('/webhooks')) {
        req.rawBody = buf;
      }
    },
  }));

  // Logging
  app.use(morgan('combined'));

  // Health check (no auth required)
  app.get('/health', async (_req, res) => {
    try {
      await container.pool.query('SELECT 1');
      res.json({
        status: 'healthy',
        version: process.env.npm_package_version ?? '1.0.0',
        checks: {
          database: { status: 'healthy' },
        },
      });
    } catch (error) {
      res.status(503).json({
        status: 'unhealthy',
        checks: {
          database: {
            status: 'unhealthy',
            message: error instanceof Error ? error.message : 'Unknown error',
          },
        },
      });
    }
  });

  // Create rate limiters
  const rateLimiters = createRateLimiters(container.rateLimitStore);

  // Auth middleware (supports both JWT and API token authentication)
  const authMiddleware = createAuthMiddleware({
    jwtSecret: config.JWT_SECRET,
    issuer: config.JWT_ISSUER,
    audience: config.JWT_AUDIENCE,
    apiTokenService: container.manageApiTokens,
  });

  // Idempotency middleware
  const idempotencyMiddleware = createIdempotencyMiddleware({
    store: container.idempotencyStore,
  });

  // Auth Routes (public, no auth required)
  const authRouter = createAuthController(container.authenticateUser);
  app.use('/auth', rateLimiters.standard, authRouter);

  // API Routes (v1)
  const v1Router = express.Router();

  // Apply auth to all v1 routes
  v1Router.use(authMiddleware);

  // Account routes
  v1Router.use(
    '/accounts',
    rateLimiters.standard,
    createAccountController(container.accountRepository, container.transactionRepository)
  );

  // Transfer routes
  v1Router.use(
    '/transfers',
    rateLimiters.transfers,
    idempotencyMiddleware,
    createTransferController(container.executeTransfer)
  );

  // Deposit routes
  v1Router.use(
    '/deposits',
    rateLimiters.deposits,
    idempotencyMiddleware,
    createDepositController(container.processDeposit, container.transactionRepository)
  );

  // Withdrawal routes
  v1Router.use(
    '/withdrawals',
    rateLimiters.withdrawals,
    idempotencyMiddleware,
    createWithdrawalController(container.initiateWithdrawal, container.transactionRepository)
  );

  // Payment method routes
  v1Router.use(
    '/payment-methods',
    rateLimiters.standard,
    createPaymentMethodController({
      paymentMethodRepository: container.paymentMethodRepository,
      accountRepository: container.accountRepository,
      providerFactory: container.paymentProviderFactory,
    })
  );

  // PIX routes (Brazilian instant payment)
  v1Router.use(
    '/pix',
    rateLimiters.standard,
    idempotencyMiddleware,
    createPixController(container.paymentProviderFactory)
  );

  // Xendit routes (Southeast Asia payments)
  v1Router.use(
    '/xendit',
    rateLimiters.standard,
    idempotencyMiddleware,
    createXenditController(container.paymentProviderFactory)
  );

  // API token management routes
  v1Router.use(
    '/api-tokens',
    rateLimiters.standard,
    createApiTokenController(container.manageApiTokens)
  );

  // Mount v1 API
  app.use('/v1', v1Router);

  // Webhook routes (no auth, different rate limit)
  const webhookRouter = createWebhookController({
    depositService: container.processDeposit,
    withdrawalService: container.initiateWithdrawal,
    transactionRepository: container.transactionRepository,
    providerFactory: container.paymentProviderFactory,
  });
  app.use('/webhooks', rateLimiters.webhooks, webhookRouter);

  // 404 handler
  app.use(notFoundHandler);

  // Global error handler
  app.use(errorHandler);

  return app;
}

async function main(): Promise<void> {
  console.log('Starting Unified Global Ledger API...');

  // Load configuration
  const config = loadConfig();
  console.log(`Environment: ${config.NODE_ENV}`);

  // Create dependency container
  const container = await createContainer(config);

  // Create Express app
  const app = await createApp(container, config);

  // Start server
  const server = app.listen(config.PORT, () => {
    console.log(`Server listening on port ${config.PORT}`);
    console.log(`Health check: http://localhost:${config.PORT}/health`);
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    console.log(`\nReceived ${signal}. Starting graceful shutdown...`);

    server.close(async () => {
      console.log('HTTP server closed');
      await container.shutdown();
      console.log('Shutdown complete');
      process.exit(0);
    });

    // Force exit after 30 seconds
    setTimeout(() => {
      console.error('Forced shutdown after timeout');
      process.exit(1);
    }, 30000);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

// Run if this is the main module
main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});

export { createApp };
