import React, { createContext, useContext, useEffect, useState } from 'react';

import type { AuthResponse, User } from '@/lib/types';

import {
  getStoredUser,
  githubOAuthAPI,
  googleOAuthAPI,
  loginAPI,
  logoutAPI,
  mapBackendUserToFrontend,
  registerAPI,
  tokenManager
} from '@/lib/real-auth-api';

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
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token management is now handled by the real auth API

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
        const storedUser = await getStoredUser();
        if (storedUser) {
          setUser(storedUser);
        }
      } catch (initError) {
        console.error('Failed to initialize auth:', initError);
        tokenManager.clearTokens();
      } finally {
        setIsInitializing(false);
      }
    };

    void initializeAuth();
  }, []);

  const handleAuthSuccess = (response: AuthResponse) => {
    // Tokens are already stored by the real auth API
    const frontendUser = mapBackendUserToFrontend(response.user);
    setUser(frontendUser);
    setError(null);
  };

  const handleAuthError = (authError: unknown) => {
    let message = 'An unexpected error occurred';

    if (authError instanceof Error) {
      message = authError.message;
    } else if (typeof authError === 'string') {
      message = authError;
    } else if (authError && typeof authError === 'object' && 'detail' in authError) {
      message = String((authError as { detail: unknown }).detail);
    }

    console.error('Auth error details:', { error: authError, message });
    setError(message);
  };

  const login = async (credentials: { email: string; password: string }): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await loginAPI(credentials);
      handleAuthSuccess(response);
    } catch (loginError) {
      handleAuthError(loginError);
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
      const response = await registerAPI(userData);
      handleAuthSuccess(response);
    } catch (registerError) {
      handleAuthError(registerError);
      throw registerError;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGoogle = async (): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // In a real implementation, this would open Google OAuth popup
      // For now, we'll simulate the OAuth flow
      const mockGoogleToken = 'mock_google_token_' + Math.random().toString(36).slice(2); // NOSONAR
      const response = await googleOAuthAPI({ token: mockGoogleToken });
      handleAuthSuccess(response);
    } catch (googleError) {
      handleAuthError(googleError);
      throw googleError;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGitHub = async (): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // In a real implementation, this would redirect to GitHub OAuth
      // For now, we'll simulate the OAuth flow
      const mockGitHubCode = 'mock_github_code_' + Math.random().toString(36).slice(2); // NOSONAR
      const response = await githubOAuthAPI({ code: mockGitHubCode });
      handleAuthSuccess(response);
    } catch (githubError) {
      handleAuthError(githubError);
      throw githubError;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async (): Promise<void> => {
    try {
      setIsLoading(true);
      const token = tokenManager.getAccessToken();

      if (token) {
        await logoutAPI(token);
      }

      setUser(null);
      setError(null);
    } catch (logoutError) {
      console.error('Logout error:', logoutError);
      // Even if logout fails, clear local state
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const clearError = () => {
    setError(null);
  };

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
    clearError
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
