/**
 * ApiTokenController Unit Tests
 *
 * Tests the HTTP handlers for API token management.
 */

import express, { Express } from 'express';
import request from 'supertest';
import { createApiTokenController } from '../../../../src/infrastructure/http/controllers/ApiTokenController';
import { ApiTokenService } from '../../../../src/application/ports/input/ApiTokenService';
import { ApiToken, TokenScope } from '../../../../src/domain/entities/ApiToken';
import { ApiTokenId, UserId } from '../../../../src/domain/value-objects/Identifiers';
import { TokenNotFoundError } from '../../../../src/domain/errors';
import {
  TooManyTokensError,
  TokenAuthorizationError,
} from '../../../../src/application/use-cases/ManageApiTokens';

describe('ApiTokenController', () => {
  let app: Express;
  let mockService: jest.Mocked<ApiTokenService>;
  const testUserId = UserId.from('user-123');

  // Mock authentication middleware that sets user
  const mockAuthMiddleware = (isApiToken: boolean = false) => {
    return (req: express.Request, _res: express.Response, next: express.NextFunction) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (req as any).user = {
        id: testUserId,
        isApiToken,
      };
      next();
    };
  };

  // Helper to create a mock token
  function createMockToken(overrides: Partial<{
    id: ApiTokenId;
    userId: UserId;
    name: string;
    scopes: TokenScope[];
    expiresAt: Date | null;
  }> = {}): ApiToken {
    const params: Parameters<typeof ApiToken.create>[0] = {
      userId: overrides.userId ?? testUserId,
      name: overrides.name ?? 'Test Token',
      scopes: overrides.scopes ?? ['accounts:read'] as TokenScope[],
    };
    if (overrides.expiresAt !== undefined && overrides.expiresAt !== null) {
      params.expiresAt = overrides.expiresAt;
    }
    const { entity } = ApiToken.create(params);
    return entity;
  }

  beforeEach(() => {
    mockService = {
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

  describe('POST /api-tokens', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should create a new token successfully', async () => {
      const mockToken = createMockToken({ name: 'New Token' });
      mockService.createToken.mockResolvedValue({
        token: 'at_abc12345_secretpart123456789012345678901234567890',
        apiToken: mockToken,
      });

      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'New Token',
          scopes: ['accounts:read'],
        });

      expect(response.status).toBe(201);
      expect(response.body.token).toBeDefined();
      expect(response.body.name).toBe('New Token');
      expect(response.body.warning).toContain('Store this token securely');
      expect(response.headers['location']).toContain('/v1/api-tokens/');
      expect(mockService.createToken).toHaveBeenCalledWith({
        userId: testUserId,
        name: 'New Token',
        scopes: ['accounts:read'],
      });
    });

    it('should create token with expiration', async () => {
      const mockToken = createMockToken();
      mockService.createToken.mockResolvedValue({
        token: 'at_abc12345_secret',
        apiToken: mockToken,
      });

      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'Expiring Token',
          scopes: ['accounts:read'],
          expires_in_days: 30,
        });

      expect(response.status).toBe(201);
      expect(mockService.createToken).toHaveBeenCalledWith(
        expect.objectContaining({
          expiresInDays: 30,
        })
      );
    });

    it('should return 422 for validation errors - empty name', async () => {
      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: '',
          scopes: ['accounts:read'],
        });

      expect(response.status).toBe(422);
      expect(response.body.type).toContain('validation-error');
      expect(response.body.errors).toBeDefined();
    });

    it('should return 422 for validation errors - empty scopes', async () => {
      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'Test Token',
          scopes: [],
        });

      expect(response.status).toBe(422);
      expect(response.body.type).toContain('validation-error');
    });

    it('should return 422 for validation errors - invalid scope', async () => {
      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'Test Token',
          scopes: ['invalid:scope'],
        });

      expect(response.status).toBe(422);
      expect(response.body.type).toContain('validation-error');
    });

    it('should return 429 when token limit reached', async () => {
      mockService.createToken.mockRejectedValue(
        new TooManyTokensError(25)
      );

      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'One Too Many',
          scopes: ['accounts:read'],
        });

      expect(response.status).toBe(429);
      expect(response.body.type).toContain('too-many-tokens');
    });
  });

  describe('POST /api-tokens with API token auth', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(true)); // API token auth
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should return 403 when using API token to create tokens', async () => {
      const response = await request(app)
        .post('/api-tokens')
        .send({
          name: 'New Token',
          scopes: ['accounts:read'],
        });

      expect(response.status).toBe(403);
      expect(response.body.detail).toContain('API tokens cannot be used to create other API tokens');
      expect(mockService.createToken).not.toHaveBeenCalled();
    });
  });

  describe('GET /api-tokens', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should list all tokens for user', async () => {
      const tokens = [
        createMockToken({ name: 'Token 1' }),
        createMockToken({ name: 'Token 2' }),
      ];
      mockService.listTokens.mockResolvedValue(tokens);

      const response = await request(app).get('/api-tokens');

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].name).toBe('Token 1');
      expect(response.body.data[1].name).toBe('Token 2');
      // Should not include full token
      expect(response.body.data[0].token).toBeUndefined();
      expect(mockService.listTokens).toHaveBeenCalledWith(testUserId);
    });

    it('should return empty array when no tokens', async () => {
      mockService.listTokens.mockResolvedValue([]);

      const response = await request(app).get('/api-tokens');

      expect(response.status).toBe(200);
      expect(response.body.data).toEqual([]);
    });

    it('should return 403 when using API token auth', async () => {
      const appWithApiToken = express();
      appWithApiToken.use(express.json());
      appWithApiToken.use(mockAuthMiddleware(true));
      appWithApiToken.use('/api-tokens', createApiTokenController(mockService));

      const response = await request(appWithApiToken).get('/api-tokens');

      expect(response.status).toBe(403);
      expect(mockService.listTokens).not.toHaveBeenCalled();
    });
  });

  describe('GET /api-tokens/:id', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should return token details', async () => {
      const token = createMockToken({ name: 'My Token' });
      mockService.getToken.mockResolvedValue(token);

      const response = await request(app).get(`/api-tokens/${token.id}`);

      expect(response.status).toBe(200);
      expect(response.body.name).toBe('My Token');
      expect(response.body.prefix).toBeDefined();
      expect(response.body.scopes).toBeDefined();
      // Should not include full token
      expect(response.body.token).toBeUndefined();
    });

    it('should return 404 when token not found', async () => {
      mockService.getToken.mockResolvedValue(null);

      const response = await request(app).get('/api-tokens/550e8400-e29b-41d4-a716-446655440000');

      expect(response.status).toBe(404);
      expect(response.body.type).toContain('not-found');
    });

    it('should return 403 when token belongs to different user', async () => {
      mockService.getToken.mockRejectedValue(
        new TokenAuthorizationError('other-token-id')
      );

      const response = await request(app).get('/api-tokens/other-token-id');

      expect(response.status).toBe(403);
      expect(response.body.detail).toContain('do not have access');
    });

    it('should return 403 when using API token auth', async () => {
      const appWithApiToken = express();
      appWithApiToken.use(express.json());
      appWithApiToken.use(mockAuthMiddleware(true));
      appWithApiToken.use('/api-tokens', createApiTokenController(mockService));

      const response = await request(appWithApiToken).get('/api-tokens/some-id');

      expect(response.status).toBe(403);
    });
  });

  describe('PATCH /api-tokens/:id', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should update token name', async () => {
      const token = createMockToken({ name: 'Old Name' });
      mockService.updateToken.mockResolvedValue(token);

      const response = await request(app)
        .patch(`/api-tokens/${token.id}`)
        .send({ name: 'New Name' });

      expect(response.status).toBe(200);
      expect(mockService.updateToken).toHaveBeenCalledWith({
        tokenId: token.id,
        userId: testUserId,
        name: 'New Name',
      });
    });

    it('should return 422 for empty name', async () => {
      const response = await request(app)
        .patch('/api-tokens/some-id')
        .send({ name: '' });

      expect(response.status).toBe(422);
      expect(mockService.updateToken).not.toHaveBeenCalled();
    });

    it('should return 404 when token not found', async () => {
      mockService.updateToken.mockRejectedValue(
        new TokenNotFoundError('nonexistent-id')
      );

      const response = await request(app)
        .patch('/api-tokens/nonexistent-id')
        .send({ name: 'New Name' });

      expect(response.status).toBe(404);
    });

    it('should return 403 when token belongs to different user', async () => {
      mockService.updateToken.mockRejectedValue(
        new TokenAuthorizationError('other-token-id')
      );

      const response = await request(app)
        .patch('/api-tokens/other-token-id')
        .send({ name: 'New Name' });

      expect(response.status).toBe(403);
    });

    it('should return 403 when using API token auth', async () => {
      const appWithApiToken = express();
      appWithApiToken.use(express.json());
      appWithApiToken.use(mockAuthMiddleware(true));
      appWithApiToken.use('/api-tokens', createApiTokenController(mockService));

      const response = await request(appWithApiToken)
        .patch('/api-tokens/some-id')
        .send({ name: 'New Name' });

      expect(response.status).toBe(403);
    });
  });

  describe('DELETE /api-tokens/:id', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should revoke token successfully', async () => {
      const token = createMockToken();
      token.revoke('User requested');
      mockService.revokeToken.mockResolvedValue(token);

      const response = await request(app)
        .delete(`/api-tokens/${token.id}`)
        .send({ reason: 'User requested' });

      expect(response.status).toBe(200);
      expect(response.body.revoked_at).toBeDefined();
      expect(response.body.revoked_reason).toBe('User requested');
      expect(mockService.revokeToken).toHaveBeenCalledWith({
        tokenId: token.id,
        userId: testUserId,
        reason: 'User requested',
      });
    });

    it('should revoke token without reason', async () => {
      const token = createMockToken();
      token.revoke();
      mockService.revokeToken.mockResolvedValue(token);

      const response = await request(app)
        .delete(`/api-tokens/${token.id}`)
        .send({});

      expect(response.status).toBe(200);
      expect(mockService.revokeToken).toHaveBeenCalledWith({
        tokenId: token.id,
        userId: testUserId,
      });
    });

    it('should return 404 when token not found', async () => {
      mockService.revokeToken.mockRejectedValue(
        new TokenNotFoundError('nonexistent-id')
      );

      const response = await request(app)
        .delete('/api-tokens/nonexistent-id')
        .send({});

      expect(response.status).toBe(404);
    });

    it('should return 403 when token belongs to different user', async () => {
      mockService.revokeToken.mockRejectedValue(
        new TokenAuthorizationError('other-token-id')
      );

      const response = await request(app)
        .delete('/api-tokens/other-token-id')
        .send({});

      expect(response.status).toBe(403);
    });

    it('should return 422 for invalid reason (too long)', async () => {
      const response = await request(app)
        .delete('/api-tokens/some-id')
        .send({ reason: 'x'.repeat(501) });

      expect(response.status).toBe(422);
      expect(mockService.revokeToken).not.toHaveBeenCalled();
    });

    it('should return 403 when using API token auth', async () => {
      const appWithApiToken = express();
      appWithApiToken.use(express.json());
      appWithApiToken.use(mockAuthMiddleware(true));
      appWithApiToken.use('/api-tokens', createApiTokenController(mockService));

      const response = await request(appWithApiToken)
        .delete('/api-tokens/some-id')
        .send({});

      expect(response.status).toBe(403);
    });
  });

  describe('Response format', () => {
    beforeEach(() => {
      app.use(mockAuthMiddleware(false));
      app.use('/api-tokens', createApiTokenController(mockService));
    });

    it('should format token response correctly', async () => {
      const expiresAt = new Date('2025-12-31T23:59:59Z');
      const token = createMockToken({ expiresAt });
      mockService.getToken.mockResolvedValue(token);

      const response = await request(app).get(`/api-tokens/${token.id}`);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        id: expect.any(String),
        prefix: expect.any(String),
        name: expect.any(String),
        scopes: expect.any(Array),
        created_at: expect.any(String),
        expires_at: expect.any(String),
        last_used_at: null, // Not used yet
      });
      // Verify no sensitive data
      expect(response.body.token).toBeUndefined();
      expect(response.body.token_hash).toBeUndefined();
    });

    it('should include pagination in list response', async () => {
      mockService.listTokens.mockResolvedValue([]);

      const response = await request(app).get('/api-tokens');

      expect(response.status).toBe(200);
      expect(response.body.pagination).toEqual({
        has_more: false,
        next_cursor: null,
      });
    });
  });
});
