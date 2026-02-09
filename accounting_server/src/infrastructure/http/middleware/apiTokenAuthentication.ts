/**
 * API Token Authentication Middleware
 *
 * Validates API tokens and extracts user context with scopes.
 */

import { Request, Response, NextFunction } from 'express';
import { TokenScope } from '../../../domain/entities/ApiToken';
import { UserId } from '../../../domain/value-objects/Identifiers';
import { ApiTokenService } from '../../../application/ports/input/ApiTokenService';

export interface ApiTokenAuthenticatedRequest extends Request {
  user: {
    id: UserId;
    scope: string[];
    isApiToken: true;
    tokenPrefix: string;
  };
}

export interface ApiTokenAuthConfig {
  apiTokenService: ApiTokenService;
}

/**
 * Create middleware that authenticates API tokens
 */
export function createApiTokenAuthMiddleware(config: ApiTokenAuthConfig) {
  return async function apiTokenAuthMiddleware(
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

    const tokenString = parts[1]!;

    // Check if this is an API token (starts with 'at_')
    if (!tokenString.startsWith('at_')) {
      res.status(401).json({
        type: 'https://api.ledger.example.com/problems/invalid-token',
        title: 'Invalid Token',
        status: 401,
        detail: 'Invalid API token format',
      });
      return;
    }

    try {
      // Get client IP for usage tracking
      const clientIp = getClientIp(req);

      // Validate the token
      const apiToken = await config.apiTokenService.validateToken(tokenString, clientIp);

      if (!apiToken) {
        res.status(401).json({
          type: 'https://api.ledger.example.com/problems/invalid-token',
          title: 'Invalid Token',
          status: 401,
          detail: 'The API token is invalid, expired, or revoked',
        });
        return;
      }

      // Attach user to request
      (req as ApiTokenAuthenticatedRequest).user = {
        id: apiToken.userId,
        scope: apiToken.scopes,
        isApiToken: true,
        tokenPrefix: apiToken.prefix,
      };

      next();
    } catch (error) {
      next(error);
    }
  };
}

/**
 * Middleware to check for specific scopes (for API token authenticated requests)
 */
export function requireTokenScope(...requiredScopes: TokenScope[]) {
  return function tokenScopeMiddleware(
    req: Request,
    res: Response,
    next: NextFunction
  ): void {
    const authReq = req as ApiTokenAuthenticatedRequest;

    if (!authReq.user) {
      res.status(401).json({
        type: 'https://api.ledger.example.com/problems/unauthorized',
        title: 'Unauthorized',
        status: 401,
        detail: 'Authentication required',
      });
      return;
    }

    // JWT users have full access (isApiToken will be undefined for JWT auth)
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

/**
 * Extract client IP from request, handling proxies
 */
function getClientIp(req: Request): string {
  // Check for forwarded header (behind proxy/load balancer)
  const forwarded = req.headers['x-forwarded-for'];
  if (forwarded) {
    const ips = Array.isArray(forwarded) ? forwarded[0] : forwarded.split(',')[0];
    return ips?.trim() ?? req.ip ?? 'unknown';
  }

  // Check for real IP header (nginx)
  const realIp = req.headers['x-real-ip'];
  if (realIp) {
    return Array.isArray(realIp) ? realIp[0] ?? 'unknown' : realIp;
  }

  return req.ip ?? 'unknown';
}
