/**
 * API Token Controller
 *
 * HTTP handlers for API token management operations.
 * All endpoints require JWT authentication (not API token auth).
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { ApiToken, ALL_TOKEN_SCOPES, TokenScope } from '../../../domain/entities/ApiToken';
import { ApiTokenService } from '../../../application/ports/input/ApiTokenService';
import { ApiTokenId } from '../../../domain/value-objects/Identifiers';
import { AuthenticatedRequest } from '../middleware/authentication';
import { TokenNotFoundError } from '../../../domain/errors';
import {
  TooManyTokensError,
  TokenAuthorizationError,
} from '../../../application/use-cases/ManageApiTokens';

// Request validation schemas
const CreateTokenSchema = z.object({
  name: z.string().min(1).max(100),
  scopes: z
    .array(z.enum(ALL_TOKEN_SCOPES as [TokenScope, ...TokenScope[]]))
    .min(1)
    .max(10),
  expires_in_days: z.number().int().positive().max(365).optional(),
});

const UpdateTokenSchema = z.object({
  name: z.string().min(1).max(100),
});

const RevokeTokenSchema = z.object({
  reason: z.string().max(500).optional(),
});

export function createApiTokenController(
  apiTokenService: ApiTokenService
): Router {
  const router = Router();

  /**
   * POST /api-tokens - Create a new API token
   * Returns the full token only once (never again)
   */
  router.post('/', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // API tokens cannot create other tokens - JWT auth only
      if (authReq.user.isApiToken) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'API tokens cannot be used to create other API tokens. Use JWT authentication.',
        });
        return;
      }

      // Validate request body
      const validation = CreateTokenSchema.safeParse(req.body);
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

      // Create token
      const createCommand: Parameters<typeof apiTokenService.createToken>[0] = {
        userId: authReq.user.id,
        name: data.name,
        scopes: data.scopes,
      };
      if (data.expires_in_days !== undefined) {
        createCommand.expiresInDays = data.expires_in_days;
      }
      const result = await apiTokenService.createToken(createCommand);

      res.status(201)
        .header('Location', `/v1/api-tokens/${result.apiToken.id}`)
        .json({
          id: result.apiToken.id,
          token: result.token, // Full token - shown only once!
          prefix: result.apiToken.prefix,
          name: result.apiToken.name,
          scopes: result.apiToken.scopes,
          created_at: result.apiToken.createdAt.toISOString(),
          expires_at: result.apiToken.expiresAt?.toISOString() ?? null,
          warning: 'Store this token securely. It will not be shown again.',
        });

    } catch (error) {
      if (error instanceof TooManyTokensError) {
        res.status(429).json({
          type: 'https://api.ledger.example.com/problems/too-many-tokens',
          title: 'Too Many Tokens',
          status: 429,
          detail: error.message,
        });
        return;
      }
      next(error);
    }
  });

  /**
   * GET /api-tokens - List user's tokens
   */
  router.get('/', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // API tokens cannot list tokens - JWT auth only
      if (authReq.user.isApiToken) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'API tokens cannot be used to manage other API tokens. Use JWT authentication.',
        });
        return;
      }

      const tokens = await apiTokenService.listTokens(authReq.user.id);

      res.json({
        data: tokens.map(formatTokenResponse),
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
   * GET /api-tokens/:id - Get token details
   */
  router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // API tokens cannot view token details - JWT auth only
      if (authReq.user.isApiToken) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'API tokens cannot be used to manage other API tokens. Use JWT authentication.',
        });
        return;
      }

      const tokenIdParam = req.params['id']!;
      const tokenId = ApiTokenId.from(tokenIdParam);

      const token = await apiTokenService.getToken(tokenId, authReq.user.id);

      if (!token) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: `API token ${tokenIdParam} not found`,
        });
        return;
      }

      res.json(formatTokenResponse(token));

    } catch (error) {
      if (error instanceof TokenAuthorizationError) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this token',
        });
        return;
      }
      next(error);
    }
  });

  /**
   * PATCH /api-tokens/:id - Update token name
   */
  router.patch('/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // API tokens cannot update tokens - JWT auth only
      if (authReq.user.isApiToken) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'API tokens cannot be used to manage other API tokens. Use JWT authentication.',
        });
        return;
      }

      // Validate request body
      const validation = UpdateTokenSchema.safeParse(req.body);
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

      const tokenId = ApiTokenId.from(req.params['id']!);

      const token = await apiTokenService.updateToken({
        tokenId,
        userId: authReq.user.id,
        name: validation.data.name,
      });

      res.json(formatTokenResponse(token));

    } catch (error) {
      if (error instanceof TokenNotFoundError) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: error.message,
        });
        return;
      }
      if (error instanceof TokenAuthorizationError) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this token',
        });
        return;
      }
      next(error);
    }
  });

  /**
   * DELETE /api-tokens/:id - Revoke token
   */
  router.delete('/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const authReq = req as AuthenticatedRequest;

      // API tokens cannot revoke tokens - JWT auth only
      if (authReq.user.isApiToken) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'API tokens cannot be used to manage other API tokens. Use JWT authentication.',
        });
        return;
      }

      // Validate request body (optional)
      const validation = RevokeTokenSchema.safeParse(req.body ?? {});
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

      const tokenId = ApiTokenId.from(req.params['id']!);

      const revokeCommand: Parameters<typeof apiTokenService.revokeToken>[0] = {
        tokenId,
        userId: authReq.user.id,
      };
      if (validation.data.reason !== undefined) {
        revokeCommand.reason = validation.data.reason;
      }
      const token = await apiTokenService.revokeToken(revokeCommand);

      res.json({
        ...formatTokenResponse(token),
        revoked_at: token.revokedAt?.toISOString() ?? null,
        revoked_reason: token.revokedReason ?? null,
      });

    } catch (error) {
      if (error instanceof TokenNotFoundError) {
        res.status(404).json({
          type: 'https://api.ledger.example.com/problems/not-found',
          title: 'Not Found',
          status: 404,
          detail: error.message,
        });
        return;
      }
      if (error instanceof TokenAuthorizationError) {
        res.status(403).json({
          type: 'https://api.ledger.example.com/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'You do not have access to this token',
        });
        return;
      }
      next(error);
    }
  });

  return router;
}

function formatTokenResponse(token: ApiToken) {
  return {
    id: token.id,
    prefix: token.prefix,
    name: token.name,
    scopes: token.scopes,
    created_at: token.createdAt.toISOString(),
    expires_at: token.expiresAt?.toISOString() ?? null,
    last_used_at: token.lastUsedAt?.toISOString() ?? null,
  };
}
