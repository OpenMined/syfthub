/**
 * Integration Test: API Token Lifecycle
 *
 * This test validates the complete API token lifecycle:
 * 1. User creates an API token with specific scopes
 * 2. API token is used to access resources
 * 3. Scope enforcement works correctly
 * 4. Token revocation prevents further access
 * 5. Expired tokens are rejected
 *
 * Run with: RUN_INTEGRATION_TESTS=true npm test -- --testPathPattern=ApiTokenLifecycle
 *
 * Prerequisites:
 * - PostgreSQL running with ledger_test database
 * - Migration 003_create_api_tokens applied
 */

import { Pool } from 'pg';
import express, { Express } from 'express';
import request from 'supertest';
import jwt from 'jsonwebtoken';

// Domain
import { Account } from '../../src/domain/entities/Account';
import { ApiToken, TokenScope } from '../../src/domain/entities/ApiToken';
import { Money } from '../../src/domain/value-objects/Money';
import { UserId, ApiTokenId } from '../../src/domain/value-objects/Identifiers';

// Infrastructure
import {
  PostgresAccountRepository,
} from '../../src/infrastructure/persistence';
import { PostgresApiTokenRepository } from '../../src/infrastructure/persistence/PostgresApiTokenRepository';
import {
  createAuthMiddleware,
  requireScope,
  AuthenticatedRequest,
} from '../../src/infrastructure/http/middleware/authentication';
import { createApiTokenController } from '../../src/infrastructure/http/controllers/ApiTokenController';

// Use Cases
import { ManageApiTokensUseCase } from '../../src/application/use-cases/ManageApiTokens';

// Skip if not explicitly enabled
const SKIP_INTEGRATION = process.env['RUN_INTEGRATION_TESTS'] !== 'true';
const describeIntegration = SKIP_INTEGRATION ? describe.skip : describe;

// Load test environment
const TEST_DB_URL = process.env['DATABASE_URL'] ?? 'postgresql://postgres:postgres@localhost:5432/ledger_test';
const JWT_SECRET = process.env['JWT_SECRET'] ?? 'test-jwt-secret-key-for-testing-only';

