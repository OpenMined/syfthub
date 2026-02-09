/**
 * Webhook Controller
 *
 * HTTP handlers for payment provider webhooks.
 * Processes callbacks from Stripe, PayPal, and other providers to update transaction states.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { DepositService } from '../../../application/ports/input/DepositService';
import { WithdrawalService } from '../../../application/ports/input/WithdrawalService';
import { TransactionRepository } from '../../../application/ports/output/TransactionRepository';
import {
  PaymentProviderGateway,
  ProviderWebhookEvent,
  WebhookEventType,
} from '../../../application/ports/output/PaymentProviderGateway';
import { TransactionId, ExternalReference } from '../../../domain/value-objects/Identifiers';
import { ProviderCode } from '../../../domain/entities/Transaction';

/**
 * Factory to get the appropriate payment provider gateway
 */
interface PaymentProviderFactory {
  getProvider(providerCode: string): PaymentProviderGateway;
  getProviderByWebhookPath(path: string): PaymentProviderGateway | null;
}

/**
 * Logger interface for webhook processing
 */
interface WebhookLogger {
  info(message: string, data?: Record<string, unknown>): void;
  warn(message: string, data?: Record<string, unknown>): void;
  error(message: string, data?: Record<string, unknown>): void;
}

const defaultLogger: WebhookLogger = {
  info: (message, data) => console.log(`[WEBHOOK] ${message}`, data ?? ''),
  warn: (message, data) => console.warn(`[WEBHOOK] ${message}`, data ?? ''),
  error: (message, data) => console.error(`[WEBHOOK] ${message}`, data ?? ''),
};

interface WebhookControllerDependencies {
  depositService: DepositService;
  withdrawalService: WithdrawalService;
  transactionRepository: TransactionRepository;
  providerFactory: PaymentProviderFactory;
  logger?: WebhookLogger;
}

export function createWebhookController(
  deps: WebhookControllerDependencies
): Router {
  const router = Router();
  const logger = deps.logger ?? defaultLogger;

  /**
   * POST /webhooks/stripe - Stripe webhooks
   */
  router.post(
    '/stripe',
    createProviderWebhookHandler('stripe', deps, logger)
  );

  /**
   * POST /webhooks/paypal - PayPal webhooks
   */
  router.post(
    '/paypal',
    createProviderWebhookHandler('paypal', deps, logger)
  );

  /**
   * POST /webhooks/pix - Brazilian PIX webhooks
   */
  router.post(
    '/pix',
    createProviderWebhookHandler('pix', deps, logger)
  );

  /**
   * POST /webhooks/xendit - Xendit (Southeast Asia) webhooks
   */
  router.post(
    '/xendit',
    createProviderWebhookHandler('xendit', deps, logger)
  );

  /**
   * POST /webhooks/:provider - Generic provider webhook endpoint
   */
  router.post(
    '/:provider',
    async (req: Request, res: Response, next: NextFunction) => {
      const providerCode = req.params['provider'];

      if (!providerCode) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/invalid-provider',
          title: 'Invalid Provider',
          status: 400,
          detail: 'Provider code is required',
        });
        return;
      }

      // Skip if already handled by specific route
      if (providerCode === 'stripe' || providerCode === 'paypal' || providerCode === 'pix' || providerCode === 'xendit') {
        next();
        return;
      }

      const handler = createProviderWebhookHandler(
        providerCode as ProviderCode,
        deps,
        logger
      );
      return handler(req, res, next);
    }
  );

  return router;
}

/**
 * Creates a webhook handler for a specific payment provider
 */
function createProviderWebhookHandler(
  providerCode: ProviderCode,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): (req: Request, res: Response, next: NextFunction) => Promise<void> {
  return async (req: Request, res: Response, next: NextFunction) => {
    const startTime = Date.now();

    try {
      // Get raw body for signature verification
      const rawBody = getRawBody(req);
      const signature = getWebhookSignature(req, providerCode);

      if (!signature) {
        logger.warn('Missing webhook signature', { provider: providerCode });
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/unauthorized',
          title: 'Unauthorized',
          status: 401,
          detail: 'Missing webhook signature',
        });
        return;
      }

      // Get the provider gateway
      let provider: PaymentProviderGateway;
      try {
        provider = deps.providerFactory.getProvider(providerCode);
      } catch {
        logger.warn('Unknown provider', { provider: providerCode });
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/invalid-provider',
          title: 'Invalid Provider',
          status: 400,
          detail: `Unknown provider: ${providerCode}`,
        });
        return;
      }

      // Verify signature
      const isValid = provider.verifyWebhookSignature(rawBody, signature);
      if (!isValid) {
        logger.warn('Invalid webhook signature', { provider: providerCode });
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/unauthorized',
          title: 'Unauthorized',
          status: 401,
          detail: 'Invalid webhook signature',
        });
        return;
      }

      // Parse the event
      const event = provider.parseWebhookEvent(rawBody);

      logger.info('Webhook received', {
        provider: providerCode,
        eventType: event.type,
        deliveryId: event.deliveryId,
      });

      // Process the event
      await processWebhookEvent(event, providerCode, deps, logger);

      // Return 200 OK to acknowledge receipt
      const processingTime = Date.now() - startTime;
      logger.info('Webhook processed', {
        provider: providerCode,
        eventType: event.type,
        deliveryId: event.deliveryId,
        processingTimeMs: processingTime,
      });

      res.status(200).json({
        received: true,
        deliveryId: event.deliveryId,
      });
    } catch (error) {
      logger.error('Webhook processing failed', {
        provider: providerCode,
        error: error instanceof Error ? error.message : 'Unknown error',
      });

      // Still return 200 to prevent provider from retrying
      // Log the error for investigation but don't fail the webhook
      res.status(200).json({
        received: true,
        processed: false,
        error: 'Internal processing error',
      });
    }
  };
}

