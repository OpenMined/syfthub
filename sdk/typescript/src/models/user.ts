import type { UserRole } from './common.js';

/**
 * User account information.
 */
export interface User {
  readonly id: number;
  readonly username: string;
  readonly email: string;
  readonly fullName: string;
  readonly avatarUrl: string | null;
  readonly role: UserRole;
  readonly isActive: boolean;
  readonly createdAt: Date;
  readonly updatedAt: Date | null;
  /** Domain for endpoint URL construction (e.g., "api.example.com" or "api.example.com:8080") */
  readonly domain: string | null;
  /** Custom aggregator URL for RAG/chat workflows */
  readonly aggregatorUrl: string | null;
}

/**
 * Authentication tokens returned from login/register.
 */
export interface AuthTokens {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly tokenType: string;
}

/**
 * Input for user registration.
 */
export interface UserRegisterInput {
  username: string;
  email: string;
  password: string;
  fullName: string;
  /** Optional accounting service URL (can be set up later in settings) */
  accountingServiceUrl?: string;
  /**
   * Optional password for the accounting service account.
   *
   * The backend uses a "try-create-first" approach:
   * - **If provided (new user)**: Creates a new accounting account with this password.
   * - **If provided (existing user)**: Validates against the existing account and links it.
   * - **If not provided**: Auto-generates a secure password for a new account.
   *
   * This means you can set your own accounting password during registration
   * without needing an existing accounting account.
   */
  accountingPassword?: string;
}

/**
 * Input for updating user profile.
 */
export interface UserUpdateInput {
  username?: string;
  email?: string;
  fullName?: string;
  avatarUrl?: string;
  /** Domain for endpoint URL construction (no protocol, e.g., "api.example.com:8080") */
  domain?: string;
  /** Custom aggregator URL for RAG/chat workflows */
  aggregatorUrl?: string;
}

/**
 * Input for changing password.
 */
export interface PasswordChangeInput {
  currentPassword: string;
  newPassword: string;
}

/**
 * Credentials for connecting to an external accounting service.
 * These are stored in the SyftHub backend and fetched via API.
 */
export interface AccountingCredentials {
  /** URL of the accounting service API (null if not configured) */
  readonly url: string | null;
  /** Email for authenticating with the accounting service (same as SyftHub email) */
  readonly email: string;
  /** Password for authenticating with the accounting service (null if not configured) */
  readonly password: string | null;
}

/**
 * A user's aggregator configuration.
 *
 * Aggregators are custom RAG orchestration service endpoints that users can
 * configure to use for chat operations. Each user can have multiple aggregator
 * configurations, with one set as the default.
 */
export interface UserAggregator {
  /** Unique aggregator configuration ID */
  readonly id: number;
  /** Owner user ID */
  readonly userId: number;
  /** Display name for the aggregator */
  readonly name: string;
  /** Aggregator service URL */
  readonly url: string;
  /** Whether this is the user's default aggregator */
  readonly isDefault: boolean;
  /** When the aggregator was created */
  readonly createdAt: Date;
  /** When the aggregator was last updated */
  readonly updatedAt: Date;
}

/**
 * Input for creating an aggregator configuration.
 */
export interface UserAggregatorCreateInput {
  /** Display name for the aggregator */
  name: string;
  /** Aggregator service URL */
  url: string;
}

/**
 * Input for updating an aggregator configuration.
 */
export interface UserAggregatorUpdateInput {
  /** New display name (optional) */
  name?: string;
  /** New aggregator URL (optional) */
  url?: string;
}
