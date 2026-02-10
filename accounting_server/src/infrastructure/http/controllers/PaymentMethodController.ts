/**
 * Payment Method Controller
 *
 * HTTP handlers for payment method operations.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { PaymentMethod, PaymentMethodType } from '../../../domain/entities/PaymentMethod';
import { ProviderCode } from '../../../domain/entities/Transaction';
import { AccountId, PaymentMethodId } from '../../../domain/value-objects/Identifiers';
import { PaymentProviderGateway } from '../../../application/ports/output/PaymentProviderGateway';
import { AuthenticatedRequest, requireScope } from '../middleware/authentication';

/**
 * Payment method repository interface
 */
interface PaymentMethodRepository {
  findById(id: string): Promise<PaymentMethod | null>;
  findByAccountId(accountId: string): Promise<PaymentMethod[]>;
  findByExternalId(externalId: string): Promise<PaymentMethod | null>;
  save(paymentMethod: PaymentMethod): Promise<void>;
  update(paymentMethod: PaymentMethod): Promise<void>;
  delete(id: string): Promise<void>;
  clearDefaultForAccount(accountId: string): Promise<void>;
  countByAccountId(accountId: string): Promise<number>;
}

/**
 * Account repository interface (for validation)
 */
interface AccountRepository {
  findById(id: AccountId): Promise<{ id: AccountId } | null>;
}

/**
 * Factory to get the appropriate payment provider
 */
interface PaymentProviderFactory {
  getProvider(providerCode: string): PaymentProviderGateway;
}

// Request validation schemas
const CreatePaymentMethodSchema = z.object({
  account_id: z.string().uuid(),
  provider_code: z.enum(['stripe', 'paypal', 'bank_transfer', 'xendit', 'pix']),
  provider_token: z.string().min(1),
  type: z.enum(['card', 'bank_account', 'wallet']),
  set_as_default: z.boolean().default(false),
  metadata: z.record(z.unknown()).optional(),
});

const UpdatePaymentMethodSchema = z.object({
  display_name: z.string().max(100).optional(),
  set_as_default: z.boolean().optional(),
});

const VerifyPaymentMethodSchema = z.object({
  verification_data: z.record(z.unknown()),
});

interface PaymentMethodControllerDependencies {
  paymentMethodRepository: PaymentMethodRepository;
  accountRepository: AccountRepository;
  providerFactory: PaymentProviderFactory;
  maxPaymentMethodsPerAccount?: number;
}