describeIntegration('API Token Lifecycle', () => {
  let pool: Pool;
  let accountRepository: PostgresAccountRepository;
  let apiTokenRepository: PostgresApiTokenRepository;
  let manageApiTokens: ManageApiTokensUseCase;
  let app: Express;

  // Test data
  let testUserId: UserId;
  let testAccount: Account;
  let jwtToken: string;

  beforeAll(async () => {
    // Create database pool
    pool = new Pool({
      connectionString: TEST_DB_URL,
      max: 5,
    });

    // Test connection
    try {
      await pool.query('SELECT 1');
      console.log('Database connection established');
    } catch (error) {
      console.error('Failed to connect to test database:', error);
      throw error;
    }

    // Create repositories
    accountRepository = new PostgresAccountRepository(pool);
    apiTokenRepository = new PostgresApiTokenRepository(pool);

    // Create use cases
    manageApiTokens = new ManageApiTokensUseCase(apiTokenRepository, {
      maxTokensPerUser: 25,
    });

    // Create Express app with auth middleware
    app = express();
    app.use(express.json());
    app.use(createAuthMiddleware({
      jwtSecret: JWT_SECRET,
      apiTokenService: manageApiTokens,
    }));

    // API Token management routes (JWT only)
    app.use('/v1/api-tokens', createApiTokenController(manageApiTokens));

    // Test protected route
    app.get('/v1/accounts',
      requireScope('accounts:read'),
      async (req, res) => {
        const authReq = req as AuthenticatedRequest;
        const accounts = await accountRepository.findByUserId(authReq.user.id);
        res.json({
          data: accounts.map(a => ({
            id: a.id.toString(),
            balance: a.balance.toJSON(),
          })),
          auth: {
            userId: authReq.user.id.toString(),
            isApiToken: authReq.user.isApiToken,
            tokenPrefix: authReq.user.tokenPrefix,
          },
        });
      }
    );

    // Test write operation route
    app.post('/v1/accounts/:id/credit',
      requireScope('accounts:write'),
      async (req, res) => {
        const authReq = req as AuthenticatedRequest;
        res.json({
          message: 'Credit applied (simulated)',
          auth: {
            userId: authReq.user.id.toString(),
            isApiToken: authReq.user.isApiToken,
          },
        });
      }
    );
  });

  afterAll(async () => {
    await pool.end();
    console.log('Database connection closed');
  });

  beforeEach(async () => {
    // Clean up test data
    await pool.query('DELETE FROM api_tokens');
    await pool.query('DELETE FROM accounts');

    // Create test user
    testUserId = UserId.generate();

    // Create test account
    testAccount = Account.create({
      userId: testUserId,
      type: 'user',
    });
    testAccount.credit(Money.credits(1000n));

    await pool.query(
      `INSERT INTO accounts (id, user_id, type, status, balance, available_balance, currency, metadata, version)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
      [
        testAccount.id.toString(),
        testUserId.toString(),
        'user',
        'active',
        '1000',
        '1000',
        'CREDIT',
        JSON.stringify({}),
        1,
      ]
    );

    // Create JWT for the test user
    const now = Math.floor(Date.now() / 1000);
    jwtToken = jwt.sign({
      sub: testUserId.toString(),
      scope: ['accounts:read', 'accounts:write'],
      exp: now + 3600,
      iat: now,
      jti: `test-jwt-${Date.now()}`,
    }, JWT_SECRET);
  });

  describe('Token Creation', () => {
    it('should create a new API token via HTTP endpoint', async () => {
      const response = await request(app)
        .post('/v1/api-tokens')
        .set('Authorization', `Bearer ${jwtToken}`)
        .send({
          name: 'Production Token',
          scopes: ['accounts:read', 'transactions:read'],
        });

      expect(response.status).toBe(201);
      expect(response.body.token).toMatch(/^at_[a-f0-9]{8}_/);
      expect(response.body.name).toBe('Production Token');
      expect(response.body.scopes).toEqual(['accounts:read', 'transactions:read']);
      expect(response.body.warning).toContain('Store this token securely');
      expect(response.headers['location']).toContain('/v1/api-tokens/');
    });

    it('should create token with expiration', async () => {
      const response = await request(app)
        .post('/v1/api-tokens')
        .set('Authorization', `Bearer ${jwtToken}`)
        .send({
          name: 'Expiring Token',
          scopes: ['accounts:read'],
          expires_in_days: 30,
        });

      expect(response.status).toBe(201);
      expect(response.body.expires_at).toBeDefined();

      const expiresAt = new Date(response.body.expires_at);
      const expectedExpiry = new Date();
      expectedExpiry.setDate(expectedExpiry.getDate() + 30);

      // Allow 10 second tolerance
      expect(Math.abs(expiresAt.getTime() - expectedExpiry.getTime())).toBeLessThan(10000);
    });
  });

  describe('Token Usage', () => {
    let apiToken: string;

    beforeEach(async () => {
      // Create an API token
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Test Token',
        scopes: ['accounts:read'] as TokenScope[],
      });
      apiToken = result.token;
    });

    it('should authenticate with API token', async () => {
      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${apiToken}`);

      expect(response.status).toBe(200);
      expect(response.body.auth.isApiToken).toBe(true);
      expect(response.body.auth.userId).toBe(testUserId.toString());
    });

    it('should return account data when authenticated', async () => {
      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${apiToken}`);

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].id).toBe(testAccount.id.toString());
    });

    it('should record token usage', async () => {
      await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${apiToken}`)
        .set('X-Forwarded-For', '192.168.1.100');

      // Wait for async usage update
      await new Promise(resolve => setTimeout(resolve, 50));

      // Check token was updated
      const result = await pool.query(
        'SELECT last_used_at, last_used_ip FROM api_tokens WHERE user_id = $1',
        [testUserId.toString()]
      );

      expect(result.rows[0]).toBeDefined();
      expect(result.rows[0].last_used_at).toBeDefined();
      expect(result.rows[0].last_used_ip).toBe('192.168.1.100');
    });
  });

  describe('Scope Enforcement', () => {
    it('should allow access to resources within token scope', async () => {
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Read Token',
        scopes: ['accounts:read'] as TokenScope[],
      });

      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${result.token}`);

      expect(response.status).toBe(200);
    });

    it('should deny access to resources outside token scope', async () => {
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Read Only Token',
        scopes: ['accounts:read'] as TokenScope[],
      });

      const response = await request(app)
        .post(`/v1/accounts/${testAccount.id}/credit`)
        .set('Authorization', `Bearer ${result.token}`)
        .send({ amount: 100 });

      expect(response.status).toBe(403);
      expect(response.body.required_scopes).toContain('accounts:write');
      expect(response.body.token_scopes).toEqual(['accounts:read']);
    });

    it('should allow access with multiple matching scopes', async () => {
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Full Access Token',
        scopes: ['accounts:read', 'accounts:write'] as TokenScope[],
      });

      const readResponse = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${result.token}`);

      const writeResponse = await request(app)
        .post(`/v1/accounts/${testAccount.id}/credit`)
        .set('Authorization', `Bearer ${result.token}`)
        .send({ amount: 100 });

      expect(readResponse.status).toBe(200);
      expect(writeResponse.status).toBe(200);
    });
  });

  describe('Token Revocation', () => {
    let apiToken: string;
    let tokenId: ApiTokenId;

    beforeEach(async () => {
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'To Be Revoked',
        scopes: ['accounts:read'] as TokenScope[],
      });
      apiToken = result.token;
      tokenId = result.apiToken.id;
    });

    it('should revoke token via HTTP endpoint', async () => {
      const response = await request(app)
        .delete(`/v1/api-tokens/${tokenId}`)
        .set('Authorization', `Bearer ${jwtToken}`)
        .send({ reason: 'No longer needed' });

      expect(response.status).toBe(200);
      expect(response.body.revoked_at).toBeDefined();
      expect(response.body.revoked_reason).toBe('No longer needed');
    });

    it('should reject revoked token', async () => {
      // Revoke the token
      await manageApiTokens.revokeToken({
        tokenId,
        userId: testUserId,
        reason: 'Security concern',
      });

      // Try to use it
      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${apiToken}`);

      expect(response.status).toBe(401);
      expect(response.body.detail).toContain('invalid, expired, or revoked');
    });
  });

  describe('Token Expiration', () => {
    it('should reject expired token', async () => {
      // Create an already-expired token by inserting directly
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Expired Token',
        scopes: ['accounts:read'] as TokenScope[],
        expiresAt: new Date(Date.now() - 1000), // Expired 1 second ago
      });

      await apiTokenRepository.save(entity);

      // Try to use it
      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${token}`);

      expect(response.status).toBe(401);
    });
  });

  describe('Token Listing', () => {
    beforeEach(async () => {
      // Create multiple tokens
      await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Token 1',
        scopes: ['accounts:read'] as TokenScope[],
      });
      await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Token 2',
        scopes: ['accounts:read', 'transactions:read'] as TokenScope[],
      });
    });

    it('should list all tokens for user', async () => {
      const response = await request(app)
        .get('/v1/api-tokens')
        .set('Authorization', `Bearer ${jwtToken}`);

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data.map((t: { name: string }) => t.name)).toContain('Token 1');
      expect(response.body.data.map((t: { name: string }) => t.name)).toContain('Token 2');
    });

    it('should not expose full token in listing', async () => {
      const response = await request(app)
        .get('/v1/api-tokens')
        .set('Authorization', `Bearer ${jwtToken}`);

      expect(response.status).toBe(200);
      response.body.data.forEach((token: { token?: string; prefix: string }) => {
        expect(token.token).toBeUndefined();
        expect(token.prefix).toBeDefined();
      });
    });
  });

  describe('API Token Cannot Manage Tokens', () => {
    let apiToken: string;

    beforeEach(async () => {
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Regular Token',
        scopes: ['accounts:read', 'accounts:write'] as TokenScope[],
      });
      apiToken = result.token;
    });

    it('should not allow API token to create new tokens', async () => {
      const response = await request(app)
        .post('/v1/api-tokens')
        .set('Authorization', `Bearer ${apiToken}`)
        .send({
          name: 'Nested Token',
          scopes: ['accounts:read'],
        });

      expect(response.status).toBe(403);
      expect(response.body.detail).toContain('API tokens cannot be used to create other API tokens');
    });

    it('should not allow API token to list tokens', async () => {
      const response = await request(app)
        .get('/v1/api-tokens')
        .set('Authorization', `Bearer ${apiToken}`);

      expect(response.status).toBe(403);
    });

    it('should not allow API token to revoke tokens', async () => {
      const response = await request(app)
        .delete('/v1/api-tokens/some-token-id')
        .set('Authorization', `Bearer ${apiToken}`);

      expect(response.status).toBe(403);
    });
  });

  describe('Token Limit', () => {
    it('should enforce maximum tokens per user', async () => {
      // Create a use case with a low limit for testing
      const limitedUseCase = new ManageApiTokensUseCase(apiTokenRepository, {
        maxTokensPerUser: 3,
      });

      // Create 3 tokens
      for (let i = 0; i < 3; i++) {
        await limitedUseCase.createToken({
          userId: testUserId,
          name: `Token ${i + 1}`,
          scopes: ['accounts:read'] as TokenScope[],
        });
      }

      // Try to create a 4th token
      await expect(
        limitedUseCase.createToken({
          userId: testUserId,
          name: 'Token 4',
          scopes: ['accounts:read'] as TokenScope[],
        })
      ).rejects.toThrow('Maximum number of tokens (3) reached');
    });
  });

  describe('Multi-user Isolation', () => {
    let otherUserId: UserId;
    let otherUserToken: string;
    let otherUserJwt: string;

    beforeEach(async () => {
      otherUserId = UserId.generate();

      // Create API token for other user
      const result = await manageApiTokens.createToken({
        userId: otherUserId,
        name: 'Other User Token',
        scopes: ['accounts:read'] as TokenScope[],
      });
      otherUserToken = result.token;

      // Create JWT for other user
      const now = Math.floor(Date.now() / 1000);
      otherUserJwt = jwt.sign({
        sub: otherUserId.toString(),
        scope: [],
        exp: now + 3600,
        iat: now,
        jti: `test-jwt-other-${Date.now()}`,
      }, JWT_SECRET);
    });

    it('should not return accounts from other users', async () => {
      // Other user's token should not see test user's accounts
      const response = await request(app)
        .get('/v1/accounts')
        .set('Authorization', `Bearer ${otherUserToken}`);

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(0); // No accounts for other user
    });

    it('should not allow access to other user tokens', async () => {
      // Create a token for test user
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Test User Token',
        scopes: ['accounts:read'] as TokenScope[],
      });

      // Other user should not be able to view it
      const response = await request(app)
        .get(`/v1/api-tokens/${result.apiToken.id}`)
        .set('Authorization', `Bearer ${otherUserJwt}`);

      expect(response.status).toBe(403);
    });

    it('should not allow revoking other user tokens', async () => {
      // Create a token for test user
      const result = await manageApiTokens.createToken({
        userId: testUserId,
        name: 'Test User Token',
        scopes: ['accounts:read'] as TokenScope[],
      });

      // Other user should not be able to revoke it
      const response = await request(app)
        .delete(`/v1/api-tokens/${result.apiToken.id}`)
        .set('Authorization', `Bearer ${otherUserJwt}`);

      expect(response.status).toBe(403);
    });
  });
});
