/**
 * ManageApiTokens Use Case Unit Tests
 *
 * Tests the API token management use case with mocked repository.
 */

import {
  ManageApiTokensUseCase,
  TooManyTokensError,
  TokenAuthorizationError,
} from '../../../src/application/use-cases/ManageApiTokens';
import { ApiToken, TokenScope } from '../../../src/domain/entities/ApiToken';
import { ApiTokenRepository } from '../../../src/application/ports/output/ApiTokenRepository';
import { TokenNotFoundError, InvalidTokenError } from '../../../src/domain/errors';
import { ApiTokenId, UserId } from '../../../src/domain/value-objects/Identifiers';

describe('ManageApiTokensUseCase', () => {
  let useCase: ManageApiTokensUseCase;
  let mockRepository: jest.Mocked<ApiTokenRepository>;
  const testUserId = UserId.from('user-123');
  const otherUserId = UserId.from('user-456');

  beforeEach(() => {
    mockRepository = {
      findById: jest.fn(),
      findByHash: jest.fn(),
      findByUserId: jest.fn(),
      save: jest.fn(),
      update: jest.fn(),
      countByUserId: jest.fn(),
    };

    useCase = new ManageApiTokensUseCase(mockRepository, { maxTokensPerUser: 25 });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('createToken', () => {
    it('should create a new token successfully', async () => {
      mockRepository.countByUserId.mockResolvedValue(0);
      mockRepository.save.mockResolvedValue();

      const result = await useCase.createToken({
        userId: testUserId,
        name: 'My API Token',
        scopes: ['accounts:read', 'transactions:read'],
      });

      expect(result.token).toMatch(/^at_[a-f0-9]{8}_[A-Za-z0-9_-]+$/);
      expect(result.apiToken.userId).toBe(testUserId);
      expect(result.apiToken.name).toBe('My API Token');
      expect(result.apiToken.scopes).toEqual(['accounts:read', 'transactions:read']);

      expect(mockRepository.save).toHaveBeenCalledTimes(1);
      expect(mockRepository.save).toHaveBeenCalledWith(result.apiToken);
    });

    it('should create a token with expiration', async () => {
      mockRepository.countByUserId.mockResolvedValue(0);
      mockRepository.save.mockResolvedValue();

      const result = await useCase.createToken({
        userId: testUserId,
        name: 'Expiring Token',
        scopes: ['accounts:read'],
        expiresInDays: 30,
      });

      expect(result.apiToken.expiresAt).toBeInstanceOf(Date);
      const expectedExpiry = new Date();
      expectedExpiry.setDate(expectedExpiry.getDate() + 30);
      // Allow 1 second tolerance
      expect(Math.abs(result.apiToken.expiresAt!.getTime() - expectedExpiry.getTime())).toBeLessThan(1000);
    });

    it('should throw TooManyTokensError when limit reached', async () => {
      mockRepository.countByUserId.mockResolvedValue(25);

      await expect(
        useCase.createToken({
          userId: testUserId,
          name: 'One Too Many',
          scopes: ['accounts:read'],
        })
      ).rejects.toThrow(TooManyTokensError);

      expect(mockRepository.save).not.toHaveBeenCalled();
    });

    it('should respect custom token limit', async () => {
      const customUseCase = new ManageApiTokensUseCase(mockRepository, { maxTokensPerUser: 5 });
      mockRepository.countByUserId.mockResolvedValue(5);

      await expect(
        customUseCase.createToken({
          userId: testUserId,
          name: 'Exceeds Custom Limit',
          scopes: ['accounts:read'],
        })
      ).rejects.toThrow('Maximum number of tokens (5) reached');
    });

    it('should not create expiring token when expiresInDays is 0', async () => {
      mockRepository.countByUserId.mockResolvedValue(0);
      mockRepository.save.mockResolvedValue();

      const result = await useCase.createToken({
        userId: testUserId,
        name: 'Non-expiring Token',
        scopes: ['accounts:read'],
        expiresInDays: 0,
      });

      expect(result.apiToken.expiresAt).toBeNull();
    });
  });

  describe('listTokens', () => {
    it('should return all tokens for a user', async () => {
      const tokens = [
        createMockToken(testUserId, 'Token 1'),
        createMockToken(testUserId, 'Token 2'),
      ];
      mockRepository.findByUserId.mockResolvedValue(tokens);

      const result = await useCase.listTokens(testUserId);

      expect(result).toHaveLength(2);
      expect(result[0]!.name).toBe('Token 1');
      expect(result[1]!.name).toBe('Token 2');
      expect(mockRepository.findByUserId).toHaveBeenCalledWith(testUserId);
    });

    it('should return empty array when user has no tokens', async () => {
      mockRepository.findByUserId.mockResolvedValue([]);

      const result = await useCase.listTokens(testUserId);

      expect(result).toEqual([]);
    });
  });

  describe('getToken', () => {
    it('should return token when found and owned by user', async () => {
      const token = createMockToken(testUserId, 'My Token');
      mockRepository.findById.mockResolvedValue(token);

      const result = await useCase.getToken(token.id, testUserId);

      expect(result).toBe(token);
      expect(mockRepository.findById).toHaveBeenCalledWith(token.id);
    });

    it('should return null when token not found', async () => {
      mockRepository.findById.mockResolvedValue(null);

      const result = await useCase.getToken(ApiTokenId.from('nonexistent'), testUserId);

      expect(result).toBeNull();
    });

    it('should throw TokenAuthorizationError when token belongs to different user', async () => {
      const token = createMockToken(otherUserId, 'Other User Token');
      mockRepository.findById.mockResolvedValue(token);

      await expect(
        useCase.getToken(token.id, testUserId)
      ).rejects.toThrow(TokenAuthorizationError);
    });
  });

  describe('updateToken', () => {
    it('should update token name successfully', async () => {
      const token = createMockToken(testUserId, 'Old Name');
      mockRepository.findById.mockResolvedValue(token);
      mockRepository.update.mockResolvedValue();

      const result = await useCase.updateToken({
        tokenId: token.id,
        userId: testUserId,
        name: 'New Name',
      });

      expect(result.name).toBe('New Name');
      expect(mockRepository.update).toHaveBeenCalledTimes(1);
    });

    it('should throw TokenNotFoundError when token does not exist', async () => {
      mockRepository.findById.mockResolvedValue(null);

      await expect(
        useCase.updateToken({
          tokenId: ApiTokenId.from('nonexistent'),
          userId: testUserId,
          name: 'New Name',
        })
      ).rejects.toThrow(TokenNotFoundError);
    });

    it('should throw TokenAuthorizationError when token belongs to different user', async () => {
      const token = createMockToken(otherUserId, 'Other Token');
      mockRepository.findById.mockResolvedValue(token);

      await expect(
        useCase.updateToken({
          tokenId: token.id,
          userId: testUserId,
          name: 'New Name',
        })
      ).rejects.toThrow(TokenAuthorizationError);
    });

    it('should throw InvalidTokenError when trying to update revoked token', async () => {
      const token = createMockToken(testUserId, 'Revoked Token');
      token.revoke('Test revocation');
      mockRepository.findById.mockResolvedValue(token);

      await expect(
        useCase.updateToken({
          tokenId: token.id,
          userId: testUserId,
          name: 'New Name',
        })
      ).rejects.toThrow(InvalidTokenError);
    });
  });

  describe('revokeToken', () => {
    it('should revoke token successfully', async () => {
      const token = createMockToken(testUserId, 'Token to Revoke');
      mockRepository.findById.mockResolvedValue(token);
      mockRepository.update.mockResolvedValue();

      const result = await useCase.revokeToken({
        tokenId: token.id,
        userId: testUserId,
        reason: 'No longer needed',
      });

      expect(result.isRevoked()).toBe(true);
      expect(result.revokedReason).toBe('No longer needed');
      expect(mockRepository.update).toHaveBeenCalledTimes(1);
    });

    it('should revoke token without reason', async () => {
      const token = createMockToken(testUserId, 'Token to Revoke');
      mockRepository.findById.mockResolvedValue(token);
      mockRepository.update.mockResolvedValue();

      const result = await useCase.revokeToken({
        tokenId: token.id,
        userId: testUserId,
      });

      expect(result.isRevoked()).toBe(true);
      expect(result.revokedReason).toBeNull();
    });

    it('should be idempotent - revoking already revoked token returns it', async () => {
      const token = createMockToken(testUserId, 'Already Revoked');
      token.revoke('Already revoked');
      mockRepository.findById.mockResolvedValue(token);

      const result = await useCase.revokeToken({
        tokenId: token.id,
        userId: testUserId,
      });

      expect(result.isRevoked()).toBe(true);
      expect(mockRepository.update).not.toHaveBeenCalled();
    });

    it('should throw TokenNotFoundError when token does not exist', async () => {
      mockRepository.findById.mockResolvedValue(null);

      await expect(
        useCase.revokeToken({
          tokenId: ApiTokenId.from('nonexistent'),
          userId: testUserId,
        })
      ).rejects.toThrow(TokenNotFoundError);
    });

    it('should throw TokenAuthorizationError when token belongs to different user', async () => {
      const token = createMockToken(otherUserId, 'Other Token');
      mockRepository.findById.mockResolvedValue(token);

      await expect(
        useCase.revokeToken({
          tokenId: token.id,
          userId: testUserId,
        })
      ).rejects.toThrow(TokenAuthorizationError);
    });
  });

  describe('validateToken', () => {
    it('should validate and return valid token', async () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Token',
        scopes: ['accounts:read'],
      });
      mockRepository.findByHash.mockResolvedValue(entity);
      mockRepository.update.mockResolvedValue();

      const result = await useCase.validateToken(token, '192.168.1.1');

      expect(result).not.toBeNull();
      expect(result!.userId).toBe(testUserId);
      expect(result!.lastUsedIp).toBe('192.168.1.1');
    });

    it('should return null for malformed token', async () => {
      const result = await useCase.validateToken('invalid-token-format', '127.0.0.1');

      expect(result).toBeNull();
      expect(mockRepository.findByHash).not.toHaveBeenCalled();
    });

    it('should return null when token not found', async () => {
      mockRepository.findByHash.mockResolvedValue(null);

      const result = await useCase.validateToken('at_12345678_validsecretpart', '127.0.0.1');

      expect(result).toBeNull();
    });

    it('should return null for expired token', async () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Expired Token',
        scopes: ['accounts:read'],
        expiresAt: new Date(Date.now() - 1000), // Expired
      });
      mockRepository.findByHash.mockResolvedValue(entity);

      const result = await useCase.validateToken(token, '127.0.0.1');

      expect(result).toBeNull();
    });

    it('should return null for revoked token', async () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Revoked Token',
        scopes: ['accounts:read'],
      });
      entity.revoke('Test');
      mockRepository.findByHash.mockResolvedValue(entity);

      const result = await useCase.validateToken(token, '127.0.0.1');

      expect(result).toBeNull();
    });

    it('should record usage for valid token', async () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Token',
        scopes: ['accounts:read'],
      });
      mockRepository.findByHash.mockResolvedValue(entity);
      mockRepository.update.mockResolvedValue();

      await useCase.validateToken(token, '10.0.0.1');

      // Allow async update to be called
      await new Promise(resolve => setTimeout(resolve, 10));

      expect(mockRepository.update).toHaveBeenCalled();
    });

    it('should not fail if usage update fails', async () => {
      const { token, entity } = ApiToken.create({
        userId: testUserId,
        name: 'Valid Token',
        scopes: ['accounts:read'],
      });
      mockRepository.findByHash.mockResolvedValue(entity);
      mockRepository.update.mockRejectedValue(new Error('DB error'));

      // Should not throw
      const result = await useCase.validateToken(token, '127.0.0.1');

      expect(result).not.toBeNull();
    });
  });
});

// Helper function to create mock tokens
function createMockToken(userId: UserId, name: string): ApiToken {
  const { entity } = ApiToken.create({
    userId,
    name,
    scopes: ['accounts:read'] as TokenScope[],
  });
  return entity;
}
