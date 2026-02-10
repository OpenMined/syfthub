/**
 * API Token Service Port (Input)
 *
 * Defines the interface for API token management operations.
 */

import { ApiToken, TokenScope } from '../../../domain/entities/ApiToken';
import { ApiTokenId, UserId } from '../../../domain/value-objects/Identifiers';

export interface CreateTokenCommand {
  userId: UserId;
  name: string;
  scopes: TokenScope[];
  expiresInDays?: number;
}

export interface CreateTokenResult {
  token: string;  // Full token (shown only once)
  apiToken: ApiToken;
}

export interface UpdateTokenCommand {
  tokenId: ApiTokenId;
  userId: UserId;  // For authorization
  name: string;
}

export interface RevokeTokenCommand {
  tokenId: ApiTokenId;
  userId: UserId;  // For authorization
  reason?: string;
}

export interface ApiTokenService {
  /**
   * Create a new API token
   * @returns The full token (shown only once) and token details
   */
  createToken(command: CreateTokenCommand): Promise<CreateTokenResult>;

  /**
   * List all tokens for a user
   */
  listTokens(userId: UserId): Promise<ApiToken[]>;

  /**
   * Get a specific token by ID
   */
  getToken(tokenId: ApiTokenId, userId: UserId): Promise<ApiToken | null>;

  /**
   * Update token name
   */
  updateToken(command: UpdateTokenCommand): Promise<ApiToken>;

  /**
   * Revoke a token
   */
  revokeToken(command: RevokeTokenCommand): Promise<ApiToken>;

  /**
   * Validate a token string and return the token if valid
   * Also records usage if token is valid
   */
  validateToken(tokenString: string, clientIp: string): Promise<ApiToken | null>;
}