/**
 * Process a webhook event based on its type
 */
async function processWebhookEvent(
  event: ProviderWebhookEvent,
  providerCode: ProviderCode,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const eventHandlers: Record<
    WebhookEventType,
    (event: ProviderWebhookEvent, providerCode: ProviderCode) => Promise<void>
  > = {
    'payment_intent.succeeded': async (evt) => {
      await handlePaymentSucceeded(evt, deps, logger);
    },
    'payment_intent.failed': async (evt) => {
      await handlePaymentFailed(evt, deps, logger);
    },
    'payout.paid': async (evt) => {
      await handlePayoutCompleted(evt, deps, logger);
    },
    'payout.failed': async (evt) => {
      await handlePayoutFailed(evt, deps, logger);
    },
    'refund.succeeded': async (evt) => {
      await handleRefundSucceeded(evt, deps, logger);
    },
    'refund.failed': async (evt) => {
      await handleRefundFailed(evt, deps, logger);
    },
    'payment_method.verified': async (evt) => {
      await handlePaymentMethodVerified(evt, deps, logger);
    },
  };

  const handler = eventHandlers[event.type];
  if (handler) {
    await handler(event, providerCode);
  } else {
    logger.warn('Unhandled webhook event type', {
      eventType: event.type,
      deliveryId: event.deliveryId,
    });
  }
}

/**
 * Handle successful payment (deposit completed)
 */
