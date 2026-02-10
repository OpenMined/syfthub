/**
 * API Token Entity
 *
 * Represents an API token for programmatic access to user accounts.
 * Tokens provide scoped access to resources without interactive JWT authentication.
 */

import { createHash, randomBytes, timingSafeEqual } from 'crypto';
import { ApiTokenId, UserId } from '../value-objects/Identifiers';

/**
 * Available token scopes for API access
 */
export type TokenScope =
  | 'accounts:read'
  | 'accounts:write'
  | 'transactions:read'
  | 'deposits:write'
  | 'withdrawals:write'
  | 'transfers:write'
  | 'payment-methods:read'
  | 'payment-methods:write';

export const ALL_TOKEN_SCOPES: TokenScope[] = [
  'accounts:read',
  'accounts:write',
  'transactions:read',
  'deposits:write',
  'withdrawals:write',
  'transfers:write',
  'payment-methods:read',
  'payment-methods:write',
];

export interface ApiTokenProps {
  id: ApiTokenId;
  userId: UserId;
  tokenPrefix: string;
  tokenHash: Buffer;
  name: string;
  scopes: TokenScope[];
  createdAt: Date;
  expiresAt: Date | null;
  lastUsedAt: Date | null;
  lastUsedIp: string | null;
  revokedAt: Date | null;
  revokedReason: string | null;
  version: number;
}

export interface CreateTokenResult {
  token: string;
  entity: ApiToken;
}

export class ApiToken {
  private constructor(private props: ApiTokenProps) {}

  // Getters
  get id(): ApiTokenId {
    return this.props.id;
  }

  get userId(): UserId {
    return this.props.userId;
  }

  get prefix(): string {
    return this.props.tokenPrefix;
  }

  get tokenHash(): Buffer {
    return this.props.tokenHash;
  }

  get name(): string {
    return this.props.name;
  }

  get scopes(): TokenScope[] {
    return [...this.props.scopes];
  }

  get createdAt(): Date {
    return this.props.createdAt;
  }

  get expiresAt(): Date | null {
    return this.props.expiresAt;
  }

  get lastUsedAt(): Date | null {
    return this.props.lastUsedAt;
  }

  get lastUsedIp(): string | null {
    return this.props.lastUsedIp;
  }

  get revokedAt(): Date | null {
    return this.props.revokedAt;
  }

  get revokedReason(): string | null {
    return this.props.revokedReason;
  }

  get version(): number {
    return this.props.version;
  }

  /**
   * Create a new API token
   * Returns both the full token (to show user once) and the entity (for persistence)
   *
   * Token format: at_<prefix>_<secret>
   * - prefix: 16 hex chars (8 bytes = 2^64 possibilities) for database lookup
   * - secret: 43 base64url chars (32 bytes = 256 bits) for authentication
   *
   * The prefix provides enumeration resistance while allowing efficient database lookups.
   * The full token hash is stored for authentication, never the plaintext.
   */
  static create(params: {
    userId: UserId;
    name: string;
    scopes: TokenScope[];
    expiresAt?: Date;
  }): CreateTokenResult {
    // Generate 16 random hex chars for prefix (8 bytes = 2^64 possibilities)
    // This provides strong enumeration resistance for database lookups
    const prefixBytes = randomBytes(8);
    const tokenPrefix = prefixBytes.toString('hex');

    // Generate 32 random bytes for secret (base64url encoded, ~43 chars)
    const secretBytes = randomBytes(32);
    const secret = secretBytes
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');

    // Full token format: at_<prefix>_<secret>
    const fullToken = `at_${tokenPrefix}_${secret}`;

    // Hash the full token for storage
    const tokenHash = ApiToken.hashToken(fullToken);

    const now = new Date();
    const entity = new ApiToken({
      id: ApiTokenId.generate(),
      userId: params.userId,
      tokenPrefix,
      tokenHash,
      name: params.name,
      scopes: [...params.scopes],
      createdAt: now,
      expiresAt: params.expiresAt ?? null,
      lastUsedAt: null,
      lastUsedIp: null,
      revokedAt: null,
      revokedReason: null,
      version: 1,
    });

    return { token: fullToken, entity };
  }

