/**
 * Withdrawal Controller
 *
 * HTTP handlers for withdrawal operations (internal → external).
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { WithdrawalService } from '../../../application/ports/input/WithdrawalService';
import { TransactionRepository } from '../../../application/ports/output/TransactionRepository';
import { Money } from '../../../domain/value-objects/Money';
import {
  AccountId,
  IdempotencyKey,
  TransactionId,
  PaymentMethodId,
} from '../../../domain/value-objects/Identifiers';
import { AuthenticatedRequest, requireScope } from '../middleware/authentication';
import { InsufficientFundsError } from '../../../domain/errors/InsufficientFundsError';

// Request validation schemas
const CreateWithdrawalSchema = z.object({
  account_id: z.string().uuid(),
  amount: z.object({
    amount: z.string().regex(/^\d+$/, 'Amount must be a positive integer string'),
    currency: z.literal('CREDIT'),
  }),
  payment_method_id: z.string().uuid(),
  description: z.string().max(500).optional(),
  metadata: z.record(z.unknown()).optional(),
});

export function createWithdrawalController(
  withdrawalService: WithdrawalService,
  transactionRepository: TransactionRepository
): Router {
  const router = Router();

  /**
   * POST /withdrawals - Initiate withdrawal
   */
  router.post('/', requireScope('withdrawals:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // Validate request body
      const validation = CreateWithdrawalSchema.safeParse(req.body);
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

      // Initiate withdrawal
      const result = await withdrawalService.initiateWithdrawal({
        idempotencyKey: IdempotencyKey.from(idempotencyKey),
        accountId: AccountId.from(data.account_id),
        amount: Money.fromString(data.amount.amount, data.amount.currency),
        paymentMethodId: PaymentMethodId.from(data.payment_method_id),
        description: data.description,
        metadata: data.metadata,
      });

      const transaction = result.transaction;
      const responseData = formatWithdrawalResponse(transaction, result.estimatedCompletion);

      // Return 202 Accepted for async processing
      res.status(202)
        .header('Location', `/v1/withdrawals/${transaction.id}`)
        .header('Retry-After', '30')
        .json(responseData);

    } catch (error) {
      handleWithdrawalError(error, res, next);
    }
  });

  /**
   * GET /withdrawals/:id - Get withdrawal status
   */
  router.get('/:id', requireScope('transactions:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transactionId = TransactionId.from(req.params.id!);

      const transaction = await withdrawalService.getWithdrawal(transactionId);

      if (!transaction) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Withdrawal ${req.params.id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this withdrawal

      const response = formatWithdrawalResponse(transaction);

      // Add Retry-After header if still pending
      if (transaction.status === 'pending' || transaction.status === 'processing') {
        res.header('Retry-After', '60');
      }

      res.json(response);

    } catch (error) {
      next(error);
    }
  });

  /**
   * POST /withdrawals/:id/cancel - Cancel pending withdrawal
   */
  router.post('/:id/cancel', requireScope('withdrawals:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transactionId = TransactionId.from(req.params.id!);

      // TODO: Verify user has access to this withdrawal

      const transaction = await withdrawalService.cancelWithdrawal({
        transactionId,
      });

      res.json(formatWithdrawalResponse(transaction));

    } catch (error) {
      handleWithdrawalError(error, res, next);
    }
  });

  return router;
}

function formatWithdrawalResponse(
  transaction: NonNullable<Awaited<ReturnType<WithdrawalService['getWithdrawal']>>>,
  estimatedCompletion?: Date
) {
  const data = transaction.toJSON();
  const amount = data.amount as { amount: string; currency: string };
  const fee = data.fee as { amount: string; currency: string };

  // Calculate destination amount (amount - fee in destination currency)
  // In a real system, this would involve exchange rate conversion
  const destinationAmount = BigInt(amount.amount) - BigInt(fee.amount);

  return {
    id: data.id,
    status: data.status,
    account_id: data.sourceAccountId,
    amount: data.amount,
    destination_amount: {
      amount: destinationAmount.toString(),
      currency: 'USD', // Would be determined by payment method
    },
    fee: data.fee,
    provider_code: data.providerCode,
    payment_method_id: data.metadata && (data.metadata as Record<string, unknown>).payment_method_id,
    external_reference: data.externalReference,
    created_at: data.createdAt,
    completed_at: data.completedAt,
    estimated_completion: estimatedCompletion?.toISOString() ?? null,
    failure_reason: data.errorDetails
      ? ((data.errorDetails as Record<string, unknown>).reason as string)
      : null,
    metadata: data.metadata,
  };
}

function handleWithdrawalError(
  error: unknown,
  res: Response,
  next: NextFunction
): void {
  if (error instanceof InsufficientFundsError) {
    res.status(422).json(error.toProblemDetails('/v1/withdrawals'));
    return;
  }

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

    if (error.name === 'InvalidTransactionStateError') {
      res.status(409).json({
        type: 'https://api.ledger.example.com/problems/invalid-transaction-state',
        title: 'Invalid Transaction State',
        status: 409,
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
