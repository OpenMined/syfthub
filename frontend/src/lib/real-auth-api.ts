/**
 * Real Authentication API - Replaces mock auth-api.ts
 * Integrates with SyftHub FastAPI backend
 */

import type {
  AuthResponse,
  AvailabilityResponse,
  BackendUser,
  PasswordChange,
  RegisterRequest,
  RegistrationResponse,
  User,
  UserResponse,
  UserUpdate
} from './types';

import { API_CONFIG, apiClient, APIError, tokenManager } from './api-client';

// Token response type from login
interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

// Utility function to convert backend user to frontend user
export function mapBackendUserToFrontend(backendUser: BackendUser): User {
  return {
    id: backendUser.id.toString(), // Convert number to string for frontend
    username: backendUser.username,
    email: backendUser.email,
    name: backendUser.full_name, // Map full_name to name for frontend
    full_name: backendUser.full_name,
    role: backendUser.role,
    // Use avatar_url from backend or generate fallback
    avatar_url: backendUser.avatar_url ?? generateAvatarUrl(backendUser.full_name),
    is_active: backendUser.is_active,
    created_at: backendUser.created_at,
    updated_at: backendUser.updated_at
  };
}

// Generate avatar URL from name (similar to mock implementation)
function generateAvatarUrl(name: string): string {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=272532&color=fff`;
}

// Login API
export async function loginAPI(credentials: {
  email: string;
  password: string;
}): Promise<AuthResponse> {
  // Backend expects OAuth2PasswordRequestForm which uses username field
  // We'll use email as username for now, or implement username lookup
  const loginData = new URLSearchParams();
  loginData.append('username', credentials.email); // Use email as username
  loginData.append('password', credentials.password);

  const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS.AUTH.LOGIN}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: loginData
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
    throw new APIError(
      (errorData as { detail?: string }).detail ?? 'Invalid email or password',
      response.status,
      errorData
    );
  }

  const tokenData = (await response.json()) as TokenResponse;

  // Get user info after successful login
  tokenManager.setTokens(tokenData.access_token, tokenData.refresh_token);

  try {
    const userResponse = await apiClient.get<UserResponse>(API_CONFIG.ENDPOINTS.AUTH.ME);

    return {
      user: userResponse as BackendUser, // UserResponse is subset of BackendUser
      access_token: tokenData.access_token,
      refresh_token: tokenData.refresh_token,
      token_type: tokenData.token_type ?? 'bearer'
    };
  } catch {
    // Clear tokens if we can't get user info
    tokenManager.clearTokens();
    throw new APIError('Failed to get user information', 500);
  }
}

// Register API
export async function registerAPI(userData: {
  name: string;
  email: string;
  password: string;
}): Promise<RegistrationResponse> {
  // Generate username from email (before @)
  const emailPrefix = userData.email.split('@')[0];
  const baseUsername = emailPrefix
    ? emailPrefix.toLowerCase().replaceAll(/[^a-z0-9]/g, '')
    : 'user';
  let username = baseUsername;
  let attempts = 0;
  const maxAttempts = 5;

  // Try registration with increasing suffixes if username exists
  while (attempts < maxAttempts) {
    const registerData: RegisterRequest = {
      username: username,
      email: userData.email,
      full_name: userData.name,
      password: userData.password
    };

    try {
      const response = await apiClient.post<RegistrationResponse>(
        API_CONFIG.ENDPOINTS.AUTH.REGISTER,
        registerData,
        false // Don't require auth for registration
      );

      // Store tokens from registration response
      tokenManager.setTokens(response.access_token, response.refresh_token);

      return response;
    } catch (error) {
      // If username already exists, try with a random suffix
      if (
        error instanceof APIError &&
        (error.message.toLowerCase().includes('username already exists') ||
          error.message.toLowerCase().includes('username already registered') ||
          error.message.toLowerCase().includes('already exists'))
      ) {
        attempts++;
        if (attempts < maxAttempts) {
          // Add random 3-digit number to username
          const randomSuffix = Math.floor(Math.random() * 900) + 100; // NOSONAR - not security-sensitive
          username = `${baseUsername}${String(randomSuffix)}`;
          // Username already taken, trying new one with random suffix
          continue;
        }
      }
      // For other errors, throw immediately
      console.error('Registration error:', error);
      throw error;
    }
  }

  // If we exhausted all attempts
  throw new APIError(
    'Username already taken. Please try a different email or contact support.',
    400
  );
}

// Google OAuth API (keeping mock for now - can implement later)
export async function googleOAuthAPI(_request: { token: string }): Promise<AuthResponse> {
  // For now, return a mock implementation
  await new Promise((resolve) => setTimeout(resolve, 600)); // Simulate delay

  throw new APIError('Google OAuth not yet implemented', 501);
}

// GitHub OAuth API (keeping mock for now - can implement later)
export async function githubOAuthAPI(_request: { code: string }): Promise<AuthResponse> {
  // For now, return a mock implementation
  await new Promise((resolve) => setTimeout(resolve, 600)); // Simulate delay

  throw new APIError('GitHub OAuth not yet implemented', 501);
}

// Logout API
export async function logoutAPI(_token: string): Promise<{ success: boolean }> {
  try {
    await apiClient.post(API_CONFIG.ENDPOINTS.AUTH.LOGOUT, {});
    tokenManager.clearTokens();
    return { success: true };
  } catch {
    // Even if logout fails on server, clear local tokens
    tokenManager.clearTokens();
    return { success: true };
  }
}

// Refresh token API
export async function refreshTokenAPI(
  refreshToken: string
): Promise<{ token: string; refresh_token?: string }> {
  try {
    const response = await apiClient.post<{ access_token: string; refresh_token: string }>(
      API_CONFIG.ENDPOINTS.AUTH.REFRESH,
      { refresh_token: refreshToken },
      false // Don't require auth for refresh
    );

    tokenManager.setTokens(response.access_token, response.refresh_token);

    return {
      token: response.access_token,
      refresh_token: response.refresh_token
    };
  } catch (error) {
    tokenManager.clearTokens();
    throw error;
  }
}

// Get current user info
export async function getCurrentUserAPI(): Promise<UserResponse> {
  return await apiClient.get<UserResponse>(API_CONFIG.ENDPOINTS.AUTH.ME);
}

// Change password API
export async function changePasswordAPI(passwordData: PasswordChange): Promise<void> {
  await apiClient.put<null>(API_CONFIG.ENDPOINTS.AUTH.CHANGE_PASSWORD, passwordData);
}

// Update user profile API
export async function updateUserProfileAPI(profileData: UserUpdate): Promise<UserResponse> {
  return await apiClient.put<UserResponse>(API_CONFIG.ENDPOINTS.USERS.ME, profileData);
}

// Check username availability
export async function checkUsernameAvailability(username: string): Promise<AvailabilityResponse> {
  const response = await fetch(
    `${API_CONFIG.BASE_URL}/users/check-username/${encodeURIComponent(username)}`,
    { method: 'GET' }
  );

  if (!response.ok) {
    throw new APIError('Failed to check username availability', response.status);
  }

  return (await response.json()) as AvailabilityResponse;
}

// Check email availability
export async function checkEmailAvailability(email: string): Promise<AvailabilityResponse> {
  const response = await fetch(
    `${API_CONFIG.BASE_URL}/users/check-email/${encodeURIComponent(email)}`,
    { method: 'GET' }
  );

  if (!response.ok) {
    throw new APIError('Failed to check email availability', response.status);
  }

  return (await response.json()) as AvailabilityResponse;
}

// Delete user account
export async function deleteUserAccountAPI(): Promise<void> {
  // Get current user to get their ID
  const user = await getCurrentUserAPI();
  await apiClient.delete(`/users/${String(user.id)}`);
  tokenManager.clearTokens();
}

// Check if user is authenticated
export function isAuthenticated(): boolean {
  return tokenManager.getAccessToken() !== null;
}

// Get stored user from token (if available)
export async function getStoredUser(): Promise<User | null> {
  if (!isAuthenticated()) {
    return null;
  }

  try {
    const userResponse = await getCurrentUserAPI();
    return mapBackendUserToFrontend(userResponse as BackendUser);
  } catch {
    // Token might be invalid, clear it
    tokenManager.clearTokens();
    return null;
  }
}

// Re-export types for use in other files
export type {
  AuthResponse,
  AvailabilityResponse,
  BackendUser,
  LoginRequest,
  PasswordChange,
  RegisterRequest,
  RegistrationResponse,
  User,
  UserResponse,
  UserUpdate
} from './types';

// Re-export token manager
export { tokenManager } from './api-client';
