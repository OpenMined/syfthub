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
 * Input for sending a heartbeat.
 */
export interface HeartbeatInput {
  /** Full URL of this space (e.g., "https://myspace.example.com") */
  url: string;
  /** Time-to-live in seconds (1-3600, server caps at 600). Default is 300. */
  ttlSeconds?: number;
}

/**
 * Response from the heartbeat endpoint.
 *
 * The heartbeat mechanism allows SyftAI Spaces to signal their availability
 * to SyftHub. The server returns the effective TTL (which may be capped)
 * and the expiration time.
 */
export interface HeartbeatResponse {
  /** Status of the heartbeat (typically 'ok') */
  readonly status: string;
  /** When the heartbeat was received (ISO 8601 string) */
  readonly receivedAt: Date;
  /** When the heartbeat will expire (ISO 8601 string) */
  readonly expiresAt: Date;
  /** Extracted domain from the URL */
  readonly domain: string;
  /** Effective TTL applied (may be capped by server) */
  readonly ttlSeconds: number;
}