export function createPaymentMethodController(
  deps: PaymentMethodControllerDependencies
): Router {
  const router = Router();
  const maxPaymentMethods = deps.maxPaymentMethodsPerAccount ?? 10;

  /**
   * POST /payment-methods - Add a new payment method
   */
  router.post('/', requireScope('payment-methods:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // Validate request body
      const validation = CreatePaymentMethodSchema.safeParse(req.body);
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

      // Verify account exists
      const account = await deps.accountRepository.findById(
        AccountId.from(data.account_id)
      );
      if (!account) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Account ${data.account_id} not found`,
        });
        return;
      }

      // TODO: Verify account belongs to authenticated user

      // Check payment method limit
      const count = await deps.paymentMethodRepository.countByAccountId(data.account_id);
      if (count >= maxPaymentMethods) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/payment-method-limit',
          title: 'Payment Method Limit Reached',
          status: 422,
          detail: `Maximum of ${maxPaymentMethods} payment methods allowed per account`,
        });
        return;
      }

      // Tokenize with provider
      const provider = deps.providerFactory.getProvider(data.provider_code);

      const tokenized = await provider.tokenizePaymentMethod({
        providerToken: data.provider_token,
        type: data.type,
        metadata: data.metadata as Record<string, string>,
      });

      // Check if this external ID is already registered
      const existing = await deps.paymentMethodRepository.findByExternalId(
        tokenized.externalId
      );
      if (existing) {
        res.status(409).json({
          type: 'https://api.ledger.example.com/problems/duplicate-payment-method',
          title: 'Duplicate Payment Method',
          status: 409,
          detail: 'This payment method is already registered',
        });
        return;
      }

      // Create payment method
      const paymentMethod = PaymentMethod.create({
        accountId: AccountId.from(data.account_id),
        providerCode: data.provider_code as ProviderCode,
        type: tokenized.type,
        externalId: tokenized.externalId,
        displayName: tokenized.displayName,
        isWithdrawable: tokenized.isWithdrawable,
        expiresAt: tokenized.expiresAt,
        metadata: data.metadata,
      });

      // Mark as verified if provider confirms it
      paymentMethod.verify();

      // Set as default if requested (and clear existing default)
      if (data.set_as_default) {
        await deps.paymentMethodRepository.clearDefaultForAccount(data.account_id);
        paymentMethod.setDefault(true);
      }

      // Save
      await deps.paymentMethodRepository.save(paymentMethod);

      res.status(201)
        .header('Location', `/v1/payment-methods/${paymentMethod.id}`)
        .json(formatPaymentMethodResponse(paymentMethod));

    } catch (error) {
      handlePaymentMethodError(error, res, next);
    }
  });

  /**
   * GET /payment-methods - List payment methods
   */
  router.get('/', requireScope('payment-methods:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const accountId = req.query['account_id'] as string;

      if (!accountId) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'account_id query parameter is required',
        });
        return;
      }

      // TODO: Verify account belongs to authenticated user

      const paymentMethods = await deps.paymentMethodRepository.findByAccountId(
        accountId
      );

      res.json({
        data: paymentMethods.map(formatPaymentMethodResponse),
      });

    } catch (error) {
      next(error);
    }
  });

  /**
   * GET /payment-methods/:id - Get payment method
   */
  router.get('/:id', requireScope('payment-methods:read'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params['id'];

      if (!id) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Payment method ID is required',
        });
        return;
      }

      const paymentMethod = await deps.paymentMethodRepository.findById(id);

      if (!paymentMethod) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Payment method ${id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this payment method

      res.json(formatPaymentMethodResponse(paymentMethod));

    } catch (error) {
      next(error);
    }
  });

  /**
   * PATCH /payment-methods/:id - Update payment method
   */
  router.patch('/:id', requireScope('payment-methods:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params['id'];

      if (!id) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Payment method ID is required',
        });
        return;
      }

      const validation = UpdatePaymentMethodSchema.safeParse(req.body);
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

      const paymentMethod = await deps.paymentMethodRepository.findById(id);

      if (!paymentMethod) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Payment method ${id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this payment method

      const data = validation.data;

      if (data.display_name) {
        paymentMethod.updateDisplayName(data.display_name);
      }

      if (data.set_as_default === true) {
        await deps.paymentMethodRepository.clearDefaultForAccount(
          paymentMethod.accountId as string
        );
        paymentMethod.setDefault(true);
      } else if (data.set_as_default === false) {
        paymentMethod.setDefault(false);
      }

      await deps.paymentMethodRepository.update(paymentMethod);

      res.json(formatPaymentMethodResponse(paymentMethod));

    } catch (error) {
      next(error);
    }
  });

  /**
   * DELETE /payment-methods/:id - Remove payment method
   */
  router.delete('/:id', requireScope('payment-methods:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params['id'];

      if (!id) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Payment method ID is required',
        });
        return;
      }

      const paymentMethod = await deps.paymentMethodRepository.findById(id);

      if (!paymentMethod) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Payment method ${id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this payment method

      // Detach from provider
      try {
        const provider = deps.providerFactory.getProvider(paymentMethod.providerCode);
        await provider.deletePaymentMethod(paymentMethod.externalId);
      } catch (error) {
        // Log but don't fail - the payment method might already be detached
        console.warn(
          `Failed to detach payment method from provider: ${error instanceof Error ? error.message : 'Unknown error'}`
        );
      }

      // Soft delete
      await deps.paymentMethodRepository.delete(id);

      res.status(204).send();

    } catch (error) {
      next(error);
    }
  });

  /**
   * POST /payment-methods/:id/verify - Verify a payment method
   */
  router.post('/:id/verify', requireScope('payment-methods:write'), async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params['id'];

      if (!id) {
        res.status(400).json({
          type: 'https://api.ledger.example.com/problems/bad-request',
          title: 'Bad Request',
          status: 400,
          detail: 'Payment method ID is required',
        });
        return;
      }

      const validation = VerifyPaymentMethodSchema.safeParse(req.body);
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

      const paymentMethod = await deps.paymentMethodRepository.findById(id);

      if (!paymentMethod) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `Payment method ${id} not found`,
        });
        return;
      }

      // TODO: Verify user has access to this payment method

      if (paymentMethod.status === 'verified') {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/already-verified',
          title: 'Already Verified',
          status: 422,
          detail: 'Payment method is already verified',
        });
        return;
      }

      // Verify with provider
      const provider = deps.providerFactory.getProvider(paymentMethod.providerCode);
      const result = await provider.verifyPaymentMethod(
        paymentMethod.externalId,
        validation.data.verification_data
      );

      if (!result.verified) {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/verification-failed',
          title: 'Verification Failed',
          status: 422,
          detail: result.errorMessage ?? 'Verification failed',
        });
        return;
      }

      paymentMethod.verify();
      await deps.paymentMethodRepository.update(paymentMethod);

      res.json(formatPaymentMethodResponse(paymentMethod));

    } catch (error) {
      handlePaymentMethodError(error, res, next);
    }
  });

  return router;
}

function formatPaymentMethodResponse(paymentMethod: PaymentMethod) {
  const data = paymentMethod.toJSON();

  return {
    id: data['id'],
    account_id: data['accountId'],
    provider_code: data['providerCode'],
    type: data['type'],
    status: data['status'],
    display_name: data['displayName'],
    is_default: data['isDefault'],
    is_withdrawable: data['isWithdrawable'],
    expires_at: data['expiresAt'],
    created_at: data['createdAt'],
    updated_at: data['updatedAt'],
    // Never expose external_id or metadata to the client
  };
}

function handlePaymentMethodError(
  error: unknown,
  res: Response,
  next: NextFunction
): void {
  if (error instanceof Error) {
    if (error.name === 'ProviderError' || error.message.includes('Stripe')) {
      res.status(502).json({
        type: 'https://api.ledger.example.com/problems/provider-error',
        title: 'Payment Provider Error',
        status: 502,
        detail: 'Failed to communicate with payment provider',
      });
      return;
    }
  }

  next(error);
}
