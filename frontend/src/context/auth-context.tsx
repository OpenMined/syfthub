/**
 * Authentication Context
 *
 * Provides authentication state and methods throughout the application.
 * Uses the SyftHub SDK for all API operations.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

import type { User as SdkUser } from '@/lib/sdk-client';
import type { User } from '@/lib/types';

import {
  AuthenticationError,
  clearPersistedTokens,
  NetworkError,
  persistTokens,
  restoreTokens,
  syftClient,
  ValidationError
} from '@/lib/sdk-client';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isInitializing: boolean;
  error: string | null;
  login: (credentials: { email: string; password: string }) => Promise<void>;
  register: (userData: { name: string; email: string; password: string }) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  loginWithGitHub: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  refreshUser: () => Promise<void>;
  updateUser: (updatedUser: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Generate a placeholder avatar URL from a name.
 */
function generateAvatarUrl(name: string): string {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=272532&color=fff`;
}

/**
 * Generate a base username from email.
 */
function generateUsernameFromEmail(email: string): string {
  const emailPrefix = email.split('@')[0];
  return emailPrefix ? emailPrefix.toLowerCase().replaceAll(/[^a-z0-9]/g, '') : 'user';
}

/**
 * Check if error is a username-already-exists error.
 */
function isUsernameExistsError(error: unknown): boolean {
  const errorMessage = error instanceof Error ? error.message.toLowerCase() : '';
  return (
    errorMessage.includes('username already exists') ||
    errorMessage.includes('username already registered') ||
    errorMessage.includes('already exists')
  );
}

/**
 * Generate a username with random suffix.
 */
function generateUsernameWithSuffix(baseUsername: string): string {
  const randomSuffix = Math.floor(Math.random() * 900) + 100; // NOSONAR - not security-sensitive
  return `${baseUsername}${String(randomSuffix)}`;
}

/**
 * Attempt registration with username retry logic.
 */
async function attemptRegistration(
  userData: { name: string; email: string; password: string },
  baseUsername: string,
  maxAttempts = 5
): Promise<SdkUser> {
  let username = baseUsername;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await syftClient.auth.register({
        username,
        email: userData.email,
        password: userData.password,
        fullName: userData.name
      });
    } catch (registerError) {
      const isLastAttempt = attempt === maxAttempts - 1;
      if (!isUsernameExistsError(registerError) || isLastAttempt) {
        throw registerError;
      }
      username = generateUsernameWithSuffix(baseUsername);
    }
  }

  throw new Error('Username already taken. Please try a different email or contact support.');
}

/**
 * Convert SDK User type to Frontend User type.
 *
 * This provides backward compatibility with existing components while
 * using the SDK internally.
 */
function mapSdkUserToFrontend(sdkUser: SdkUser): User {
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
 * Extract a user-friendly error message from an error.
 */
function getErrorMessage(error: unknown): string {
  if (error instanceof AuthenticationError) {
    return 'Invalid email or password';
  }
  if (error instanceof ValidationError) {
    return error.message;
  }
  if (error instanceof NetworkError) {
    return 'Network error. Please check your connection.';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

interface AuthProviderProperties {
  children: React.ReactNode;
}

export function AuthProvider({ children }: Readonly<AuthProviderProperties>) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize auth state from localStorage on app start
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // Restore tokens from localStorage to SDK
        if (restoreTokens()) {
          // Tokens restored, fetch current user
          const sdkUser = await syftClient.auth.me();
          setUser(mapSdkUserToFrontend(sdkUser));
        }
      } catch (initError) {
        console.error('Failed to initialize auth:', initError);
        // Clear invalid tokens
        clearPersistedTokens();
      } finally {
        setIsInitializing(false);
      }
    };

    void initializeAuth();
  }, []);

  const login = async (credentials: { email: string; password: string }): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // SDK auth.login takes username (email works as username)
      const sdkUser = await syftClient.auth.login(credentials.email, credentials.password);

      // Persist tokens to localStorage
      persistTokens();

      // Update state
      setUser(mapSdkUserToFrontend(sdkUser));
    } catch (loginError) {
      const message = getErrorMessage(loginError);
      setError(message);
      throw loginError;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (userData: {
    name: string;
    email: string;
    password: string;
  }): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      const baseUsername = generateUsernameFromEmail(userData.email);
      const sdkUser = await attemptRegistration(userData, baseUsername);

      // Persist tokens to localStorage
      persistTokens();

      // Update state
      setUser(mapSdkUserToFrontend(sdkUser));
    } catch (registerError) {
      const message = getErrorMessage(registerError);
      setError(message);
      throw registerError;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGoogle = async (): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // Google OAuth not yet implemented
      await new Promise((resolve) => setTimeout(resolve, 600));
      throw new Error('Google OAuth not yet implemented');
    } catch (googleError) {
      const message = getErrorMessage(googleError);
      setError(message);
      throw googleError;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGitHub = async (): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // GitHub OAuth not yet implemented
      await new Promise((resolve) => setTimeout(resolve, 600));
      throw new Error('GitHub OAuth not yet implemented');
    } catch (githubError) {
      const message = getErrorMessage(githubError);
      setError(message);
      throw githubError;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async (): Promise<void> => {
    try {
      setIsLoading(true);

      // Call SDK logout (this also clears SDK internal tokens)
      if (syftClient.isAuthenticated) {
        await syftClient.auth.logout();
      }

      // Clear persisted tokens
      clearPersistedTokens();

      // Update state
      setUser(null);
      setError(null);

      // Dispatch logout event for other contexts to clean up (e.g., accounting vault)
      globalThis.dispatchEvent(new CustomEvent('syft:logout'));
    } catch (logoutError) {
      console.error('Logout error:', logoutError);
      // Even if logout fails, clear local state
      clearPersistedTokens();
      setUser(null);
      // Still dispatch logout event on error
      globalThis.dispatchEvent(new CustomEvent('syft:logout'));
    } finally {
      setIsLoading(false);
    }
  };

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const sdkUser = await syftClient.auth.me();
      setUser(mapSdkUserToFrontend(sdkUser));
    } catch (refreshError) {
      console.error('Failed to refresh user:', refreshError);
      // Don't clear user state on refresh failure - let them continue with stale data
    }
  }, []);

  /**
   * Directly update the user state without fetching from the API.
   * Use this when you already have the updated user data (e.g., from a PUT response).
   */
  const updateUser = useCallback((updatedUser: User): void => {
    setUser(updatedUser);
  }, []);

  const value: AuthContextType = {
    user,
    isLoading,
    isInitializing,
    error,
    login,
    register,
    loginWithGoogle,
    loginWithGitHub,
    logout,
    clearError,
    refreshUser,
    updateUser
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Custom hook to use auth context
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
