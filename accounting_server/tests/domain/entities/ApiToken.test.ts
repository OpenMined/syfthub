/**
 * ApiToken Entity Unit Tests
 *
 * Tests the ApiToken entity including creation, validation, and state transitions.
 */

import { ApiToken, TokenScope, ALL_TOKEN_SCOPES } from '../../../src/domain/entities/ApiToken';
import { UserId } from '../../../src/domain/value-objects/Identifiers';

describe('ApiToken', () => {
  const testUserId = UserId.from('user-123');

  describe('create', () => {
    it('should create a new token with valid parameters', () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'My API Token',
        scopes: ['accounts:read', 'transactions:read'],
      });

      expect(token).toMatch(/^at_[a-f0-9]{8}_[A-Za-z0-9_-]+$/);
      expect(entity.userId).toBe(testUserId);
      expect(entity.name).toBe('My API Token');
      expect(entity.scopes).toEqual(['accounts:read', 'transactions:read']);
      expect(entity.prefix).toHaveLength(8);
      expect(entity.version).toBe(1);
      expect(entity.revokedAt).toBeNull();
      expect(entity.expiresAt).toBeNull();
      expect(entity.lastUsedAt).toBeNull();
    });

    it('should create a token with expiration date', () => {
      const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // 7 days
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Expiring Token',
        scopes: ['accounts:read'],
        expiresAt,
      });

      expect(entity.expiresAt).toEqual(expiresAt);
    });

    it('should generate unique tokens on each call', () => {
      const result1 = ApiToken.create({
        userId: testUserId,
        name: 'Token 1',
        scopes: ['accounts:read'],
      });

      const result2 = ApiToken.create({
        userId: testUserId,
        name: 'Token 2',
        scopes: ['accounts:read'],
      });

      expect(result1.token).not.toBe(result2.token);
      expect(result1.entity.id).not.toBe(result2.entity.id);
      expect(result1.entity.prefix).not.toBe(result2.entity.prefix);
    });

    it('should generate unique hash for each token', () => {
      const result1 = ApiToken.create({
        userId: testUserId,
        name: 'Token 1',
        scopes: ['accounts:read'],
      });

      const result2 = ApiToken.create({
        userId: testUserId,
        name: 'Token 2',
        scopes: ['accounts:read'],
      });

      expect(result1.entity.tokenHash.equals(result2.entity.tokenHash)).toBe(false);
    });
  });

  describe('hashToken', () => {
    it('should produce consistent hash for the same token', () => {
      const token = 'at_12345678_abcdefghijklmnopqrstuvwxyz1234567890AB';

      const hash1 = ApiToken.hashToken(token);
      const hash2 = ApiToken.hashToken(token);

      expect(hash1.equals(hash2)).toBe(true);
    });

    it('should produce different hashes for different tokens', () => {
      const hash1 = ApiToken.hashToken('at_12345678_token1');
      const hash2 = ApiToken.hashToken('at_12345678_token2');

      expect(hash1.equals(hash2)).toBe(false);
    });

    it('should produce a 32-byte SHA-256 hash', () => {
      const hash = ApiToken.hashToken('at_12345678_anytoken');

      expect(hash).toBeInstanceOf(Buffer);
      expect(hash.length).toBe(32);
    });
  });

  describe('compareHashes', () => {
    it('should return true for equal hashes', () => {
      const hash1 = ApiToken.hashToken('at_12345678_sametoken');
      const hash2 = ApiToken.hashToken('at_12345678_sametoken');

      expect(ApiToken.compareHashes(hash1, hash2)).toBe(true);
    });

    it('should return false for different hashes', () => {
      const hash1 = ApiToken.hashToken('at_12345678_token1');
      const hash2 = ApiToken.hashToken('at_87654321_token2');

      expect(ApiToken.compareHashes(hash1, hash2)).toBe(false);
    });

    it('should return false for hashes of different lengths', () => {
      const hash1 = Buffer.from('short');
      const hash2 = Buffer.from('much longer buffer');

      expect(ApiToken.compareHashes(hash1, hash2)).toBe(false);
    });
  });

  describe('parseToken', () => {
    it('should parse valid token format', () => {
      const result = ApiToken.parseToken('at_12345678_abcdefghijklmnop');

      expect(result.valid).toBe(true);
      expect(result.prefix).toBe('12345678');
    });

    it('should reject token without at_ prefix', () => {
      const result = ApiToken.parseToken('jwt_12345678_abcdefghijklmnop');

      expect(result.valid).toBe(false);
      expect(result.prefix).toBeUndefined();
    });

    it('should reject token with wrong number of parts', () => {
      expect(ApiToken.parseToken('at_12345678').valid).toBe(false);
      expect(ApiToken.parseToken('at_12345678_abc_extra').valid).toBe(false);
      expect(ApiToken.parseToken('at_').valid).toBe(false);
    });

    it('should reject token with invalid prefix length', () => {
      expect(ApiToken.parseToken('at_1234567_secret').valid).toBe(false); // 7 chars
      expect(ApiToken.parseToken('at_123456789_secret').valid).toBe(false); // 9 chars
    });
  });

  describe('isValid', () => {
    it('should return true for non-revoked, non-expired token', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Token',
        scopes: ['accounts:read'],
      });

      expect(entity.isValid()).toBe(true);
    });

    it('should return false for revoked token', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      entity.revoke('No longer needed');

      expect(entity.isValid()).toBe(false);
    });

    it('should return false for expired token', () => {
      const pastDate = new Date(Date.now() - 1000); // 1 second ago
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Expired Token',
        scopes: ['accounts:read'],
        expiresAt: pastDate,
      });

      expect(entity.isValid()).toBe(false);
    });

    it('should return true for token with future expiration', () => {
      const futureDate = new Date(Date.now() + 86400000); // 1 day from now
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Future Token',
        scopes: ['accounts:read'],
        expiresAt: futureDate,
      });

      expect(entity.isValid()).toBe(true);
    });
  });

  describe('isExpired', () => {
    it('should return false for token without expiration', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'No Expiry Token',
        scopes: ['accounts:read'],
      });

      expect(entity.isExpired()).toBe(false);
    });

    it('should return true for expired token', () => {
      const pastDate = new Date(Date.now() - 1000);
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Expired Token',
        scopes: ['accounts:read'],
        expiresAt: pastDate,
      });

      expect(entity.isExpired()).toBe(true);
    });

    it('should return false for token with future expiration', () => {
      const futureDate = new Date(Date.now() + 86400000);
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Future Token',
        scopes: ['accounts:read'],
        expiresAt: futureDate,
      });

      expect(entity.isExpired()).toBe(false);
    });
  });

  describe('isRevoked', () => {
    it('should return false for non-revoked token', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Active Token',
        scopes: ['accounts:read'],
      });

      expect(entity.isRevoked()).toBe(false);
    });

    it('should return true for revoked token', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      entity.revoke();

      expect(entity.isRevoked()).toBe(true);
    });
  });

  describe('hasScope', () => {
    it('should return true for existing scope', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token with Scopes',
        scopes: ['accounts:read', 'accounts:write', 'transactions:read'],
      });

      expect(entity.hasScope('accounts:read')).toBe(true);
      expect(entity.hasScope('accounts:write')).toBe(true);
      expect(entity.hasScope('transactions:read')).toBe(true);
    });

    it('should return false for missing scope', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token with Limited Scopes',
        scopes: ['accounts:read'],
      });

      expect(entity.hasScope('accounts:write')).toBe(false);
      expect(entity.hasScope('transfers:write')).toBe(false);
    });
  });

  describe('hasAllScopes', () => {
    it('should return true when token has all required scopes', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Multi-scope Token',
        scopes: ['accounts:read', 'accounts:write', 'transactions:read'],
      });

      expect(entity.hasAllScopes(['accounts:read', 'transactions:read'])).toBe(true);
    });

    it('should return false when token is missing some scopes', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Limited Token',
        scopes: ['accounts:read'],
      });

      expect(entity.hasAllScopes(['accounts:read', 'accounts:write'])).toBe(false);
    });

    it('should return true for empty scope array', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Any Token',
        scopes: ['accounts:read'],
      });

      expect(entity.hasAllScopes([])).toBe(true);
    });
  });

  describe('recordUsage', () => {
    it('should update lastUsedAt and lastUsedIp', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Track',
        scopes: ['accounts:read'],
      });

      const initialVersion = entity.version;

      entity.recordUsage('192.168.1.100');

      expect(entity.lastUsedAt).toBeInstanceOf(Date);
      expect(entity.lastUsedIp).toBe('192.168.1.100');
      expect(entity.version).toBe(initialVersion + 1);
    });

    it('should update usage on subsequent calls', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Track',
        scopes: ['accounts:read'],
      });

      entity.recordUsage('192.168.1.1');
      const firstUsedAt = entity.lastUsedAt;

      // Small delay to ensure different timestamps
      entity.recordUsage('10.0.0.1');

      expect(entity.lastUsedIp).toBe('10.0.0.1');
      expect(entity.lastUsedAt!.getTime()).toBeGreaterThanOrEqual(firstUsedAt!.getTime());
    });
  });

  describe('revoke', () => {
    it('should set revokedAt timestamp', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      entity.revoke();

      expect(entity.revokedAt).toBeInstanceOf(Date);
      expect(entity.revokedReason).toBeNull();
    });

    it('should set revocation reason when provided', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      entity.revoke('Security concern');

      expect(entity.revokedReason).toBe('Security concern');
    });

    it('should be idempotent (calling twice does not change timestamp)', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      entity.revoke('First revocation');
      const firstRevokedAt = entity.revokedAt;
      const firstVersion = entity.version;

      entity.revoke('Second revocation');

      expect(entity.revokedAt).toEqual(firstRevokedAt);
      expect(entity.revokedReason).toBe('First revocation');
      expect(entity.version).toBe(firstVersion);
    });

    it('should increment version', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Token to Revoke',
        scopes: ['accounts:read'],
      });

      const initialVersion = entity.version;
      entity.revoke();

      expect(entity.version).toBe(initialVersion + 1);
    });
  });

  describe('updateName', () => {
    it('should update the token name', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Original Name',
        scopes: ['accounts:read'],
      });

      entity.updateName('New Name');

      expect(entity.name).toBe('New Name');
    });

    it('should increment version', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Original Name',
        scopes: ['accounts:read'],
      });

      const initialVersion = entity.version;
      entity.updateName('New Name');

      expect(entity.version).toBe(initialVersion + 1);
    });

    it('should reject empty name', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Name',
        scopes: ['accounts:read'],
      });

      expect(() => entity.updateName('')).toThrow('Token name must be between 1 and 100 characters');
    });

    it('should reject name exceeding 100 characters', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Name',
        scopes: ['accounts:read'],
      });

      const longName = 'a'.repeat(101);
      expect(() => entity.updateName(longName)).toThrow('Token name must be between 1 and 100 characters');
    });
  });

  describe('toJSON', () => {
    it('should return serializable representation without sensitive data', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Test Token',
        scopes: ['accounts:read', 'transactions:read'],
      });

      entity.recordUsage('127.0.0.1');

      const json = entity.toJSON();

      expect(json['id']).toBe(entity.id);
      expect(json['userId']).toBe(testUserId);
      expect(json['prefix']).toBe(entity.prefix);
      expect(json['name']).toBe('Test Token');
      expect(json['scopes']).toEqual(['accounts:read', 'transactions:read']);
      expect(json['createdAt']).toBeDefined();
      expect(json['lastUsedAt']).toBeDefined();
      expect(json['version']).toBe(entity.version);

      // Should NOT include token hash or full token
      expect(json['tokenHash']).toBeUndefined();
      expect(json['token']).toBeUndefined();
    });

    it('should handle null dates correctly', () => {
      const { entity } = ApiToken.create({
        userId: testUserId,
        name: 'Test Token',
        scopes: ['accounts:read'],
      });

      const json = entity.toJSON();

      expect(json['expiresAt']).toBeNull();
      expect(json['lastUsedAt']).toBeNull();
      expect(json['revokedAt']).toBeNull();
    });
  });

  describe('fromPersistence', () => {
    it('should reconstitute token from persistence data', () => {
      const now = new Date();
      const lastUsed = new Date(now.getTime() - 3600000);
      const tokenHash = Buffer.from('0'.repeat(64), 'hex');

      const token = ApiToken.fromPersistence({
        id: 'token-123' as any,
        userId: testUserId,
        tokenPrefix: 'abcd1234',
        tokenHash,
        name: 'Persisted Token',
        scopes: ['accounts:read', 'accounts:write'] as TokenScope[],
        createdAt: now,
        expiresAt: null,
        lastUsedAt: lastUsed,
        lastUsedIp: '10.0.0.1',
        revokedAt: null,
        revokedReason: null,
        version: 5,
      });

      expect(token.id).toBe('token-123');
      expect(token.userId).toBe(testUserId);
      expect(token.prefix).toBe('abcd1234');
      expect(token.name).toBe('Persisted Token');
      expect(token.scopes).toEqual(['accounts:read', 'accounts:write']);
      expect(token.lastUsedAt).toEqual(lastUsed);
      expect(token.lastUsedIp).toBe('10.0.0.1');
      expect(token.version).toBe(5);
    });
  });

  describe('ALL_TOKEN_SCOPES', () => {
    it('should contain all expected scopes', () => {
      expect(ALL_TOKEN_SCOPES).toContain('accounts:read');
      expect(ALL_TOKEN_SCOPES).toContain('accounts:write');
      expect(ALL_TOKEN_SCOPES).toContain('transactions:read');
      expect(ALL_TOKEN_SCOPES).toContain('deposits:write');
      expect(ALL_TOKEN_SCOPES).toContain('withdrawals:write');
      expect(ALL_TOKEN_SCOPES).toContain('transfers:write');
      expect(ALL_TOKEN_SCOPES).toContain('payment-methods:read');
      expect(ALL_TOKEN_SCOPES).toContain('payment-methods:write');
    });

    it('should have 8 total scopes', () => {
      expect(ALL_TOKEN_SCOPES).toHaveLength(8);
    });
  });
});
