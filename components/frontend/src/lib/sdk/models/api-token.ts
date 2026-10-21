/**
 * API Token models for managing personal access tokens.
 */

/**
 * Permission scopes for API tokens.
 */
export type APITokenScope = 'read' | 'write' | 'full';

/**
 * API token representation (without the actual token value).
 */
export interface APIToken {
  /** Unique token identifier */
  id: number;
  /** User-friendly label for the token */
  name: string;
  /** First characters of the token for identification (e.g., 'syft_pat_aB3d') */
  tokenPrefix: string;
  /** Permission scopes */
  scopes: readonly APITokenScope[];
  /** Expiration timestamp, null if never expires */
  expiresAt: Date | null;
  /** Last time the token was used for authentication */
  lastUsedAt: Date | null;
  /** IP address from the last authentication */
  lastUsedIp: string | null;
  /** Whether the token is active (not revoked) */
  isActive: boolean;
  /** When the token was created */
  createdAt: Date;
  /** When the token was last updated */
  updatedAt: Date | null;
}

/**
 * Response when creating a new API token.
 * IMPORTANT: The token is only shown ONCE in this response!
 */
export interface APITokenCreateResponse extends APIToken {
  /** The full API token. SAVE THIS NOW - it will not be shown again! */
  token: string;
}

/**
 * Input for creating a new API token.
 */
export interface CreateAPITokenInput {
  /** User-friendly label for the token (e.g., 'CI/CD Pipeline') */
  name: string;
  /** Permission scopes. Defaults to ['full'] if not specified. */
  scopes?: APITokenScope[];
  /** Optional expiration timestamp. Null means never expires. */
  expiresAt?: Date | null;
}

/**
 * Input for updating an API token.
 */
export interface UpdateAPITokenInput {
  /** New name for the token */
  name: string;
}

/**
 * Response for listing API tokens.
 */
export interface APITokenListResponse {
  /** List of API tokens */
  tokens: APIToken[];
  /** Total number of tokens */
  total: number;
}
