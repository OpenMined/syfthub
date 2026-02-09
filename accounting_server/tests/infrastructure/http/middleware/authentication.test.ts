/**
 * Authentication Middleware Unit Tests
 *
 * Tests JWT and API token authentication, scope enforcement.
 */

import express, { Express } from 'express';
import request from 'supertest';
import jwt from 'jsonwebtoken';
import {
  createAuthMiddleware,
  requireScope,
  AuthenticatedRequest,
} from '../../../../src/infrastructure/http/middleware/authentication';
import { ApiTokenService } from '../../../../src/application/ports/input/ApiTokenService';
import { ApiToken, TokenScope } from '../../../../src/domain/entities/ApiToken';
import { UserId } from '../../../../src/domain/value-objects/Identifiers';

describe('Authentication Middleware', () => {
  const jwtSecret = 'test-secret-key-for-jwt-signing';
  const testUserId = 'user-123';

  // Helper to create a valid JWT
  function createJwt(payload: Partial<{
    sub: string;
    scope: string[];
    exp: number;
    iat: number;
    jti: string;
  }> = {}): string {
    const now = Math.floor(Date.now() / 1000);
    return jwt.sign({
      sub: testUserId,
      scope: ['accounts:read', 'accounts:write'],
      exp: now + 3600,
      iat: now,
      jti: 'test-jwt-id',
      ...payload,
    }, jwtSecret);
  }

  // Helper to create a mock API token entity
  function createMockApiToken(overrides: Partial<{
    userId: UserId;
    scopes: TokenScope[];
    prefix: string;
  }> = {}): ApiToken {
    const { entity } = ApiToken.create({
      userId: overrides.userId ?? UserId.from(testUserId),
      name: 'Test Token',
      scopes: overrides.scopes ?? ['accounts:read'] as TokenScope[],
    });
    return entity;
  }

  describe('createAuthMiddleware', () => {
    let app: Express;
    let mockApiTokenService: jest.Mocked<ApiTokenService>;

    beforeEach(() => {
      mockApiTokenService = {
        createToken: jest.fn(),
        listTokens: jest.fn(),
        getToken: jest.fn(),
        updateToken: jest.fn(),
        revokeToken: jest.fn(),
        validateToken: jest.fn(),
      };

      app = express();
      app.use(express.json());
    });

    afterEach(() => {
      jest.clearAllMocks();
    });

    describe('Missing Authorization header', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({ jwtSecret });
        app.use(middleware);
        app.get('/test', (_req, res) => res.json({ ok: true }));
      });

      it('should return 401 when Authorization header is missing', async () => {
        const response = await request(app).get('/test');

        expect(response.status).toBe(401);
        expect(response.body.type).toContain('unauthorized');
        expect(response.body.detail).toContain('Missing Authorization header');
      });
    });

    describe('Invalid Authorization header format', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({ jwtSecret });
        app.use(middleware);
        app.get('/test', (_req, res) => res.json({ ok: true }));
      });

      it('should return 401 when Authorization header is not Bearer format', async () => {
        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Basic abc123');

        expect(response.status).toBe(401);
        expect(response.body.detail).toContain('Invalid Authorization header format');
      });

      it('should return 401 when Authorization header has no token', async () => {
        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer');

        expect(response.status).toBe(401);
      });

      it('should return 401 when Authorization header has too many parts', async () => {
        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer token extra');

        expect(response.status).toBe(401);
      });
    });

    describe('JWT Authentication', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({ jwtSecret });
        app.use(middleware);
        app.get('/test', (req, res) => {
          const authReq = req as AuthenticatedRequest;
          res.json({
            userId: authReq.user.id.toString(),
            scope: authReq.user.scope,
            isApiToken: authReq.user.isApiToken,
          });
        });
      });

      it('should authenticate valid JWT', async () => {
        const token = createJwt();

        const response = await request(app)
          .get('/test')
          .set('Authorization', `Bearer ${token}`);

        expect(response.status).toBe(200);
        expect(response.body.userId).toBe(testUserId);
        expect(response.body.scope).toEqual(['accounts:read', 'accounts:write']);
        expect(response.body.isApiToken).toBe(false);
      });

      it('should return 401 for expired JWT', async () => {
        const expiredToken = createJwt({
          exp: Math.floor(Date.now() / 1000) - 3600, // Expired 1 hour ago
        });

        const response = await request(app)
          .get('/test')
          .set('Authorization', `Bearer ${expiredToken}`);

        expect(response.status).toBe(401);
        expect(response.body.type).toContain('token-expired');
      });

      it('should return 401 for invalid JWT signature', async () => {
        const invalidToken = jwt.sign({ sub: testUserId }, 'wrong-secret');

        const response = await request(app)
          .get('/test')
          .set('Authorization', `Bearer ${invalidToken}`);

        expect(response.status).toBe(401);
        expect(response.body.type).toContain('invalid-token');
      });

      it('should return 401 for malformed JWT', async () => {
        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer not.a.valid.jwt');

        expect(response.status).toBe(401);
        expect(response.body.type).toContain('invalid-token');
      });
    });

    describe('JWT with issuer and audience', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({
          jwtSecret,
          issuer: 'https://auth.example.com',
          audience: 'ledger-api',
        });
        app.use(middleware);
        app.get('/test', (_req, res) => res.json({ ok: true }));
      });

      it('should reject JWT with wrong issuer', async () => {
        const token = jwt.sign({
          sub: testUserId,
          scope: [],
          iss: 'https://wrong-issuer.com',
        }, jwtSecret);

        const response = await request(app)
          .get('/test')
          .set('Authorization', `Bearer ${token}`);

        expect(response.status).toBe(401);
      });

      it('should reject JWT with wrong audience', async () => {
        const token = jwt.sign({
          sub: testUserId,
          scope: [],
          aud: 'wrong-audience',
        }, jwtSecret);

        const response = await request(app)
          .get('/test')
          .set('Authorization', `Bearer ${token}`);

        expect(response.status).toBe(401);
      });
    });

    describe('API Token Authentication', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({
          jwtSecret,
          apiTokenService: mockApiTokenService,
        });
        app.use(middleware);
        app.get('/test', (req, res) => {
          const authReq = req as AuthenticatedRequest;
          res.json({
            userId: authReq.user.id.toString(),
            scope: authReq.user.scope,
            isApiToken: authReq.user.isApiToken,
            tokenPrefix: authReq.user.tokenPrefix,
          });
        });
      });

      it('should authenticate valid API token', async () => {
        const mockToken = createMockApiToken({
          scopes: ['accounts:read', 'transactions:read'] as TokenScope[],
        });
        mockApiTokenService.validateToken.mockResolvedValue(mockToken);

        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_abc12345_secretpart');

        expect(response.status).toBe(200);
        expect(response.body.userId).toBe(testUserId);
        expect(response.body.scope).toEqual(['accounts:read', 'transactions:read']);
        expect(response.body.isApiToken).toBe(true);
        expect(response.body.tokenPrefix).toBeDefined();
        expect(mockApiTokenService.validateToken).toHaveBeenCalledWith(
          'at_abc12345_secretpart',
          expect.any(String)
        );
      });

      it('should return 401 for invalid API token', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_invalid_token');

        expect(response.status).toBe(401);
        expect(response.body.detail).toContain('invalid, expired, or revoked');
      });

      it('should return 401 for expired API token', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_expired_token');

        expect(response.status).toBe(401);
      });

      it('should return 401 for revoked API token', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_revoked_token');

        expect(response.status).toBe(401);
      });

      it('should pass client IP to validateToken', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_test_token')
          .set('X-Forwarded-For', '192.168.1.100');

        expect(mockApiTokenService.validateToken).toHaveBeenCalledWith(
          'at_test_token',
          '192.168.1.100'
        );
      });

      it('should handle X-Real-IP header', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_test_token')
          .set('X-Real-IP', '10.0.0.1');

        expect(mockApiTokenService.validateToken).toHaveBeenCalledWith(
          'at_test_token',
          '10.0.0.1'
        );
      });

      it('should use first IP from X-Forwarded-For chain', async () => {
        mockApiTokenService.validateToken.mockResolvedValue(null);

        await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_test_token')
          .set('X-Forwarded-For', '192.168.1.100, 10.0.0.1, 172.16.0.1');

        expect(mockApiTokenService.validateToken).toHaveBeenCalledWith(
          'at_test_token',
          '192.168.1.100'
        );
      });
    });

    describe('API Token without service configured', () => {
      beforeEach(() => {
        const middleware = createAuthMiddleware({ jwtSecret }); // No apiTokenService
        app.use(middleware);
        app.get('/test', (_req, res) => res.json({ ok: true }));
      });

      it('should return 401 when API token auth is not configured', async () => {
        const response = await request(app)
          .get('/test')
          .set('Authorization', 'Bearer at_test_token');

        expect(response.status).toBe(401);
        expect(response.body.detail).toContain('API token authentication is not configured');
      });
    });
  });

  describe('requireScope', () => {
    let app: Express;

    // Helper middleware that attaches user
    const attachUser = (user: AuthenticatedRequest['user']) => {
      return (req: express.Request, _res: express.Response, next: express.NextFunction) => {
        (req as AuthenticatedRequest).user = user;
        next();
      };
    };

    beforeEach(() => {
      app = express();
      app.use(express.json());
    });

    it('should allow JWT user regardless of scopes', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: [], // No scopes
        isApiToken: false,
      }));
      app.use(requireScope('accounts:read', 'accounts:write'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(200);
    });

    it('should allow API token with required scopes', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: ['accounts:read', 'accounts:write', 'transactions:read'],
        isApiToken: true,
      }));
      app.use(requireScope('accounts:read'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(200);
    });

    it('should allow API token with all required scopes', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: ['accounts:read', 'accounts:write'],
        isApiToken: true,
      }));
      app.use(requireScope('accounts:read', 'accounts:write'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(200);
    });

    it('should deny API token missing required scope', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: ['accounts:read'],
        isApiToken: true,
      }));
      app.use(requireScope('accounts:write'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(403);
      expect(response.body.type).toContain('forbidden');
      expect(response.body.detail).toContain('accounts:write');
      expect(response.body.required_scopes).toEqual(['accounts:write']);
      expect(response.body.token_scopes).toEqual(['accounts:read']);
    });

    it('should deny API token missing any of multiple required scopes', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: ['accounts:read'],
        isApiToken: true,
      }));
      app.use(requireScope('accounts:read', 'transactions:read'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(403);
      expect(response.body.required_scopes).toEqual(['accounts:read', 'transactions:read']);
    });

    it('should return 401 when user is not authenticated', async () => {
      // No user attached
      app.use(requireScope('accounts:read'));
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(401);
      expect(response.body.detail).toContain('Authentication required');
    });

    it('should work with no required scopes', async () => {
      app.use(attachUser({
        id: UserId.from(testUserId),
        scope: [],
        isApiToken: true,
      }));
      app.use(requireScope());
      app.get('/test', (_req, res) => res.json({ ok: true }));

      const response = await request(app).get('/test');

      expect(response.status).toBe(200);
    });
  });
});
