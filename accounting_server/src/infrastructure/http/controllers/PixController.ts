/**
 * PIX Controller
 *
 * HTTP handlers for Brazilian PIX-specific operations:
 * - QR code generation (static and dynamic)
 * - PIX key lookup (DICT)
 * - PIX charge management
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { PaymentProviderFactory } from '../../payment-providers/PaymentProviderFactory';
import {
  PixKeyType,
  isValidPixKey,
} from '../../payment-providers/pix/PixTypes';

// Request validation schemas
const LookupPixKeySchema = z.object({
  key_type: z.enum(['cpf', 'cnpj', 'email', 'phone', 'evp']),
  key_value: z.string().min(1),
});

const CreateStaticQrCodeSchema = z.object({
  amount: z.number().int().positive().optional(),
  description: z.string().max(140).optional(),
});

const CreateDynamicQrCodeSchema = z.object({
  amount: z.number().int().positive(),
  expires_in_seconds: z.number().int().min(60).max(86400),
  description: z.string().max(140).optional(),
  payer_document: z.string().optional(),
  payer_name: z.string().optional(),
  metadata: z.record(z.string()).optional(),
});

const CreateChargeSchema = z.object({
  amount: z.number().int().positive(),
  expires_in_seconds: z.number().int().min(60).max(86400),
  description: z.string().max(140).optional(),
  payer_document: z.string().optional(),
  payer_name: z.string().optional(),
  metadata: z.record(z.string()).optional(),
});

export function createPixController(
  providerFactory: PaymentProviderFactory
): Router {
  const router = Router();

  /**
   * Middleware to ensure PIX is available
   */
  const ensurePixAvailable = (
    _req: Request,
    res: Response,
    next: NextFunction
  ): void => {
    if (!providerFactory.hasProvider('pix')) {
      res.status(503).json({
        type: 'https://api.ledger.example.com/problems/provider-unavailable',
        title: 'PIX Provider Unavailable',
        status: 503,
        detail: 'PIX payment provider is not configured',
      });
      return;
    }
    next();
  };

  router.use(ensurePixAvailable);

  /**
   * POST /pix/keys/lookup - Look up PIX key in DICT
   */
  router.post(
    '/keys/lookup',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = LookupPixKeySchema.safeParse(req.body);
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

        const { key_type, key_value } = validation.data;

        // Validate PIX key format
        if (!isValidPixKey(key_type as PixKeyType, key_value)) {
          res.status(422).json({
            type: 'https://api.ledger.example.com/problems/invalid-pix-key',
            title: 'Invalid PIX Key',
            status: 422,
            detail: `Invalid ${key_type.toUpperCase()} format`,
          });
          return;
        }

        const pixAdapter = providerFactory.getPixAdapter();
        const result = await pixAdapter.lookupPixKey(
          key_type as PixKeyType,
          key_value
        );

        if (!result) {
          res.status(404).json({
            type: 'https://api.ledger.example.com/problems/pix-key-not-found',
            title: 'PIX Key Not Found',
            status: 404,
            detail: 'The specified PIX key was not found in DICT',
          });
          return;
        }

        res.json({
          key: {
            type: result.key.type,
            value: result.key.value,
          },
          holder: {
            name: result.holderName,
            document_type: result.holderDocumentType,
            document: result.holderDocument,
          },
          bank: {
            ispb: result.bankIspb,
            name: result.bankName,
          },
          account: {
            agency: result.agency,
            number: result.accountNumber,
            type: result.accountType,
          },
          created_at: result.createdAt.toISOString(),
          verified_at: result.verifiedAt?.toISOString() ?? null,
        });
      } catch (error) {
        handlePixError(error, res, next);
      }
    }
  );

  /**
   * POST /pix/qr-codes/static - Generate static QR code
   */
  router.post(
    '/qr-codes/static',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = CreateStaticQrCodeSchema.safeParse(req.body);
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

        const { amount, description } = validation.data;

        const pixAdapter = providerFactory.getPixAdapter();
        const qrCode = await pixAdapter.createStaticQrCode(amount, description);

        res.status(201).json({
          id: qrCode.id,
          type: qrCode.type,
          payload: qrCode.payload,
          qr_code_base64: qrCode.qrCodeBase64 ?? null,
          qr_code_url: qrCode.qrCodeUrl ?? null,
          pix_key: qrCode.pixKey,
          merchant_name: qrCode.merchantName,
          merchant_city: qrCode.merchantCity,
          amount: qrCode.amount ?? null,
          description: qrCode.description ?? null,
          created_at: qrCode.createdAt.toISOString(),
        });
      } catch (error) {
        handlePixError(error, res, next);
      }
    }
  );

  /**
   * POST /pix/qr-codes/dynamic - Generate dynamic QR code (cobranca imediata)
   */
  router.post(
    '/qr-codes/dynamic',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = CreateDynamicQrCodeSchema.safeParse(req.body);
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

        const pixAdapter = providerFactory.getPixAdapter();
        const qrCode = await pixAdapter.createDynamicQrCode({
          pixKey: pixAdapter.receiverPixKey,
          amount: data.amount,
          expiresInSeconds: data.expires_in_seconds,
          description: data.description,
          payerDocument: data.payer_document,
          payerName: data.payer_name,
          metadata: data.metadata,
        });

        res.status(201).json({
          id: qrCode.id,
          type: qrCode.type,
          txid: qrCode.txid,
          payload: qrCode.payload,
          qr_code_base64: qrCode.qrCodeBase64 ?? null,
          qr_code_url: qrCode.qrCodeUrl ?? null,
          pix_key: qrCode.pixKey,
          merchant_name: qrCode.merchantName,
          merchant_city: qrCode.merchantCity,
          amount: qrCode.amount,
          expires_at: qrCode.expiresAt?.toISOString() ?? null,
          description: qrCode.description ?? null,
          created_at: qrCode.createdAt.toISOString(),
        });
      } catch (error) {
        handlePixError(error, res, next);
      }
    }
  );

  /**
   * POST /pix/charges - Create a PIX charge (cobranca)
   */
  router.post(
    '/charges',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = CreateChargeSchema.safeParse(req.body);
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

        const pixAdapter = providerFactory.getPixAdapter();
        const charge = await pixAdapter.createCharge({
          amount: data.amount,
          expiresInSeconds: data.expires_in_seconds,
          description: data.description,
          payerDocument: data.payer_document,
          payerName: data.payer_name,
          metadata: data.metadata,
          idempotencyKey,
        });

        res.status(201)
          .header('Location', `/v1/pix/charges/${charge.id}`)
          .json({
            id: charge.id,
            txid: charge.txid,
            status: charge.status,
            pix_key: charge.pixKey,
            amount: charge.amount,
            description: charge.description ?? null,
            payer_document: charge.payerDocument ?? null,
            payer_name: charge.payerName ?? null,
            qr_code: {
              payload: charge.qrCode.payload,
              base64: charge.qrCode.qrCodeBase64 ?? null,
            },
            expires_at: charge.expiresAt.toISOString(),
            created_at: charge.createdAt.toISOString(),
          });
      } catch (error) {
        handlePixError(error, res, next);
      }
    }
  );

  /**
   * GET /pix/charges/:txid - Get charge status by txid
   */
  router.get(
    '/charges/:txid',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { txid } = req.params;

        const pixAdapter = providerFactory.getPixAdapter();
        const charge = await pixAdapter.getCharge(txid!);

        if (!charge) {
          res.status(404).json({
            type: 'https://api.ledger.example.com/problems/not-found',
            title: 'Not Found',
            status: 404,
            detail: `PIX charge with txid ${txid} not found`,
          });
          return;
        }

        res.json({
          id: charge.id,
          txid: charge.txid,
          status: charge.status,
          pix_key: charge.pixKey,
          amount: charge.amount,
          description: charge.description ?? null,
          payer_document: charge.payerDocument ?? null,
          payer_name: charge.payerName ?? null,
          qr_code: {
            payload: charge.qrCode.payload,
            base64: charge.qrCode.qrCodeBase64 ?? null,
          },
          end_to_end_id: charge.endToEndId ?? null,
          paid_at: charge.paidAt?.toISOString() ?? null,
          expires_at: charge.expiresAt.toISOString(),
          created_at: charge.createdAt.toISOString(),
        });
      } catch (error) {
        handlePixError(error, res, next);
      }
    }
  );

  /**
   * POST /pix/validate-key - Validate PIX key format (client-side validation)
   */
  router.post(
    '/validate-key',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = LookupPixKeySchema.safeParse(req.body);
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

        const { key_type, key_value } = validation.data;
        const isValid = isValidPixKey(key_type as PixKeyType, key_value);

        res.json({
          key_type,
          key_value,
          is_valid: isValid,
        });
      } catch (error) {
        next(error);
      }
    }
  );

  return router;
}

