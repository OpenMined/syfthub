/**
 * Authentication Middleware
 *
 * Validates JWT tokens and API tokens, extracting user context.
 * Supports dual auth: JWT for interactive sessions, API tokens for programmatic access.
 */

import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { UserId } from '../../../domain/value-objects/Identifiers';
import { ApiTokenService } from '../../../application/ports/input/ApiTokenService';

export interface JwtPayload {
  sub: string;        // User ID
  scope: string[];    // Permissions
  exp: number;
  iat: number;
  jti: string;
}

export interface AuthenticatedRequest extends Request {
  user: {
    id: UserId;
    scope: string[];
    isApiToken?: boolean;
    tokenPrefix?: string;
  };
}

export interface AuthConfig {
  jwtSecret: string;
  issuer?: string;
  audience?: string;
  apiTokenService?: ApiTokenService;
}

export function createAuthMiddleware(config: AuthConfig) {
  return async function authMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
  ): Promise<void> {
    const authHeader = req.headers.authorization;

    if (!authHeader) {
      res.status(401).json({
        type: 'https://api.ledger.example.com/problems/unauthorized',
        title: 'Unauthorized',
        status: 401,
        detail: 'Missing Authorization header',
      });
      return;
    }

    const parts = authHeader.split(' ');
    if (parts.length !== 2 || parts[0] !== 'Bearer') {
      res.status(401).json({
        type: 'https://api.ledger.example.com/problems/unauthorized',
        title: 'Unauthorized',
        status: 401,
        detail: 'Invalid Authorization header format. Expected: Bearer <token>',
      });
      return;
    }

    const token = parts[1]!;

    // Check if this is an API token (starts with 'at_')
    if (token.startsWith('at_')) {
      // API token authentication
      if (!config.apiTokenService) {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/invalid-token',
          title: 'Invalid Token',
          status: 401,
          detail: 'API token authentication is not configured',
        });
        return;
      }

      try {
        const clientIp = getClientIp(req);
        const apiToken = await config.apiTokenService.validateToken(token, clientIp);

        if (!apiToken) {
          res.status(401).json({
            type: 'https://api.ledger.example.com/problems/invalid-token',
            title: 'Invalid Token',
            status: 401,
            detail: 'The API token is invalid, expired, or revoked',
          });
          return;
        }

        // Attach user to request with API token info
        (req as AuthenticatedRequest).user = {
          id: apiToken.userId,
          scope: apiToken.scopes,
          isApiToken: true,
          tokenPrefix: apiToken.prefix,
        };

        next();
        return;
      } catch (error) {
        next(error);
        return;
      }
    }

    // JWT authentication
    try {
      const payload = jwt.verify(token, config.jwtSecret, {
        issuer: config.issuer,
        audience: config.audience,
      }) as JwtPayload;

      // Attach user to request
      (req as AuthenticatedRequest).user = {
        id: UserId.from(payload.sub),
        scope: payload.scope,
        isApiToken: false,
      };

      next();
    } catch (error) {
      if (error instanceof jwt.TokenExpiredError) {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/token-expired',
          title: 'Token Expired',
          status: 401,
          detail: 'The access token has expired',
        });
        return;
      }

      if (error instanceof jwt.JsonWebTokenError) {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/invalid-token',
          title: 'Invalid Token',
          status: 401,
          detail: 'The access token is invalid',
        });
        return;
      }

      next(error);
    }
  };
}

/**
 * Extract client IP from request.
 *
 * IMPORTANT: This function relies on Express's `trust proxy` setting being
 * configured correctly in server.ts. When `trust proxy` is set, Express
 * automatically parses X-Forwarded-For headers from trusted proxies and
 * sets `req.ip` to the correct client IP.
 *
 * Without proper `trust proxy` configuration, X-Forwarded-For headers can
 * be spoofed by malicious clients, leading to:
 * - Rate limit bypass
 * - Audit log manipulation
 * - IP-based access control bypass
 *
 * @see https://expressjs.com/en/guide/behind-proxies.html
 */
function getClientIp(req: Request): string {
  // req.ip is automatically set correctly when 'trust proxy' is configured
  // Express handles X-Forwarded-For parsing based on the trust proxy setting
  if (req.ip) {
    return req.ip;
  }

  // Fallback for edge cases (should rarely be needed)
  return req.socket?.remoteAddress ?? 'unknown';
}

/**
 * Middleware to check for specific scopes
 * JWT users: full access (existing behavior for interactive sessions)
 * API token users: verify token has required scopes
 */
export function requireScope(...requiredScopes: string[]) {
  return function scopeMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
  ): void {
    const authReq = req as AuthenticatedRequest;

    if (!authReq.user) {
      res.status(401).json({
        type: 'https://api.ledger.example.com/problems/unauthorized',
        title: 'Unauthorized',
        status: 401,
        detail: 'Authentication required',
      });
      return;
    }

    // JWT users have full access
    if (!authReq.user.isApiToken) {
      next();
      return;
    }

    // API token users need the required scopes
    const hasScope = requiredScopes.every((scope) =>
      authReq.user.scope.includes(scope)
    );

    if (!hasScope) {
      res.status(403).json({
        type: 'https://api.ledger.example.com/problems/forbidden',
        title: 'Forbidden',
        status: 403,
        detail: `Missing required scope(s): ${requiredScopes.join(', ')}`,
        required_scopes: requiredScopes,
        token_scopes: authReq.user.scope,
      });
      return;
    }

    next();
  };
}
