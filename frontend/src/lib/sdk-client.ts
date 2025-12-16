// ============================================================================
// User Profile Utilities
// ============================================================================

import type {
  AvailabilityResponse,
  User as FrontendUser,
  PasswordChange,
  UserUpdate
} from './types';

import { SyftHubClient } from '@syfthub/sdk';

/**
 * SyftHub SDK Client Configuration
 *
 * This module provides:
 * - Configured SyftHubClient singleton instance
 * - Token persistence helpers for localStorage
 * - Utilities for session management
 */

// Storage keys for tokens (compatible with existing frontend storage)
const ACCESS_TOKEN_KEY = 'syft_access_token';
const REFRESH_TOKEN_KEY = 'syft_refresh_token';

/**
 * Get the base URL for the SDK client.
 *
 * The SDK expects the base URL WITHOUT the `/api/v1` suffix (it adds that internally).
 *
 * - For same-origin (VITE_API_URL empty or '/api/v1'): return undefined to use same-origin
 * - For direct backend (VITE_API_URL = 'http://localhost:8000/api/v1'): strip suffix
 */
function getBaseUrl(): string | undefined {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;

  // If not set or is the proxy path, use same-origin (undefined lets SDK use same-origin in browser)
  if (!envUrl || envUrl === '/api/v1') {
    return undefined;
  }

  // If it has /api/v1 suffix, strip it
  if (envUrl.endsWith('/api/v1')) {
    return envUrl.slice(0, -7); // Remove '/api/v1'
  }

  if (envUrl.endsWith('/api/v1/')) {
    return envUrl.slice(0, -8); // Remove '/api/v1/'
  }

  // Otherwise use as-is
  return envUrl;
}

/**
 * Singleton SyftHub client instance.
 *
 * Use this throughout the application for all API calls.
 *
 * @example
 * import { syftClient } from '@/lib/sdk-client';
 *
 * // Login
 * const user = await syftClient.auth.login(email, password);
 *
 * // Browse endpoints
 * for await (const ep of syftClient.hub.browse()) {
 *   console.log(ep.name);
 * }
 */
export const syftClient = new SyftHubClient({
  baseUrl: getBaseUrl(),
  timeout: 30_000
});

/**
 * Persist SDK tokens to localStorage.
 *
 * Call this after successful login/register to save tokens for future sessions.
 *
 * @returns true if tokens were persisted, false if no tokens to persist
 */
export function persistTokens(): boolean {
  const tokens = syftClient.getTokens();
  if (!tokens) {
    return false;
  }

  try {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
    return true;
  } catch (error) {
    console.error('Failed to persist tokens:', error);
    return false;
  }
}

/**
 * Restore tokens from localStorage to SDK client.
 *
 * Call this on app initialization to restore previous session.
 *
 * @returns true if tokens were restored, false if no saved tokens
 */
export function restoreTokens(): boolean {
  try {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);

    if (accessToken && refreshToken) {
      syftClient.setTokens({
        accessToken,
        refreshToken,
        tokenType: 'bearer'
      });
      return true;
    }
  } catch (error) {
    console.error('Failed to restore tokens:', error);
  }
  return false;
}

/**
 * Clear persisted tokens from localStorage.
 *
 * Call this on logout or when tokens are invalid.
 */
export function clearPersistedTokens(): void {
  try {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch (error) {
    console.error('Failed to clear tokens:', error);
  }
}

/**
 * Check if there are persisted tokens in localStorage.
 *
 * This doesn't validate the tokens, just checks if they exist.
 */
export function hasPersistedTokens(): boolean {
  try {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    return accessToken !== null;
  } catch {
    return false;
  }
}

// Re-export commonly used SDK types for convenience
export type { AuthTokens } from '@syfthub/sdk';
export {
  // Error types
  SyftHubError,
  APIError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  NetworkError,
  // Chat-specific errors
  AggregatorError,
  EndpointResolutionError,
  // Accounting-related errors
  AccountingAccountExistsError,
  InvalidAccountingPasswordError,
  AccountingServiceUnavailableError,
  // Enums
  Visibility,
  EndpointType,
  UserRole
} from '@syfthub/sdk';

// Re-export model types
export type {
  User,
  Endpoint,
  EndpointPublic,
  EndpointCreateInput,
  EndpointUpdateInput,
  Policy,
  Connection,
  UserUpdateInput,
  PasswordChangeInput
} from '@syfthub/sdk';

// Re-export chat types for frontend usage
export type {
  // Chat options and response
  ChatOptions,
  ChatResponse,
  ChatMetadata,
  // Endpoint reference
  EndpointRef,
  // Source information
  SourceInfo,
  SourceStatus,
  // Streaming event types
  ChatStreamEvent,
  RetrievalStartEvent,
  SourceCompleteEvent,
  RetrievalCompleteEvent,
  GenerationStartEvent,
  TokenEvent,
  DoneEvent,
  ErrorEvent
} from '@syfthub/sdk';

/**
 * Change the current user's password.
 *
 * @param passwordData - Current and new password
 */
export async function changePasswordAPI(passwordData: PasswordChange): Promise<void> {
  await syftClient.auth.changePassword(passwordData.current_password, passwordData.new_password);
}

/**
 * Generate a placeholder avatar URL from a name.
 */
function generateAvatarUrl(name: string): string {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=272532&color=fff`;
}

/**
 * Update the current user's profile.
 *
 * @param profileData - Fields to update
 * @returns Updated user in frontend User format
 */
export async function updateUserProfileAPI(profileData: UserUpdate): Promise<FrontendUser> {
  const sdkUser = await syftClient.users.update({
    username: profileData.username,
    email: profileData.email,
    fullName: profileData.full_name,
    avatarUrl: profileData.avatar_url
  });

  // Convert SDK User to frontend User format
  return {
    id: String(sdkUser.id),
    username: sdkUser.username,
    email: sdkUser.email,
    name: sdkUser.fullName,
    full_name: sdkUser.fullName,
    avatar_url: sdkUser.avatarUrl ?? generateAvatarUrl(sdkUser.fullName),
    role: sdkUser.role,
    is_active: sdkUser.isActive,
    created_at: sdkUser.createdAt.toISOString(),
    updated_at: sdkUser.updatedAt?.toISOString() ?? sdkUser.createdAt.toISOString()
  };
}

/**
 * Check if a username is available.
 *
 * @param username - Username to check
 * @returns Availability response
 */
export async function checkUsernameAvailability(username: string): Promise<AvailabilityResponse> {
  const available = await syftClient.users.checkUsername(username);
  return { available, username };
}

/**
 * Check if an email is available.
 *
 * @param email - Email to check
 * @returns Availability response
 */
export async function checkEmailAvailability(email: string): Promise<AvailabilityResponse> {
  const available = await syftClient.users.checkEmail(email);
  return { available, email };
}

/**
 * Delete the current user's account.
 *
 * Note: This function uses direct fetch since the SDK doesn't provide this method.
 */
export async function deleteUserAccountAPI(): Promise<void> {
  // First get the current user to get their ID
  const user = await syftClient.auth.me();

  // Get base URL for API call (empty string for same-origin)
  const baseUrl = getBaseUrl() ?? '';

  // Get the access token
  const tokens = syftClient.getTokens();
  if (!tokens) {
    throw new Error('Not authenticated');
  }

  // Make the delete request
  const response = await fetch(`${baseUrl}/api/v1/users/${String(user.id)}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${tokens.accessToken}`
    }
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to delete account' }));
    throw new Error((errorData as { detail?: string }).detail ?? 'Failed to delete account');
  }

  // Clear tokens after successful deletion
  clearPersistedTokens();
}
