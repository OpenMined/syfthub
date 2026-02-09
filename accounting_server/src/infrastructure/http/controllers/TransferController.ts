/**
 * Transfer Controller
 *
 * HTTP handlers for P2P transfer operations with confirmation flow.
 *
 * Flow:
 * 1. POST /transfers - Initiate transfer (funds held, token generated)
 * 2. POST /transfers/:id/confirm - Recipient confirms with token
 * 3. POST /transfers/:id/cancel - Sender cancels pending transfer
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { TransferService } from '../../../application/ports/input/TransferService';
import {
  TransferNotFoundError,
  InvalidConfirmationTokenError,
} from '../../../application/use-cases/ExecuteTransfer';
import { Money } from '../../../domain/value-objects/Money';
import {
  AccountId,
  IdempotencyKey,
  TransactionId,
} from '../../../domain/value-objects/Identifiers';
import { Transaction } from '../../../domain/entities/Transaction';
import { InsufficientFundsError } from '../../../domain/errors/InsufficientFundsError';
import { AccountNotFoundError } from '../../../domain/errors/AccountNotFoundError';
import { InvalidAccountStateError } from '../../../domain/errors/InvalidAccountStateError';
import { InvalidTransactionStateError } from '../../../domain/errors/InvalidTransactionStateError';
import { requireScope } from '../middleware/authentication';

// Request validation schemas
const InitiateTransferSchema = z.object({
  source_account_id: z.string().uuid(),
  destination_account_id: z.string().uuid(),
  amount: z.object({
    amount: z.string().regex(/^\d+$/, 'Amount must be a positive integer string'),
    currency: z.literal('CREDIT'),
  }),
  description: z.string().max(500).optional(),
  metadata: z.record(z.unknown()).optional(),
});

const ConfirmTransferSchema = z.object({
  confirmation_token: z.string().min(1, 'Confirmation token is required'),
});

const CancelTransferSchema = z.object({
  reason: z.string().max(500).optional(),
});

export function createTransferController(transferService: TransferService): Router {
  const router = Router();

  /**
   * POST /transfers - Initiate P2P transfer
   *
   * Holds funds from sender's account and returns a confirmation token.
   * Returns 202 Accepted as the transfer is not yet complete.
   */
  router.post('/', requireScope('transfers:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      // Validate request body
      const validation = InitiateTransferSchema.safeParse(req.body);
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

      if (!idempotencyKey) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/missing-idempotency-key',
          title: 'Missing Idempotency Key',
          status: 400,
          detail: 'Idempotency-Key header is required for transfer operations',
        });
        return;
      }

      // Initiate transfer (funds held, awaiting confirmation)
      const result = await transferService.initiateTransfer({
        idempotencyKey: IdempotencyKey.from(idempotencyKey),
        sourceAccountId: AccountId.from(data.source_account_id),
        destinationAccountId: AccountId.from(data.destination_account_id),
        amount: Money.fromString(data.amount.amount, data.amount.currency),
        description: data.description,
        metadata: data.metadata,
      });

      // Return 202 Accepted - transfer is pending confirmation
      res
        .status(202)
        .header('Location', `/v1/transfers/${result.transaction.id}`)
        .json({
          ...formatTransferResponse(result.transaction),
          confirmation_token: result.confirmationToken,
          confirmation_expires_at: result.expiresAt.toISOString(),
        });
    } catch (error) {
      handleTransferError(error, res, next);
    }
  });

  /**
   * POST /transfers/:id/confirm - Confirm pending transfer
   *
   * Called by recipient with the confirmation token.
   * Transfers the held funds to recipient's account.
   */
  router.post('/:id/confirm', requireScope('transfers:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transferId = req.params['id'];

      if (!transferId) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Transfer ID is required',
        });
        return;
      }

      // Validate request body
      const validation = ConfirmTransferSchema.safeParse(req.body);
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

      // Confirm the transfer
      const transaction = await transferService.confirmTransfer({
        transactionId: TransactionId.from(transferId),
        confirmationToken: validation.data.confirmation_token,
      });

      res.status(200).json(formatTransferResponse(transaction));
    } catch (error) {
      handleTransferError(error, res, next);
    }
  });

  /**
   * POST /transfers/:id/cancel - Cancel pending transfer
   *
   * Called by sender to cancel and release held funds.
   */
  router.post('/:id/cancel', requireScope('transfers:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transferId = req.params['id'];

      if (!transferId) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Transfer ID is required',
        });
        return;
      }

      // Validate request body (optional reason)
      const validation = CancelTransferSchema.safeParse(req.body);
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

      // TODO: Verify caller is the sender (authorization check)

      // Cancel the transfer
      const transaction = await transferService.cancelTransfer({
        transactionId: TransactionId.from(transferId),
        reason: validation.data.reason,
      });

      res.status(200).json(formatTransferResponse(transaction));
    } catch (error) {
      handleTransferError(error, res, next);
    }
  });

  /**
   * GET /transfers/:id - Get transfer details
   */
  router.get('/:id', requireScope('transactions:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const transferId = req.params['id'];

      if (!transferId) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Transfer ID is required',
        });
        return;
      }

      const transaction = await transferService.getTransfer(TransactionId.from(transferId));

      if (!transaction) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Transfer ${transferId} not found`,
        });
        return;
      }

      // TODO: Add authorization check (user must own source or destination account)

      res.json(formatTransferResponse(transaction));
    } catch (error) {
      next(error);
    }
  });

  return router;
}

function formatTransferResponse(transaction: Transaction) {
  const data = transaction.toJSON();
  return {
    id: data['id'],
    type: data['type'],
    status: data['status'],
    source_account_id: data['sourceAccountId'],
    destination_account_id: data['destinationAccountId'],
    amount: data['amount'],
    fee: data['fee'],
    description: data['description'],
    created_at: data['createdAt'],
    completed_at: data['completedAt'],
    confirmation_expires_at: data['confirmationExpiresAt'],
    metadata: data['metadata'],
  };
}

function handleTransferError(error: unknown, res: Response, next: NextFunction): void {
  if (error instanceof InsufficientFundsError) {
    res.status(422).json(error.toProblemDetails('/v1/transfers'));
    return;
  }

  if (error instanceof AccountNotFoundError) {
    res.status(404).json(error.toProblemDetails('/v1/transfers'));
    return;
  }

  if (error instanceof InvalidAccountStateError) {
    res.status(409).json({
      type: 'https://api.ledger.example.com/problems/invalid-account-state',
      title: 'Invalid Account State',
      status: 409,
      detail: error.message,
    });
    return;
  }

  if (error instanceof TransferNotFoundError) {
    res.status(404).json({
      type: 'https://api.ledger.example.com/problems/not-found',
      title: 'Not Found',
      status: 404,
      detail: error.message,
    });
    return;
  }

  if (error instanceof InvalidConfirmationTokenError) {
    const isExpired = error.message.toLowerCase().includes('expired');
    res.status(isExpired ? 410 : 422).json({
      type: isExpired
        ? 'https://api.ledger.example.com/problems/token-expired'
        : 'https://api.ledger.example.com/problems/invalid-token',
      title: isExpired ? 'Token Expired' : 'Invalid Token',
      status: isExpired ? 410 : 422,
      detail: error.message,
    });
    return;
  }

  if (error instanceof InvalidTransactionStateError) {
    res.status(409).json({
      type: 'https://api.ledger.example.com/problems/invalid-transaction-state',
      title: 'Invalid Transaction State',
      status: 409,
      detail: error.message,
    });
    return;
  }

  if (error instanceof Error && error.message.includes('same account')) {
    res.status(422).json({
      type: 'https://api.ledger.example.com/problems/validation-error',
      title: 'Validation Error',
      status: 422,
      detail: 'Cannot transfer to the same account',
    });
    return;
  }

  // Pass to global error handler
  next(error);
}
