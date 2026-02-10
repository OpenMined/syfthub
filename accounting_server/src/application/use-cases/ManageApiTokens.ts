/**
 * Manage API Tokens Use Case
 *
 * Handles CRUD operations for API tokens.
 * Implements the ApiTokenService input port.
 */

import { ApiToken } from '../../domain/entities/ApiToken';
import { TokenNotFoundError, InvalidTokenError } from '../../domain/errors';
import {
  ApiTokenService,
  CreateTokenCommand,
  CreateTokenResult,
  UpdateTokenCommand,
  RevokeTokenCommand,
} from '../ports/input/ApiTokenService';
import { ApiTokenRepository } from '../ports/output/ApiTokenRepository';
import { ApiTokenId, UserId } from '../../domain/value-objects/Identifiers';

export interface ManageApiTokensConfig {
  /** Maximum number of tokens per user (default: 25) */
  maxTokensPerUser?: number;
}

export class TooManyTokensError extends Error {
  constructor(maxTokens: number) {
    super(`Maximum number of tokens (${maxTokens}) reached. Please revoke unused tokens.`);
    this.name = 'TooManyTokensError';
  }
}

export class TokenAuthorizationError extends Error {
  constructor(message: string = 'Not authorized to access this token') {
    super(message);
    this.name = 'TokenAuthorizationError';
  }
}

export class ManageApiTokensUseCase implements ApiTokenService {
  private readonly maxTokensPerUser: number;

  constructor(
    private apiTokenRepository: ApiTokenRepository,
    config?: ManageApiTokensConfig
  ) {
    this.maxTokensPerUser = config?.maxTokensPerUser ?? 25;
  }

  async createToken(command: CreateTokenCommand): Promise<CreateTokenResult> {
    // Check token limit
    const currentCount = await this.apiTokenRepository.countByUserId(command.userId);
    if (currentCount >= this.maxTokensPerUser) {
      throw new TooManyTokensError(this.maxTokensPerUser);
    }

    // Calculate expiration date if specified
    let expiresAt: Date | undefined;
    if (command.expiresInDays !== undefined && command.expiresInDays > 0) {
      expiresAt = new Date();
      expiresAt.setDate(expiresAt.getDate() + command.expiresInDays);
    }

    // Create the token
    const createParams: Parameters<typeof ApiToken.create>[0] = {
      userId: command.userId,
      name: command.name,
      scopes: command.scopes,
    };
    if (expiresAt !== undefined) {
      createParams.expiresAt = expiresAt;
    }
    const { token, entity } = ApiToken.create(createParams);

    // Save to repository
    await this.apiTokenRepository.save(entity);

    return {
      token,
      apiToken: entity,
    };
  }

  async listTokens(userId: UserId): Promise<ApiToken[]> {
    return this.apiTokenRepository.findByUserId(userId);
  }

  async getToken(tokenId: ApiTokenId, userId: UserId): Promise<ApiToken | null> {
    const token = await this.apiTokenRepository.findById(tokenId);

    if (!token) {
      return null;
    }

    // Authorization check
    if (token.userId !== userId) {
      throw new TokenAuthorizationError();
    }

    return token;
  }

  async updateToken(command: UpdateTokenCommand): Promise<ApiToken> {
    const token = await this.apiTokenRepository.findById(command.tokenId);

    if (!token) {
      throw new TokenNotFoundError(command.tokenId);
    }

    // Authorization check
    if (token.userId !== command.userId) {
      throw new TokenAuthorizationError();
    }

    // Cannot update revoked tokens
    if (token.isRevoked()) {
      throw new InvalidTokenError('revoked', 'Cannot update a revoked token');
    }

    // Update the name
    token.updateName(command.name);

    // Save changes
    await this.apiTokenRepository.update(token);

    return token;
  }

  async revokeToken(command: RevokeTokenCommand): Promise<ApiToken> {
    const token = await this.apiTokenRepository.findById(command.tokenId);

    if (!token) {
      throw new TokenNotFoundError(command.tokenId);
    }

    // Authorization check
    if (token.userId !== command.userId) {
      throw new TokenAuthorizationError();
    }

    // Idempotent: if already revoked, just return it
    if (token.isRevoked()) {
      return token;
    }

    // Revoke the token
    token.revoke(command.reason);

    // Save changes
    await this.apiTokenRepository.update(token);

    return token;
  }

  async validateToken(tokenString: string, clientIp: string): Promise<ApiToken | null> {
    // Parse and validate token format
    const parsed = ApiToken.parseToken(tokenString);
    if (!parsed.valid) {
      return null;
    }

    // Hash the token and look it up
    const hash = ApiToken.hashToken(tokenString);
    const token = await this.apiTokenRepository.findByHash(hash);

    if (!token) {
      return null;
    }

    // Check if token is valid (not expired, not revoked)
    if (!token.isValid()) {
      return null;
    }

    // Record usage
    token.recordUsage(clientIp);

    // Update last used timestamp (fire and forget, don't block the request)
    this.apiTokenRepository.update(token).catch((err) => {
      console.error('Failed to update token usage:', err);
    });

    return token;
  }
}
