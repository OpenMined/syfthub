/**
 * PostgresApiTokenRepository Unit Tests
 *
 * Tests the PostgreSQL API token repository with mocked database.
 */

import { Pool, PoolClient as PgPoolClient, QueryResult } from 'pg';
type PoolClient = PgPoolClient;
import { PostgresApiTokenRepository } from '../../../src/infrastructure/persistence/PostgresApiTokenRepository';
import { ApiToken, TokenScope } from '../../../src/domain/entities/ApiToken';
import { ApiTokenId, UserId } from '../../../src/domain/value-objects/Identifiers';
import { OptimisticLockError } from '../../../src/infrastructure/persistence/PostgresAccountRepository';

describe('PostgresApiTokenRepository', () => {
  let repository: PostgresApiTokenRepository;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockPool: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockClient: any;

  const testUserId = UserId.from('user-123');
  const testTokenId = ApiTokenId.from('550e8400-e29b-41d4-a716-446655440000');

  // Helper to create mock query result
  function createQueryResult<T extends Record<string, unknown>>(rows: T[], rowCount: number = rows.length): QueryResult<T> {
    return {
      rows,
      rowCount,
      command: 'SELECT',
      oid: 0,
      fields: [],
    };
  }

  // Helper to create mock token row from database
  function createMockRow(overrides: Partial<{
    id: string;
    user_id: string;
    token_prefix: string;
    token_hash: Buffer;
    name: string;
    scopes: string[];
    created_at: Date;
    expires_at: Date | null;
    last_used_at: Date | null;
    last_used_ip: string | null;
    revoked_at: Date | null;
    revoked_reason: string | null;
    version: number;
  }> = {}) {
    return {
      id: testTokenId.toString(),
      user_id: testUserId.toString(),
      token_prefix: 'abcd1234',
      token_hash: Buffer.from('somehash'),
      name: 'Test Token',
      scopes: ['accounts:read'] as string[],
      created_at: new Date('2024-01-15T10:00:00Z'),
      expires_at: null,
      last_used_at: null,
      last_used_ip: null,
      revoked_at: null,
      revoked_reason: null,
      version: 1,
      ...overrides,
    };
  }

  beforeEach(() => {
    mockPool = {
      query: jest.fn(),
    };

    mockClient = {
      query: jest.fn(),
      release: jest.fn(),
    };

    repository = new PostgresApiTokenRepository(mockPool as unknown as Pool);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findById', () => {
    it('should return token when found', async () => {
      const mockRow = createMockRow();
      mockPool.query.mockResolvedValue(createQueryResult([mockRow]));

      const result = await repository.findById(testTokenId);

      expect(result).not.toBeNull();
      expect(result!.id).toBe(testTokenId);
      expect(result!.userId).toBe(testUserId);
      expect(result!.name).toBe('Test Token');
      expect(result!.scopes).toEqual(['accounts:read']);
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT * FROM api_tokens WHERE id = $1'),
        [testTokenId]
      );
    });

    it('should return null when not found', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([]));

      const result = await repository.findById(testTokenId);

      expect(result).toBeNull();
    });

    it('should trim token prefix from char(8) field', async () => {
      const mockRow = createMockRow({ token_prefix: 'abc12   ' }); // Trailing spaces from char(8)
      mockPool.query.mockResolvedValue(createQueryResult([mockRow]));

      const result = await repository.findById(testTokenId);

      expect(result!.prefix).toBe('abc12');
    });
  });

  describe('findByHash', () => {
    it('should return token when found by hash', async () => {
      const testHash = Buffer.from('testhash');
      const mockRow = createMockRow();
      mockPool.query.mockResolvedValue(createQueryResult([mockRow]));

      const result = await repository.findByHash(testHash);

      expect(result).not.toBeNull();
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('WHERE token_hash = $1 AND revoked_at IS NULL'),
        [testHash]
      );
    });

    it('should return null when hash not found', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([]));

      const result = await repository.findByHash(Buffer.from('nonexistent'));

      expect(result).toBeNull();
    });

    it('should not return revoked tokens', async () => {
      // The query filters by revoked_at IS NULL
      mockPool.query.mockResolvedValue(createQueryResult([]));

      const result = await repository.findByHash(Buffer.from('hash'));

      expect(result).toBeNull();
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('revoked_at IS NULL'),
        expect.anything()
      );
    });
  });

  describe('findByUserId', () => {
    it('should return all active tokens for user', async () => {
      const mockRows = [
        createMockRow({ name: 'Token 1' }),
        createMockRow({ id: 'other-id', name: 'Token 2' }),
      ];
      mockPool.query.mockResolvedValue(createQueryResult(mockRows));

      const result = await repository.findByUserId(testUserId);

      expect(result).toHaveLength(2);
      expect(result[0]!.name).toBe('Token 1');
      expect(result[1]!.name).toBe('Token 2');
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('WHERE user_id = $1 AND revoked_at IS NULL'),
        [testUserId]
      );
    });

    it('should return empty array when no tokens found', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([]));

      const result = await repository.findByUserId(testUserId);

      expect(result).toEqual([]);
    });

    it('should order tokens by created_at descending', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([]));

      await repository.findByUserId(testUserId);

      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('ORDER BY created_at DESC'),
        expect.anything()
      );
    });
  });

  describe('save', () => {
    it('should insert new token', async () => {
      const { entity: token } = ApiToken.create({
        userId: testUserId,
        name: 'New Token',
        scopes: ['accounts:read', 'transactions:read'] as TokenScope[],
      });

      mockPool.query.mockResolvedValue(createQueryResult([], 1));

      await repository.save(token);

      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO api_tokens'),
        expect.arrayContaining([
          token.id,
          token.userId,
          token.prefix,
          token.tokenHash,
          token.name,
          token.scopes,
          token.createdAt,
          token.expiresAt,
          token.lastUsedAt,
          token.lastUsedIp,
          token.revokedAt,
          token.revokedReason,
          token.version,
        ])
      );
    });

    it('should save token with expiration', async () => {
      const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000); // 30 days
      const { entity: token } = ApiToken.create({
        userId: testUserId,
        name: 'Expiring Token',
        scopes: ['accounts:read'] as TokenScope[],
        expiresAt,
      });

      mockPool.query.mockResolvedValue(createQueryResult([], 1));

      await repository.save(token);

      const callArgs = mockPool.query.mock.calls[0]![1] as unknown[];
      expect(callArgs[7]).toEqual(expiresAt); // expires_at parameter position
    });
  });

  describe('update', () => {
    it('should update token successfully', async () => {
      const mockRow = createMockRow({ version: 1 });
      mockPool.query
        .mockResolvedValueOnce(createQueryResult([mockRow])) // findById
        .mockResolvedValueOnce(createQueryResult([], 1)); // update

      const token = await repository.findById(testTokenId);
      token!.updateName('Updated Name');

      await repository.update(token!);

      expect(mockPool.query).toHaveBeenLastCalledWith(
        expect.stringContaining('UPDATE api_tokens SET'),
        expect.arrayContaining(['Updated Name'])
      );
    });

    it('should throw OptimisticLockError when version mismatch', async () => {
      const { entity: token } = ApiToken.create({
        userId: testUserId,
        name: 'Token',
        scopes: ['accounts:read'] as TokenScope[],
      });

      // Simulate version mismatch - no rows updated
      mockPool.query.mockResolvedValue(createQueryResult([], 0));

      await expect(repository.update(token)).rejects.toThrow(OptimisticLockError);
    });

    it('should update revoked token fields', async () => {
      const mockRow = createMockRow({ version: 1 });
      mockPool.query
        .mockResolvedValueOnce(createQueryResult([mockRow]))
        .mockResolvedValueOnce(createQueryResult([], 1));

      const token = await repository.findById(testTokenId);
      token!.revoke('User requested');

      await repository.update(token!);

      const updateCall = mockPool.query.mock.calls[1]!;
      const updateArgs = updateCall[1] as unknown[];
      expect(updateArgs[3]).toBeInstanceOf(Date); // revoked_at
      expect(updateArgs[4]).toBe('User requested'); // revoked_reason
    });

    it('should update last used fields', async () => {
      const mockRow = createMockRow({ version: 1 });
      mockPool.query
        .mockResolvedValueOnce(createQueryResult([mockRow]))
        .mockResolvedValueOnce(createQueryResult([], 1));

      const token = await repository.findById(testTokenId);
      token!.recordUsage('192.168.1.1');

      await repository.update(token!);

      const updateCall = mockPool.query.mock.calls[1]!;
      const updateArgs = updateCall[1] as unknown[];
      expect(updateArgs[1]).toBeInstanceOf(Date); // last_used_at
      expect(updateArgs[2]).toBe('192.168.1.1'); // last_used_ip
    });
  });

  describe('countByUserId', () => {
    it('should return count of active tokens', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([{ count: '5' }]));

      const count = await repository.countByUserId(testUserId);

      expect(count).toBe(5);
      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT COUNT(*) as count'),
        [testUserId]
      );
    });

    it('should return 0 when no tokens', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([{ count: '0' }]));

      const count = await repository.countByUserId(testUserId);

      expect(count).toBe(0);
    });

    it('should only count non-revoked tokens', async () => {
      mockPool.query.mockResolvedValue(createQueryResult([{ count: '3' }]));

      await repository.countByUserId(testUserId);

      expect(mockPool.query).toHaveBeenCalledWith(
        expect.stringContaining('revoked_at IS NULL'),
        expect.anything()
      );
    });
  });

  describe('withClient', () => {
    it('should create new repository bound to client', () => {
      const boundRepository = repository.withClient(mockClient as PoolClient);

      expect(boundRepository).toBeInstanceOf(PostgresApiTokenRepository);
      expect(boundRepository).not.toBe(repository);
    });

    it('should use client for queries when bound', async () => {
      const boundRepository = repository.withClient(mockClient as PoolClient);
      mockClient.query.mockResolvedValue(createQueryResult([]));

      await boundRepository.findById(testTokenId);

      expect(mockClient.query).toHaveBeenCalled();
      expect(mockPool.query).not.toHaveBeenCalled();
    });
  });

  describe('mapRowToToken', () => {
    it('should correctly map all token fields', async () => {
      const mockRow = createMockRow({
        id: '550e8400-e29b-41d4-a716-446655440001',
        user_id: 'user-456',
        token_prefix: 'xyz98765',
        token_hash: Buffer.from('hashvalue'),
        name: 'Complete Token',
        scopes: ['accounts:read', 'transactions:read', 'deposits:write'],
        created_at: new Date('2024-01-01T00:00:00Z'),
        expires_at: new Date('2024-12-31T23:59:59Z'),
        last_used_at: new Date('2024-06-15T12:00:00Z'),
        last_used_ip: '10.0.0.1',
        revoked_at: null,
        revoked_reason: null,
        version: 3,
      });
      mockPool.query.mockResolvedValue(createQueryResult([mockRow]));

      const token = await repository.findById(ApiTokenId.from('550e8400-e29b-41d4-a716-446655440001'));

      expect(token!.id.toString()).toBe('550e8400-e29b-41d4-a716-446655440001');
      expect(token!.userId.toString()).toBe('user-456');
      expect(token!.prefix).toBe('xyz98765');
      expect(token!.name).toBe('Complete Token');
      expect(token!.scopes).toEqual(['accounts:read', 'transactions:read', 'deposits:write']);
      expect(token!.createdAt).toEqual(new Date('2024-01-01T00:00:00Z'));
      expect(token!.expiresAt).toEqual(new Date('2024-12-31T23:59:59Z'));
      expect(token!.lastUsedAt).toEqual(new Date('2024-06-15T12:00:00Z'));
      expect(token!.lastUsedIp).toBe('10.0.0.1');
      expect(token!.version).toBe(3);
    });

    it('should handle null optional fields', async () => {
      const mockRow = createMockRow({
        expires_at: null,
        last_used_at: null,
        last_used_ip: null,
        revoked_at: null,
        revoked_reason: null,
      });
      mockPool.query.mockResolvedValue(createQueryResult([mockRow]));

      const token = await repository.findById(testTokenId);

      expect(token!.expiresAt).toBeNull();
      expect(token!.lastUsedAt).toBeNull();
      expect(token!.lastUsedIp).toBeNull();
      expect(token!.revokedAt).toBeNull();
      expect(token!.revokedReason).toBeNull();
    });
  });
});
