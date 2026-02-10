/**
 * Deposit Controller
 *
 * HTTP handlers for deposit operations (external → internal).
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { DepositService } from '../../../application/ports/input/DepositService';
import { TransactionRepository } from '../../../application/ports/output/TransactionRepository';
import { Money } from '../../../domain/value-objects/Money';
import {
  AccountId,
  IdempotencyKey,
  TransactionId,
  PaymentMethodId,
} from '../../../domain/value-objects/Identifiers';
import { AuthenticatedRequest, requireScope } from '../middleware/authentication';

// Request validation schemas
const CreateDepositSchema = z.object({
  account_id: z.string().uuid(),
  amount: z.object({
    amount: z.string().regex(/^\d+$/, 'Amount must be a positive integer string'),
    currency: z.string().min(1),
  }),
  payment_method_id: z.string().uuid(),
  metadata: z.record(z.unknown()).optional(),
});

export function createDepositController(
  depositService: DepositService,
  transactionRepository: TransactionRepository
): Router {
  const router = Router();

  /**
   * POST /deposits - Initiate deposit
   */
  router.post('/', requireScope('deposits:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // Validate request body
      const validation = CreateDepositSchema.safeParse(req.body);
      if (!validation.success) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/validation-error',
          title: 'Validation Error',
          status: 422,
          detail: 'Request body validation failed',
          errors: validation.error.errors.map((e) => ({
            field: e.path.join('.'),
            message: e.message,
          })),
        });
        return;
      }

      const data = validation.data;
      const idempotencyKey = req.headers['idempotency-key'] as string;

      // TODO: Verify account belongs to authenticated user

      // Initiate deposit
      const result = await depositService.initiateDeposit({
        idempotencyKey: IdempotencyKey.from(idempotencyKey),
        accountId: AccountId.from(data.account_id),
        amount: Money.fromString(data.amount.amount, data.amount.currency as 'CREDIT'),
        paymentMethodId: PaymentMethodId.from(data.payment_method_id),
        metadata: data.metadata,
      });

      const transaction = result.transaction;
      const responseData = formatDepositResponse(transaction);

      // Add client secret if action required (e.g., 3DS)
      if (result.requiresAction && result.clientSecret) {
        Object.assign(responseData, { client_secret: result.clientSecret });
      }

      // Return 202 Accepted for async processing
      res.status(202)
        .header('Location', `/v1/deposits/${transaction.id}`)
        .header('Retry-After', '5')
        .json(responseData);

    } catch (error) {
      handleDepositError(error, res, next);
    }
  });

  /**
   * GET /deposits/:id - Get deposit status
   */
  router.get('/:id', requireScope('transactions:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transactionId = TransactionId.from(req.params.id!);

      const transaction = await depositService.getDeposit(transactionId);

      if (!transaction) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Deposit ${req.params.id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this deposit

      const response = formatDepositResponse(transaction);

      // Add Retry-After header if still pending
      if (transaction.status === 'pending' || transaction.status === 'processing') {
        res.header('Retry-After', '10');
      }

      res.json(response);

    } catch (error) {
      next(error);
    }
  });

  return router;
}

function formatDepositResponse(transaction: Awaited<ReturnType<DepositService['getDeposit']>>) {
  if (!transaction) return null;

  const data = transaction.toJSON();
  const amount = data.amount as { amount: string; currency: string };
  const fee = data.fee as { amount: string; currency: string };

  // Calculate net credits
  const netCredits = BigInt(amount.amount) - BigInt(fee.amount);

  return {
    id: data.id,
    status: data.status,
    account_id: data.destinationAccountId,
    amount: data.amount,
    credits_amount: {
      amount: amount.amount,
      currency: 'CREDIT',
    },
    fee: data.fee,
    net_credits: {
      amount: netCredits.toString(),
      currency: 'CREDIT',
    },
    provider_code: data.providerCode,
    external_reference: data.externalReference,
    created_at: data.createdAt,
    completed_at: data.completedAt,
    metadata: data.metadata,
  };
}

function handleDepositError(
  error: unknown,
  res: Response,
  next: NextFunction
): void {
  if (error instanceof Error) {
    if (error.name === 'AccountNotFoundError') {
      res.status(404).json({
        type: 'https://api.ledger.example.com/problems/not-found',
        title: 'Not Found',
        status: 404,
        detail: error.message,
      });
      return;
    }

    if (error.name === 'PaymentMethodNotFoundError') {
      res.status(404).json({
        type: 'https://api.ledger.example.com/problems/payment-method-not-found',
        title: 'Payment Method Not Found',
        status: 404,
        detail: error.message,
      });
      return;
    }

    if (error.name === 'InvalidPaymentMethodError') {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/invalid-payment-method',
        title: 'Invalid Payment Method',
        status: 422,
        detail: error.message,
      });
      return;
    }

    if (error.name === 'InvalidAccountStateError') {
      res.status(409).json({
        type: 'https://api.ledger.example.com/problems/invalid-account-state',
        title: 'Invalid Account State',
        status: 409,
        detail: error.message,
      });
      return;
    }
  }

  next(error);
}
