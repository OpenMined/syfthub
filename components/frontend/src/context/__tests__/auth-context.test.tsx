import type { ReactNode } from 'react';

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@/context/theme-context';
import { createMockSdkUser } from '@/test/mocks/fixtures';
import {
  AuthenticationError,
  clearPersistedTokens,
  NetworkError,
  persistTokens,
  restoreTokens,
  syftClient,
  UserAlreadyExistsError
} from '@/test/mocks/sdk-client';

import {
  AuthProvider,
  generateUsernameFromEmail,
  mapSdkUserToFrontend,
  useAuth
} from '../auth-context';

// Mock the SDK client module before importing anything that uses it
vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

// Wrapper for renderHook
function wrapper({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider defaultTheme='light'>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  );
}

describe('auth-context', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: no persisted tokens, me() rejects
    vi.mocked(restoreTokens).mockReturnValue(false);
    vi.mocked(syftClient.auth.me).mockRejectedValue(new AuthenticationError());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ========================================================================
  // generateUsernameFromEmail
  // ========================================================================

  describe('generateUsernameFromEmail', () => {
    it('extracts lowercase alphanumeric from email prefix', () => {
      expect(generateUsernameFromEmail('John.Doe+test@example.com')).toBe('johndoetest');
    });

    it('strips special characters', () => {
      expect(generateUsernameFromEmail('user_name-123@test.com')).toBe('username123');
    });

    it('returns "user" for empty email', () => {
      expect(generateUsernameFromEmail('')).toBe('user');
    });

    it('handles email without @ sign', () => {
      // split('@')[0] returns the whole string if no @
      const result = generateUsernameFromEmail('noatsign');
      expect(result).toBe('noatsign');
    });
  });

  // ========================================================================
  // mapSdkUserToFrontend
  // ========================================================================

  describe('mapSdkUserToFrontend', () => {
    it('maps all SDK user fields to frontend User format', () => {
      const sdkUser = createMockSdkUser();
      const user = mapSdkUserToFrontend(sdkUser as never);

      expect(user.id).toBe('1');
      expect(user.username).toBe('testuser');
      expect(user.email).toBe('test@example.com');
      expect(user.name).toBe('Test User');
      expect(user.full_name).toBe('Test User');
      expect(user.role).toBe('user');
      expect(user.is_active).toBe(true);
      expect(user.created_at).toBe('2024-01-01T00:00:00.000Z');
      expect(user.updated_at).toBe('2024-01-01T00:00:00.000Z');
    });

    it('uses avatarUrl if provided', () => {
      const sdkUser = createMockSdkUser({ avatarUrl: 'https://custom-avatar.com/img.png' });
      const user = mapSdkUserToFrontend(sdkUser as never);
      expect(user.avatar_url).toBe('https://custom-avatar.com/img.png');
    });

    it('generates avatar URL if not provided', () => {
      const sdkUser = createMockSdkUser({ avatarUrl: null });
      const user = mapSdkUserToFrontend(sdkUser as never);
      expect(user.avatar_url).toContain('ui-avatars.com');
    });

    it('maps domain and aggregator_url', () => {
      const sdkUser = createMockSdkUser({
        domain: 'api.example.com',
        aggregatorUrl: 'https://agg.example.com'
      });
      const user = mapSdkUserToFrontend(sdkUser as never);
      expect(user.domain).toBe('api.example.com');
      expect(user.aggregator_url).toBe('https://agg.example.com');
    });
  });

  // ========================================================================
  // useAuth hook - initialization
  // ========================================================================

  describe('useAuth initialization', () => {
    it('starts with null user when no tokens exist', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      // Wait for initialization to complete
      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      expect(result.current.user).toBeNull();
    });

    it('finishes initialization with no user when no tokens', async () => {
      vi.mocked(restoreTokens).mockReturnValue(false);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      expect(result.current.user).toBeNull();
    });

    it('restores user when valid tokens exist', async () => {
      vi.mocked(restoreTokens).mockReturnValue(true);
      vi.mocked(syftClient.auth.me).mockResolvedValue(createMockSdkUser() as never);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      expect(result.current.user).not.toBeNull();
      expect(result.current.user?.email).toBe('test@example.com');
    });

    it('clears tokens when me() rejects with expired token', async () => {
      vi.mocked(restoreTokens).mockReturnValue(true);
      vi.mocked(syftClient.auth.me).mockRejectedValue(new AuthenticationError());

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      expect(result.current.user).toBeNull();
      expect(clearPersistedTokens).toHaveBeenCalled();
    });
  });

  // ========================================================================
  // login
  // ========================================================================

  describe('login', () => {
    it('sets user on successful login', async () => {
      vi.mocked(syftClient.auth.login).mockResolvedValue(createMockSdkUser() as never);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.login({ email: 'test@example.com', password: 'password' });
      });

      expect(result.current.user).not.toBeNull();
      expect(persistTokens).toHaveBeenCalled();
    });

    it('sets error on AuthenticationError', async () => {
      vi.mocked(syftClient.auth.login).mockRejectedValue(new AuthenticationError());

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.login({ email: 'wrong@test.com', password: 'wrong' });
        } catch {
          // Expected
        }
      });

      expect(result.current.error).toBe('Invalid email or password');
    });
  });

  // ========================================================================
  // register
  // ========================================================================

  describe('register', () => {
    it('registers and sets user on success', async () => {
      vi.mocked(syftClient.auth.register).mockResolvedValue(createMockSdkUser() as never);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.register({
          name: 'Test User',
          email: 'test@example.com',
          password: 'password123'
        });
      });

      expect(result.current.user).not.toBeNull();
      expect(persistTokens).toHaveBeenCalled();
    });

    it('retries with suffix on username conflict', async () => {
      const usernameError = new UserAlreadyExistsError('Username taken', 'username');
      vi.mocked(syftClient.auth.register)
        .mockRejectedValueOnce(usernameError)
        .mockResolvedValueOnce(createMockSdkUser() as never);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.register({
          name: 'Test User',
          email: 'test@example.com',
          password: 'password123'
        });
      });

      expect(syftClient.auth.register).toHaveBeenCalledTimes(2);
      expect(result.current.user).not.toBeNull();
    });

    it('does not retry for email conflict', async () => {
      const emailError = new UserAlreadyExistsError('Email taken', 'email');
      vi.mocked(syftClient.auth.register).mockRejectedValue(emailError);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.register({
            name: 'Test User',
            email: 'existing@example.com',
            password: 'password123'
          });
        } catch {
          // Expected
        }
      });

      expect(syftClient.auth.register).toHaveBeenCalledTimes(1);
      expect(result.current.error).toContain('email is already registered');
    });

    it('shows network error message', async () => {
      vi.mocked(syftClient.auth.register).mockRejectedValue(new NetworkError());

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.register({
            name: 'Test',
            email: 'test@test.com',
            password: 'password'
          });
        } catch {
          // Expected
        }
      });

      expect(result.current.error).toBe('Network error. Please check your connection.');
    });
  });

  // ========================================================================
  // logout
  // ========================================================================

  describe('logout', () => {
    it('clears user state and tokens', async () => {
      // First login
      vi.mocked(syftClient.auth.login).mockResolvedValue(createMockSdkUser() as never);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.login({ email: 'test@example.com', password: 'password' });
      });

      expect(result.current.user).not.toBeNull();

      // Logout
      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.user).toBeNull();
      expect(clearPersistedTokens).toHaveBeenCalled();
    });

    it('clears state even if SDK logout throws', async () => {
      vi.mocked(syftClient.auth.login).mockResolvedValue(createMockSdkUser() as never);
      vi.mocked(syftClient.auth.logout).mockRejectedValue(new Error('Logout failed'));
      // isAuthenticated is a property, not a function
      Object.defineProperty(syftClient, 'isAuthenticated', { value: true, writable: true });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.login({ email: 'test@example.com', password: 'password' });
      });

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.user).toBeNull();
      expect(clearPersistedTokens).toHaveBeenCalled();
    });
  });

  // ========================================================================
  // clearError
  // ========================================================================

  describe('clearError', () => {
    it('clears the error state', async () => {
      vi.mocked(syftClient.auth.login).mockRejectedValue(new AuthenticationError());

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.login({ email: 'x@y.com', password: 'wrong' });
        } catch {
          // Expected
        }
      });

      expect(result.current.error).not.toBeNull();

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  // ========================================================================
  // refreshUser
  // ========================================================================

  describe('refreshUser', () => {
    it('updates user from API', async () => {
      vi.mocked(syftClient.auth.login).mockResolvedValue(createMockSdkUser() as never);
      vi.mocked(syftClient.auth.me).mockResolvedValue(
        createMockSdkUser({ fullName: 'Updated Name' }) as never
      );

      const { result } = renderHook(() => useAuth(), { wrapper });

      // First restore tokens to log in
      await waitFor(() => {
        expect(result.current.isInitializing).toBe(false);
      });

      await act(async () => {
        await result.current.login({ email: 'test@example.com', password: 'password' });
      });

      await act(async () => {
        await result.current.refreshUser();
      });

      expect(result.current.user?.name).toBe('Updated Name');
    });
  });
});
