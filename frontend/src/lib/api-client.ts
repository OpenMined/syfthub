/**
 * API Client Configuration for SyftHub Backend Integration
 *
 * Provides centralized HTTP client with:
 * - JWT token management
 * - Request/response interceptors
 * - Error handling
 * - Automatic token refresh
 */

// API Configuration
// Uses VITE_API_URL env var if set, otherwise defaults to same-origin (via proxy)
const API_BASE_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1';

// Storage keys for tokens
const ACCESS_TOKEN_KEY = 'syft_access_token';
const REFRESH_TOKEN_KEY = 'syft_refresh_token';

// Token management utilities
export const tokenManager = {
  getAccessToken: (): string | null => {
    try {
      return localStorage.getItem(ACCESS_TOKEN_KEY);
    } catch {
      return null;
    }
  },

  getRefreshToken: (): string | null => {
    try {
      return localStorage.getItem(REFRESH_TOKEN_KEY);
    } catch {
      return null;
    }
  },

  setTokens: (accessToken: string, refreshToken: string): void => {
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    } catch (error) {
      console.error('Failed to store tokens:', error);
    }
  },

  clearTokens: (): void => {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch (error) {
      console.error('Failed to clear tokens:', error);
    }
  }
};

// API Error class
export class APIError extends Error {
  public status: number;
  public data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

// Token response type
interface TokenRefreshResponse {
  access_token: string;
  refresh_token: string;
}

// Error response type
interface ErrorResponse {
  detail?: string;
}

// HTTP Client class
class HTTPClient {
  private baseURL: string;
  private isRefreshing = false;
  private refreshPromise: Promise<void> | null = null;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private async refreshAccessToken(): Promise<void> {
    const refreshToken = tokenManager.getRefreshToken();

    if (!refreshToken) {
      throw new APIError('No refresh token available', 401);
    }

    const response = await fetch(`${this.baseURL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ refresh_token: refreshToken })
    });

    if (!response.ok) {
      tokenManager.clearTokens();
      throw new APIError('Token refresh failed', response.status);
    }

    const data = (await response.json()) as TokenRefreshResponse;
    tokenManager.setTokens(data.access_token, data.refresh_token);
  }

  private async handleTokenRefresh(): Promise<void> {
    if (this.isRefreshing) {
      // Wait for ongoing refresh
      if (this.refreshPromise) {
        await this.refreshPromise;
      }
      return;
    }

    this.isRefreshing = true;
    this.refreshPromise = this.refreshAccessToken().finally(() => {
      this.isRefreshing = false;
      this.refreshPromise = null;
    });

    await this.refreshPromise;
  }

  async request<T>(
    endpoint: string,
    options: {
      method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
      body?: unknown;
      headers?: Record<string, string>;
      requiresAuth?: boolean;
    } = {}
  ): Promise<T> {
    const { method = 'GET', body, headers = {}, requiresAuth = true } = options;

    const url = `${this.baseURL}${endpoint}`;
    const requestHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      ...headers
    };

    // Add authorization header if required
    if (requiresAuth) {
      const accessToken = tokenManager.getAccessToken();
      if (accessToken) {
        requestHeaders.Authorization = `Bearer ${accessToken}`;
      }
    }

    const requestOptions: RequestInit = {
      method,
      headers: requestHeaders
    };

    if (body && method !== 'GET') {
      requestOptions.body = JSON.stringify(body);
    }

    try {
      const response = await fetch(url, requestOptions);

      // Handle 401 - try token refresh
      if (response.status === 401 && requiresAuth) {
        try {
          await this.handleTokenRefresh();

          // Retry request with new token
          const newAccessToken = tokenManager.getAccessToken();
          if (newAccessToken) {
            requestHeaders.Authorization = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(url, {
              ...requestOptions,
              headers: requestHeaders
            });

            if (retryResponse.ok) {
              return (await retryResponse.json()) as T;
            }
          }
        } catch {
          // Refresh failed, clear tokens and throw error
          tokenManager.clearTokens();
          throw new APIError('Authentication failed', 401);
        }
      }

      if (!response.ok) {
        let errorData: ErrorResponse = { detail: 'Request failed' };
        try {
          errorData = (await response.json()) as ErrorResponse;
        } catch {
          // Keep default error data
        }

        throw new APIError(
          errorData.detail ?? `HTTP ${String(response.status)}`,
          response.status,
          errorData
        );
      }

      // Handle no-content responses
      if (response.status === 204) {
        return null as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }

      // Network or other errors
      throw new APIError(error instanceof Error ? error.message : 'Network error', 0);
    }
  }

  // Convenience methods
  async get<T>(endpoint: string, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET', requiresAuth });
  }

  async post<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data,
      requiresAuth
    });
  }

  async put<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data,
      requiresAuth
    });
  }

  async patch<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data,
      requiresAuth
    });
  }

  async delete<T>(endpoint: string, requiresAuth = true): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE', requiresAuth });
  }
}

// Export configured API client
export const apiClient = new HTTPClient(API_BASE_URL);

// Export configuration
export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
  ENDPOINTS: {
    AUTH: {
      LOGIN: '/auth/login',
      REGISTER: '/auth/register',
      LOGOUT: '/auth/logout',
      REFRESH: '/auth/refresh',
      ME: '/auth/me',
      CHANGE_PASSWORD: '/auth/me/password',
      REGENERATE_KEYS: '/auth/regenerate-keys'
    },
    USERS: {
      LIST: '/users',
      ME: '/users/me',
      BY_ID: (id: number) => `/users/${String(id)}`,
      DEACTIVATE: (id: number) => `/users/${String(id)}/deactivate`,
      ACTIVATE: (id: number) => `/users/${String(id)}/activate`,
      VERIFY_SIGNATURE: '/users/verify-signature'
    },
    DATASITES: {
      LIST: '/datasites',
      CREATE: '/datasites',
      PUBLIC: '/datasites/public',
      TRENDING: '/datasites/trending',
      BY_ID: (id: number) => `/datasites/${String(id)}`
    },
    ORGANIZATIONS: {
      LIST: '/organizations',
      CREATE: '/organizations',
      BY_ID: (id: number) => `/organizations/${String(id)}`,
      MEMBERS: (id: number) => `/organizations/${String(id)}/members`,
      MEMBER: (orgId: number, userId: number) =>
        `/organizations/${String(orgId)}/members/${String(userId)}`
    }
  }
} as const;
