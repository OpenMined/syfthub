/**
 * Xendit Controller
 *
 * HTTP handlers for Xendit-specific operations:
 * - Invoice creation and management
 * - Virtual account management
 * - Payment channel listing
 * - Payment status checking
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { PaymentProviderFactory } from '../../payment-providers/PaymentProviderFactory';
import { XenditChannelCode, XenditCountry, XenditCurrency } from '../../payment-providers/xendit';

// Request validation schemas
const CreateInvoiceSchema = z.object({
  external_id: z.string().min(1).max(255),
  amount: z.number().int().positive(),
  currency: z.enum(['IDR', 'PHP', 'VND', 'THB', 'MYR', 'USD']).optional(),
  payer_email: z.string().email().optional(),
  description: z.string().max(255).optional(),
  duration_seconds: z.number().int().min(60).max(31536000).optional(), // 1 min to 1 year
  payment_methods: z.array(z.string()).optional(),
  metadata: z.record(z.string()).optional(),
});

const CreateVirtualAccountSchema = z.object({
  external_id: z.string().min(1).max(255),
  bank_code: z.string().min(1),
  name: z.string().min(1).max(100),
  expected_amount: z.number().int().positive().optional(),
  expiration_date: z.string().datetime().optional(),
  is_closed: z.boolean().optional(),
  is_single_use: z.boolean().optional(),
});

const ListChannelsSchema = z.object({
  country: z.enum(['ID', 'PH', 'VN', 'TH', 'MY']).optional(),
});

export function createXenditController(
  providerFactory: PaymentProviderFactory
): Router {
  const router = Router();

  /**
   * Middleware to ensure Xendit is available
   */
  const ensureXenditAvailable = (
    _req: Request,
    res: Response,
    next: NextFunction
  ): void => {
    if (!providerFactory.hasProvider('xendit')) {
      res.status(503).json({
        type: 'https://api.ledger.example.com/problems/provider-unavailable',
        title: 'Xendit Provider Unavailable',
        status: 503,
        detail: 'Xendit payment provider is not configured',
      });
      return;
    }
    next();
  };

  router.use(ensureXenditAvailable);

  /**
   * POST /xendit/invoices - Create a payment invoice (payment link)
   */
  router.post(
    '/invoices',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = CreateInvoiceSchema.safeParse(req.body);
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

        const xenditAdapter = providerFactory.getXenditAdapter();
        const invoice = await xenditAdapter.createInvoice({
          externalId: data.external_id,
          amount: data.amount,
          currency: data.currency,
          payerEmail: data.payer_email,
          description: data.description,
          durationSeconds: data.duration_seconds,
          paymentMethods: data.payment_methods,
          metadata: data.metadata,
        });

        res.status(201)
          .header('Location', `/v1/xendit/invoices/${invoice.id}`)
          .json({
            id: invoice.id,
            external_id: invoice.external_id,
            status: invoice.status,
            amount: invoice.amount,
            currency: invoice.currency,
            invoice_url: invoice.invoice_url,
            description: invoice.description ?? null,
            payer_email: invoice.payer_email ?? null,
            available_banks: invoice.available_banks?.map((b) => ({
              bank_code: b.bank_code,
              collection_type: b.collection_type,
              account_holder_name: b.account_holder_name,
            })) ?? [],
            available_ewallets: invoice.available_ewallets?.map((e) => ({
              ewallet_type: e.ewallet_type,
            })) ?? [],
            success_redirect_url: invoice.success_redirect_url ?? null,
            failure_redirect_url: invoice.failure_redirect_url ?? null,
            created: invoice.created,
            updated: invoice.updated,
          });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * GET /xendit/invoices/:id - Get invoice by ID
   */
  router.get(
    '/invoices/:id',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { id } = req.params;

        const xenditAdapter = providerFactory.getXenditAdapter();
        const invoice = await xenditAdapter.getInvoice(id!);

        if (!invoice) {
          res.status(404).json({
            type: 'https://api.ledger.example.com/problems/not-found',
            title: 'Not Found',
            status: 404,
            detail: `Invoice with ID ${id} not found`,
          });
          return;
        }

        res.json({
          id: invoice.id,
          external_id: invoice.external_id,
          status: invoice.status,
          amount: invoice.amount,
          currency: invoice.currency,
          invoice_url: invoice.invoice_url,
          description: invoice.description ?? null,
          payer_email: invoice.payer_email ?? null,
          paid_at: invoice.status === 'PAID' ? invoice.updated : null,
          fees_paid_amount: invoice.fees_paid_amount ?? null,
          adjusted_received_amount: invoice.adjusted_received_amount ?? null,
          created: invoice.created,
          updated: invoice.updated,
        });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * POST /xendit/invoices/:id/expire - Expire an invoice
   */
  router.post(
    '/invoices/:id/expire',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { id } = req.params;

        const xenditAdapter = providerFactory.getXenditAdapter();
        const invoice = await xenditAdapter.expireInvoice(id!);

        res.json({
          id: invoice.id,
          external_id: invoice.external_id,
          status: invoice.status,
          message: 'Invoice expired successfully',
        });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * POST /xendit/virtual-accounts - Create a virtual account
   */
  router.post(
    '/virtual-accounts',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = CreateVirtualAccountSchema.safeParse(req.body);
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

        const xenditAdapter = providerFactory.getXenditAdapter();
        const va = await xenditAdapter.createVirtualAccount({
          externalId: data.external_id,
          bankCode: data.bank_code,
          name: data.name,
          expectedAmount: data.expected_amount,
          expirationDate: data.expiration_date ? new Date(data.expiration_date) : undefined,
          isClosed: data.is_closed,
          isSingleUse: data.is_single_use,
        });

        res.status(201)
          .header('Location', `/v1/xendit/virtual-accounts/${va.id}`)
          .json({
            id: va.id,
            external_id: va.external_id,
            owner_id: va.owner_id,
            bank_code: va.bank_code,
            merchant_code: va.merchant_code,
            name: va.name,
            account_number: va.account_number,
            is_closed: va.is_closed,
            is_single_use: va.is_single_use,
            expected_amount: va.expected_amount ?? null,
            suggested_amount: va.suggested_amount ?? null,
            expiration_date: va.expiration_date,
            status: va.status,
            currency: va.currency,
            country: va.country,
          });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * GET /xendit/virtual-accounts/:id - Get virtual account by ID
   */
  router.get(
    '/virtual-accounts/:id',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { id } = req.params;

        const xenditAdapter = providerFactory.getXenditAdapter();
        const va = await xenditAdapter.getVirtualAccount(id!);

        if (!va) {
          res.status(404).json({
            type: 'https://api.ledger.example.com/problems/not-found',
            title: 'Not Found',
            status: 404,
            detail: `Virtual account with ID ${id} not found`,
          });
          return;
        }

        res.json({
          id: va.id,
          external_id: va.external_id,
          owner_id: va.owner_id,
          bank_code: va.bank_code,
          merchant_code: va.merchant_code,
          name: va.name,
          account_number: va.account_number,
          is_closed: va.is_closed,
          is_single_use: va.is_single_use,
          expected_amount: va.expected_amount ?? null,
          suggested_amount: va.suggested_amount ?? null,
          expiration_date: va.expiration_date,
          status: va.status,
          currency: va.currency,
          country: va.country,
        });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * GET /xendit/channels - List available payment channels
   */
  router.get(
    '/channels',
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        const validation = ListChannelsSchema.safeParse(req.query);
        if (!validation.success) {
          res.status(422).json({
            type: 'https://api.ledger.example.com/problems/validation-error',
            title: 'Validation Error',
            status: 422,
            detail: 'Query parameter validation failed',
            errors: validation.error.errors.map((e) => ({
              field: e.path.join('.'),
              message: e.message,
            })),
          });
          return;
        }

        const { country } = validation.data;

        const xenditAdapter = providerFactory.getXenditAdapter();
        const channels = await xenditAdapter.getAvailableChannels(country);

        // Group channels by type
        const channelsByType: Record<string, XenditChannelCode[]> = {
          cards: [],
          virtual_accounts: [],
          ewallets: [],
          qr_codes: [],
          retail_outlets: [],
          direct_debit: [],
        };

        for (const channel of channels) {
          if (channel === 'CARDS') {
            channelsByType['cards']!.push(channel);
          } else if (channel.includes('VIRTUAL_ACCOUNT')) {
            channelsByType['virtual_accounts']!.push(channel);
          } else if (channel === 'QRIS' || channel === 'PROMPTPAY') {
            channelsByType['qr_codes']!.push(channel);
          } else if (channel === 'ALFAMART' || channel === 'INDOMARET' || channel === '7ELEVEN' || channel === 'CEBUANA' || channel === 'ECPAY') {
            channelsByType['retail_outlets']!.push(channel);
          } else if (channel.includes('DIRECT_DEBIT')) {
            channelsByType['direct_debit']!.push(channel);
          } else {
            channelsByType['ewallets']!.push(channel);
          }
        }

        res.json({
          country: country ?? xenditAdapter.defaultCountry,
          currency: getCurrencyForCountry(country as XenditCountry ?? xenditAdapter.defaultCountry),
          channels: channelsByType,
          all_channels: channels,
        });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  /**
   * GET /xendit/config - Get current Xendit configuration info
   */
  router.get(
    '/config',
    async (_req: Request, res: Response, next: NextFunction) => {
      try {
        const xenditAdapter = providerFactory.getXenditAdapter();

        res.json({
          default_country: xenditAdapter.defaultCountry,
          default_currency: xenditAdapter.defaultCurrency,
          success_redirect_url: xenditAdapter.successRedirectUrl ?? null,
          failure_redirect_url: xenditAdapter.failureRedirectUrl ?? null,
          supported_countries: ['ID', 'PH', 'VN', 'TH', 'MY'],
          supported_currencies: ['IDR', 'PHP', 'VND', 'THB', 'MYR', 'USD'],
        });
      } catch (error) {
        handleXenditError(error, res, next);
      }
    }
  );

  return router;
}

/**
 * Get currency for country
 */
function getCurrencyForCountry(country: XenditCountry): XenditCurrency {
  const currencyMap: Record<XenditCountry, XenditCurrency> = {
    ID: 'IDR',
    PH: 'PHP',
    VN: 'VND',
    TH: 'THB',
    MY: 'MYR',
  };
  return currencyMap[country];
}

/**
 * Handle Xendit-specific errors
 */
function handleXenditError(
  error: unknown,
  res: Response,
  next: NextFunction
): void {
  if (error instanceof Error) {
    // Handle Xendit API errors
    if (error.name === 'XenditApiError') {
      const xenditError = error as unknown as { code: string; message: string; httpStatus: number };

      // Map common Xendit error codes
      if (xenditError.code === 'CHANNEL_NOT_ACTIVATED') {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/channel-not-activated',
          title: 'Channel Not Activated',
          status: 422,
          detail: 'The requested payment channel is not activated for your account',
          error_code: xenditError.code,
        });
        return;
      }

      if (xenditError.code === 'INSUFFICIENT_BALANCE') {
        res.status(422).json({
          type: 'https://api.ledger.example.com/problems/insufficient-balance',
          title: 'Insufficient Balance',
          status: 422,
          detail: 'Insufficient balance to complete the operation',
          error_code: xenditError.code,
        });
        return;
      }

      if (xenditError.code === 'DUPLICATE_PAYMENT_REQUEST_ERROR') {
        res.status(409).json({
          type: 'https://api.ledger.example.com/problems/duplicate-request',
          title: 'Duplicate Request',
          status: 409,
          detail: 'A payment request with this reference ID already exists',
          error_code: xenditError.code,
        });
        return;
      }

      if (xenditError.code === 'INVALID_API_KEY') {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/authentication-error',
          title: 'Authentication Error',
          status: 401,
          detail: 'Invalid Xendit API key',
          error_code: xenditError.code,
        });
        return;
      }

      if (xenditError.code === 'REQUEST_FORBIDDEN_ERROR') {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have permission to perform this action',
          error_code: xenditError.code,
        });
        return;
      }

      // Generic Xendit error
      res.status(xenditError.httpStatus || 500).json({
        type: 'https://api.ledger.example.com/problems/xendit-error',
        title: 'Xendit Error',
        status: xenditError.httpStatus || 500,
        detail: xenditError.message,
        error_code: xenditError.code,
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
