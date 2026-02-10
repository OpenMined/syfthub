/**
 * Account Controller
 *
 * HTTP handlers for account management operations.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { Account } from '../../../domain/entities/Account';
import { AccountRepository } from '../../../application/ports/output/AccountRepository';
import { TransactionRepository } from '../../../application/ports/output/TransactionRepository';
import { Money } from '../../../domain/value-objects/Money';
import { AccountId, UserId } from '../../../domain/value-objects/Identifiers';
import { AuthenticatedRequest, requireScope } from '../middleware/authentication';

// Request validation schemas
const CreateAccountSchema = z.object({
  type: z.enum(['user', 'escrow']),
  metadata: z.record(z.unknown()).optional(),
});

const ListAccountsQuerySchema = z.object({
  status: z.enum(['active', 'frozen', 'closed']).optional(),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

export function createAccountController(
  accountRepository: AccountRepository,
  transactionRepository: TransactionRepository
): Router {
  const router = Router();

  /**
   * POST /accounts - Create a new account
   */
  router.post('/', requireScope('accounts:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // Validate request body
      const validation = CreateAccountSchema.safeParse(req.body);
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

      // Create account
      const account = Account.create({
        userId: authReq.user.id,
        type: data.type,
        metadata: data.metadata,
      });

      await accountRepository.save(account);

      res.status(201)
        .header('Location', `/v1/accounts/${account.id}`)
        .json(formatAccountResponse(account));

    } catch (error) {
      next(error);
    }
  });

  /**
   * GET /accounts - List user's accounts
   */
  router.get('/', requireScope('accounts:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // Validate query params
      const validation = ListAccountsQuerySchema.safeParse(req.query);
      if (!validation.success) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Invalid query parameters',
          errors: validation.error.errors.map((e) => ({
            field: e.path.join('.'),
            message: e.message,
          })),
        });
        return;
      }

      const accounts = await accountRepository.findByUserId(authReq.user.id);

      // Apply status filter if provided
      let filtered = accounts;
      if (validation.data.status) {
        filtered = accounts.filter((a) => a.status === validation.data.status);
      }

      res.json({
        data: filtered.map(formatAccountResponse),
        pagination: {
          has_more: false,
          next_cursor: null,
        },
      });

    } catch (error) {
      next(error);
    }
  });

  /**
   * GET /accounts/:id - Get account details
   */
  router.get('/:id', requireScope('accounts:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;
      const accountId = AccountId.from(req.params.id!);

      const account = await accountRepository.findById(accountId);

      if (!account) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Account ${req.params.id} not found`,
        });
        return;
      }

      // Authorization: user must own the account
      if (account.userId !== authReq.user.id) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this account',
        });
        return;
      }

      res.json(formatAccountResponse(account));

    } catch (error) {
      next(error);
    }
  });

  /**
   * GET /accounts/:id/balance - Get current balance
   */
  router.get('/:id/balance', requireScope('accounts:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;
      const accountId = AccountId.from(req.params.id!);

      const account = await accountRepository.findById(accountId);

      if (!account) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Account ${req.params.id} not found`,
        });
        return;
      }

      // Authorization
      if (account.userId !== authReq.user.id) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this account',
        });
        return;
      }

      const pending = account.pendingAmount;

      res.json({
        account_id: account.id,
        balance: account.balance.toJSON(),
        available_balance: account.availableBalance.toJSON(),
        pending_deposits: Money.credits(0n).toJSON(), // Would need separate tracking
        pending_withdrawals: pending.toJSON(),
        as_of: new Date().toISOString(),
      });

    } catch (error) {
      next(error);
    }
  });

  /**
   * GET /accounts/:id/transactions - List account transactions
   */
  router.get('/:id/transactions', requireScope('transactions:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;
      const accountId = AccountId.from(req.params.id!);

      // Verify account ownership
      const account = await accountRepository.findById(accountId);
      if (!account) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Account ${req.params.id} not found`,
        });
        return;
      }

      if (account.userId !== authReq.user.id) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this account',
        });
        return;
      }

      // Get transactions
      const limit = Math.min(parseInt(req.query.limit as string) || 20, 100);
      const cursor = req.query.cursor as string | undefined;

      const result = await transactionRepository.findByAccountId(accountId, {
        limit,
        cursor,
        sortOrder: 'desc',
      });

      res.json({
        data: result.data.map((txn) => {
          const data = txn.toJSON();
          return {
            id: data.id,
            type: data.type,
            status: data.status,
            source_account_id: data.sourceAccountId,
            destination_account_id: data.destinationAccountId,
            amount: data.amount,
            fee: data.fee,
            created_at: data.createdAt,
            completed_at: data.completedAt,
          };
        }),
        pagination: {
          has_more: result.pagination.hasMore,
          next_cursor: result.pagination.nextCursor,
        },
      });

    } catch (error) {
      next(error);
    }
  });

  return router;
}

function formatAccountResponse(account: Account) {
  return {
    id: account.id,
    type: account.type,
    status: account.status,
    balance: account.balance.toJSON(),
    available_balance: account.availableBalance.toJSON(),
    created_at: account.createdAt.toISOString(),
    updated_at: account.updatedAt.toISOString(),
    metadata: account.metadata,
  };
}