async function handlePaymentSucceeded(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const transactionId = data['metadata']
    ? (data['metadata'] as Record<string, string>)['transaction_id']
    : null;
  const externalId = data['id'] as string;

  if (!transactionId) {
    logger.warn('Payment succeeded event missing transaction_id', {
      externalId,
      deliveryId: event.deliveryId,
    });
    return;
  }

  try {
    await deps.depositService.completeDeposit({
      transactionId: TransactionId.from(transactionId),
      externalReference: externalId,
    });

    logger.info('Deposit completed via webhook', {
      transactionId,
      externalId,
    });
  } catch (error) {
    logger.error('Failed to complete deposit', {
      transactionId,
      externalId,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    throw error;
  }
}

/**
 * Handle failed payment (deposit failed)
 */
async function handlePaymentFailed(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const transactionId = data['metadata']
    ? (data['metadata'] as Record<string, string>)['transaction_id']
    : null;
  const externalId = data['id'] as string;
  const errorCode = data['last_payment_error']
    ? ((data['last_payment_error'] as Record<string, unknown>)['code'] as string)
    : undefined;
  const errorMessage = data['last_payment_error']
    ? ((data['last_payment_error'] as Record<string, unknown>)['message'] as string)
    : undefined;

  if (!transactionId) {
    logger.warn('Payment failed event missing transaction_id', {
      externalId,
      deliveryId: event.deliveryId,
    });
    return;
  }

  try {
    await deps.depositService.failDeposit({
      transactionId: TransactionId.from(transactionId),
      reason: errorMessage ?? 'Payment failed',
      errorDetails: {
        code: errorCode,
        externalId,
      },
    });

    logger.info('Deposit failed via webhook', {
      transactionId,
      externalId,
      errorCode,
    });
  } catch (error) {
    logger.error('Failed to mark deposit as failed', {
      transactionId,
      externalId,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    throw error;
  }
}

/**
 * Handle completed payout (withdrawal completed)
 */
async function handlePayoutCompleted(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const transactionId = data['metadata']
    ? (data['metadata'] as Record<string, string>)['transaction_id']
    : null;
  const externalId = data['id'] as string;

  if (!transactionId) {
    // Try to find by external reference
    const transaction = await deps.transactionRepository.findByExternalReference(
      ExternalReference.from(externalId)
    );

    if (!transaction) {
      logger.warn('Payout completed event: transaction not found', {
        externalId,
        deliveryId: event.deliveryId,
      });
      return;
    }

    await deps.withdrawalService.completeWithdrawal({
      transactionId: transaction.id as TransactionId,
      externalReference: externalId,
    });

    logger.info('Withdrawal completed via webhook (by external reference)', {
      transactionId: transaction.id,
      externalId,
    });
    return;
  }

  try {
    await deps.withdrawalService.completeWithdrawal({
      transactionId: TransactionId.from(transactionId),
      externalReference: externalId,
    });

    logger.info('Withdrawal completed via webhook', {
      transactionId,
      externalId,
    });
  } catch (error) {
    logger.error('Failed to complete withdrawal', {
      transactionId,
      externalId,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    throw error;
  }
}

/**
 * Handle failed payout (withdrawal failed)
 */
async function handlePayoutFailed(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const transactionId = data['metadata']
    ? (data['metadata'] as Record<string, string>)['transaction_id']
    : null;
  const externalId = data['id'] as string;
  const failureReason = data['failure_message'] as string | undefined;
  const failureCode = data['failure_code'] as string | undefined;

  if (!transactionId) {
    // Try to find by external reference
    const transaction = await deps.transactionRepository.findByExternalReference(
      ExternalReference.from(externalId)
    );

    if (!transaction) {
      logger.warn('Payout failed event: transaction not found', {
        externalId,
        deliveryId: event.deliveryId,
      });
      return;
    }

    await deps.withdrawalService.failWithdrawal({
      transactionId: transaction.id as TransactionId,
      reason: failureReason ?? 'Payout failed',
      errorDetails: {
        code: failureCode,
        externalId,
      },
    });

    logger.info('Withdrawal failed via webhook (by external reference)', {
      transactionId: transaction.id,
      externalId,
    });
    return;
  }

  try {
    await deps.withdrawalService.failWithdrawal({
      transactionId: TransactionId.from(transactionId),
      reason: failureReason ?? 'Payout failed',
      errorDetails: {
        code: failureCode,
        externalId,
      },
    });

    logger.info('Withdrawal failed via webhook', {
      transactionId,
      externalId,
      failureCode,
    });
  } catch (error) {
    logger.error('Failed to mark withdrawal as failed', {
      transactionId,
      externalId,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    throw error;
  }
}

/**
 * Handle successful refund
 */
async function handleRefundSucceeded(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const refundId = data['id'] as string;
  const chargeId = data['charge'] as string | undefined;
  const paymentIntentId = data['payment_intent'] as string | undefined;

  logger.info('Refund succeeded', {
    refundId,
    chargeId,
    paymentIntentId,
    deliveryId: event.deliveryId,
  });

  // In a full implementation, you would:
  // 1. Find the original deposit transaction by chargeId/paymentIntentId
  // 2. Create a refund transaction
  // 3. Debit the account for the refund amount
  // This would be handled by a RefundService
}

/**
 * Handle failed refund
 */
async function handleRefundFailed(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const refundId = data['id'] as string;
  const reason = data['failure_reason'] as string | undefined;

  logger.warn('Refund failed', {
    refundId,
    reason,
    deliveryId: event.deliveryId,
  });

  // In a full implementation, handle refund failure
}

/**
 * Handle payment method verification
 */
async function handlePaymentMethodVerified(
  event: ProviderWebhookEvent,
  deps: WebhookControllerDependencies,
  logger: WebhookLogger
): Promise<void> {
  const data = event.data;
  const paymentMethodId = data['id'] as string;

  logger.info('Payment method verified', {
    paymentMethodId,
    deliveryId: event.deliveryId,
  });

  // In a full implementation:
  // 1. Find the PaymentMethod by externalId
  // 2. Update its status to 'verified'
}

/**
 * Get raw body from request for signature verification
 */
function getRawBody(req: Request): string {
  // If using express.raw() middleware, body is a Buffer
  if (Buffer.isBuffer(req.body)) {
    return req.body.toString('utf8');
  }

  // If using express.json(), need to re-stringify
  // Note: This may not preserve exact formatting, which could break signatures
  // In production, use express.raw() for webhook endpoints
  if (typeof req.body === 'object') {
    return JSON.stringify(req.body);
  }

  return String(req.body);
}

/**
 * Get webhook signature from request headers based on provider
 */
function getWebhookSignature(req: Request, providerCode: ProviderCode): string | null {
  const headerMap: Record<string, string> = {
    stripe: 'stripe-signature',
    paypal: 'paypal-transmission-sig',
    pix: 'x-webhook-signature',
    xendit: 'x-callback-token',
    bank_transfer: 'x-webhook-signature',
    manual: 'x-webhook-signature',
  };

  const headerName = headerMap[providerCode] ?? 'x-webhook-signature';
  const signature = req.headers[headerName];

  if (Array.isArray(signature)) {
    return signature[0] ?? null;
  }

  return signature ?? null;
}