  /**
   * Hash a token using SHA-256
   */
  static hashToken(token: string): Buffer {
    return createHash('sha256').update(token).digest();
  }

  /**
   * Compare two token hashes in constant time
   */
  static compareHashes(a: Buffer, b: Buffer): boolean {
    if (a.length !== b.length) {
      return false;
    }
    return timingSafeEqual(a, b);
  }

  /**
   * Parse a token string and extract the prefix.
   *
   * Token format: at_<prefix>_<secret>
   * - prefix: 16 hex chars (8 bytes = 2^64 possibilities)
   * - secret: ~43 base64url chars (32 bytes = 256 bits)
   *
   * Note: The secret is base64url encoded and may contain underscores,
   * so we must allow for more than 3 parts when splitting.
   */
  static parseToken(token: string): { valid: boolean; prefix?: string } {
    if (!token.startsWith('at_')) {
      return { valid: false };
    }

    const parts = token.split('_');
    // Must have at least 3 parts: 'at', prefix, and secret (which may contain more underscores)
    if (parts.length < 3) {
      return { valid: false };
    }

    const prefix = parts[1];
    if (!prefix || prefix.length !== 16) {
      return { valid: false };
    }

    // Validate prefix is valid hex
    if (!/^[0-9a-f]+$/i.test(prefix)) {
      return { valid: false };
    }

    return { valid: true, prefix };
  }

  /**
   * Reconstitute from persistence
   */
  static fromPersistence(props: ApiTokenProps): ApiToken {
    return new ApiToken(props);
  }

  /**
   * Check if the token is valid (not revoked and not expired)
   */
  isValid(): boolean {
    if (this.props.revokedAt !== null) {
      return false;
    }

    if (this.props.expiresAt !== null && this.props.expiresAt < new Date()) {
      return false;
    }

    return true;
  }

  /**
   * Check if the token has expired
   */
  isExpired(): boolean {
    return this.props.expiresAt !== null && this.props.expiresAt < new Date();
  }

  /**
   * Check if the token is revoked
   */
  isRevoked(): boolean {
    return this.props.revokedAt !== null;
  }

  /**
   * Check if the token has a specific scope
   */
  hasScope(scope: TokenScope): boolean {
    return this.props.scopes.includes(scope);
  }

  /**
   * Check if the token has all of the specified scopes
   */
  hasAllScopes(scopes: TokenScope[]): boolean {
    return scopes.every((scope) => this.hasScope(scope));
  }

  /**
   * Record token usage
   */
  recordUsage(ip: string): void {
    this.props.lastUsedAt = new Date();
    this.props.lastUsedIp = ip;
    this.props.version++;
  }

  /**
   * Revoke the token
   */
  revoke(reason?: string): void {
    if (this.props.revokedAt !== null) {
      return; // Already revoked
    }
    this.props.revokedAt = new Date();
    this.props.revokedReason = reason ?? null;
    this.props.version++;
  }

  /**
   * Update the token name
   */
  updateName(name: string): void {
    if (name.length < 1 || name.length > 100) {
      throw new Error('Token name must be between 1 and 100 characters');
    }
    this.props.name = name;
    this.props.version++;
  }

  /**
   * Convert to plain object for serialization (excludes sensitive data)
   */
  toJSON(): Record<string, unknown> {
    return {
      id: this.props.id,
      userId: this.props.userId,
      prefix: this.props.tokenPrefix,
      name: this.props.name,
      scopes: this.props.scopes,
      createdAt: this.props.createdAt.toISOString(),
      expiresAt: this.props.expiresAt?.toISOString() ?? null,
      lastUsedAt: this.props.lastUsedAt?.toISOString() ?? null,
      revokedAt: this.props.revokedAt?.toISOString() ?? null,
      version: this.props.version,
    };
  }
}