function handlePixError(
  error: unknown,
  res: Response,
  next: NextFunction
): void {
  if (error instanceof Error) {
    // Handle PIX-specific errors
    if (error.message.includes('INVALID_KEY')) {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/invalid-pix-key',
        title: 'Invalid PIX Key',
        status: 422,
        detail: error.message,
      });
      return;
    }

    if (error.message.includes('KEY_BLOCKED')) {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/pix-key-blocked',
        title: 'PIX Key Blocked',
        status: 422,
        detail: 'The PIX key is blocked and cannot be used',
      });
      return;
    }

    if (error.message.includes('DAILY_LIMIT_EXCEEDED')) {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/daily-limit-exceeded',
        title: 'Daily Limit Exceeded',
        status: 422,
        detail: 'Daily PIX transaction limit exceeded',
      });
      return;
    }

    if (error.message.includes('TRANSACTION_LIMIT_EXCEEDED')) {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/transaction-limit-exceeded',
        title: 'Transaction Limit Exceeded',
        status: 422,
        detail: 'Per-transaction PIX limit exceeded',
      });
      return;
    }

    if (error.message.includes('DUPLICATE_TRANSACTION')) {
      res.status(409).json({
        type: 'https://api.ledger.example.com/problems/duplicate-transaction',
        title: 'Duplicate Transaction',
        status: 409,
        detail: 'Transaction has already been processed',
      });
      return;
    }

    if (error.message.includes('FRAUD_SUSPECTED')) {
      res.status(422).json({
        type: 'https://api.ledger.example.com/problems/fraud-suspected',
        title: 'Fraud Suspected',
        status: 422,
        detail: 'Transaction flagged for potential fraud',
      });
      return;
    }

    if (error.name === 'UnsupportedProviderError') {
      res.status(503).json({
        type: 'https://api.ledger.example.com/problems/provider-unavailable',
        title: 'Provider Unavailable',
        status: 503,
        detail: error.message,
      });
      return;
    }
  }

  next(error);
}
