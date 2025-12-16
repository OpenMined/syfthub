import {
  AccountingAccountExistsError,
  AccountingServiceUnavailableError,
  APIError,
  AuthenticationError,
  AuthorizationError,
  InvalidAccountingPasswordError,
  NetworkError,
  NotFoundError,
  ValidationError,
} from './errors.js';
import { toCamelCase, toSnakeCase, buildSearchParams } from './utils.js';

/**
 * Options for HTTP requests.
 */
export interface RequestOptions {
  /** Whether to include the Authorization header (default: true) */
  includeAuth?: boolean;
  /** Whether to send body as form-urlencoded instead of JSON */
  isFormData?: boolean;
  /** Request-specific timeout in milliseconds */
  timeout?: number;
}

/**
 * Internal request options including body and params.
 */
interface InternalRequestOptions extends RequestOptions {
  body?: unknown;
  params?: Record<string, unknown>;
}

/**
 * Auth tokens returned from login/refresh.
 */
export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
}

/**
 * Internal HTTP client for making API requests.
 *
 * Handles:
 * - Bearer token authentication
 * - Automatic token refresh on 401 responses
 * - JSON serialization/deserialization
 * - snake_case <-> camelCase conversion
 * - Error handling and exception mapping
 */
export class HTTPClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private isRefreshing = false;
  private refreshPromise: Promise<void> | null = null;

  /**
   * Create a new HTTP client.
   *
   * @param baseUrl - Base URL for all API requests (without trailing slash)
   * @param timeout - Default timeout in milliseconds (default: 30000)
   */
  constructor(
    private readonly baseUrl: string,
    private readonly timeout: number = 30000
  ) {}

  /**
   * Set authentication tokens.
   */
  setTokens(access: string, refresh: string): void {
    this.accessToken = access;
    this.refreshToken = refresh;
  }

  /**
   * Get current authentication tokens.
   */
  getTokens(): AuthTokens | null {
    if (!this.accessToken || !this.refreshToken) {
      return null;
    }
    return {
      accessToken: this.accessToken,
      refreshToken: this.refreshToken,
      tokenType: 'bearer',
    };
  }

  /**
   * Clear authentication tokens.
   */
  clearTokens(): void {
    this.accessToken = null;
    this.refreshToken = null;
  }

  /**
   * Check if the client has valid tokens.
   */
  hasTokens(): boolean {
    return this.accessToken !== null;
  }

  /**
   * Make a GET request.
   */
  async get<T>(
    path: string,
    params?: Record<string, unknown>,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>('GET', path, { ...options, params });
  }

  /**
   * Make a POST request.
   */
  async post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', path, { ...options, body });
  }

  /**
   * Make a PUT request.
   */
  async put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>('PUT', path, { ...options, body });
  }

  /**
   * Make a PATCH request.
   */
  async patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>('PATCH', path, { ...options, body });
  }

  /**
   * Make a DELETE request.
   */
  async delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('DELETE', path, options);
  }

  /**
   * Make an HTTP request with automatic retry on 401.
   */
  private async request<T>(
    method: string,
    path: string,
    options: InternalRequestOptions = {}
  ): Promise<T> {
    const { includeAuth = true, isFormData = false, timeout, body, params } = options;

    // Build URL with query params
    let url = `${this.baseUrl}${path}`;
    if (params) {
      const searchParams = buildSearchParams(params);
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    // Build headers
    const headers: Record<string, string> = {};

    if (includeAuth && this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    // Build body
    let requestBody: string | undefined;
    if (body !== undefined) {
      if (isFormData) {
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
        // For form data, convert to URLSearchParams
        const formData = new URLSearchParams();
        for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
          if (value !== undefined && value !== null) {
            formData.append(key, String(value));
          }
        }
        requestBody = formData.toString();
      } else {
        headers['Content-Type'] = 'application/json';
        // Convert camelCase to snake_case for JSON bodies
        requestBody = JSON.stringify(toSnakeCase(body));
      }
    }

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout ?? this.timeout);

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: requestBody,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Handle 401 with automatic token refresh
      if (response.status === 401 && includeAuth && this.refreshToken) {
        // Attempt to refresh the token
        await this.attemptTokenRefresh();

        // Retry the original request with new token
        return this.request<T>(method, path, {
          ...options,
          // Mark that we shouldn't retry again to prevent infinite loops
          includeAuth: true,
        });
      }

      return await this.handleResponse<T>(response);
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof SyftHubError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new NetworkError('Request timed out', error);
        }
        throw new NetworkError(error.message, error);
      }

      throw new NetworkError('Unknown network error');
    }
  }

  /**
   * Handle the HTTP response and convert to the expected type.
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    // Try to parse response as JSON
    let data: unknown;
    const contentType = response.headers.get('content-type');

    if (contentType?.includes('application/json')) {
      try {
        data = await response.json();
      } catch {
        data = null;
      }
    } else {
      // For non-JSON responses, use text
      const text = await response.text();
      data = text || null;
    }

    // Handle error responses
    if (!response.ok) {
      this.handleErrorResponse(response.status, data);
    }

    // Convert snake_case to camelCase and parse dates
    return toCamelCase<T>(data);
  }

  /**
   * Handle error responses by throwing appropriate exceptions.
   */
  private handleErrorResponse(status: number, data: unknown): never {
    const message = this.extractErrorMessage(data);
    const { code, detail } = this.extractErrorCodeAndDetail(data);

    // Check for accounting-specific errors based on error code first
    if (code) {
      switch (code) {
        case 'ACCOUNTING_ACCOUNT_EXISTS':
          throw new AccountingAccountExistsError(message, detail);
        case 'INVALID_ACCOUNTING_PASSWORD':
          throw new InvalidAccountingPasswordError(message, detail);
        case 'ACCOUNTING_SERVICE_UNAVAILABLE':
          throw new AccountingServiceUnavailableError(message, detail);
      }
    }

    // Standard status code handling
    switch (status) {
      case 401:
        throw new AuthenticationError(message);
      case 403:
        throw new AuthorizationError(message);
      case 404:
        throw new NotFoundError(message);
      case 422:
        throw new ValidationError(message, this.extractValidationErrors(data));
      default:
        throw new APIError(message, status, data);
    }
  }

  /**
   * Extract error code and detail from API response.
   * Used for accounting-specific error handling.
   */
  private extractErrorCodeAndDetail(
    data: unknown
  ): { code?: string; detail?: unknown } {
    if (!data || typeof data !== 'object') {
      return {};
    }

    // FastAPI returns { detail: { code: "...", message: "...", ... } }
    if ('detail' in data) {
      const detail = (data as { detail: unknown }).detail;
      if (detail && typeof detail === 'object' && 'code' in detail) {
        const innerDetail = detail as { code?: string };
        return {
          code: innerDetail.code,
          detail: detail,
        };
      }
    }

    return {};
  }

  /**
   * Extract error message from API response.
   */
  private extractErrorMessage(data: unknown): string {
    if (typeof data === 'string') {
      return data;
    }

    if (data && typeof data === 'object') {
      // FastAPI style: { detail: "message" }
      if ('detail' in data) {
        const detail = (data as { detail: unknown }).detail;
        if (typeof detail === 'string') {
          return detail;
        }
        // FastAPI validation errors: { detail: [{ msg: "...", loc: [...] }] }
        if (Array.isArray(detail) && detail.length > 0) {
          const firstError = detail[0] as { msg?: string };
          if (firstError?.msg) {
            return firstError.msg;
          }
        }
      }

      // Generic: { message: "..." } or { error: "..." }
      if ('message' in data && typeof (data as { message: unknown }).message === 'string') {
        return (data as { message: string }).message;
      }
      if ('error' in data && typeof (data as { error: unknown }).error === 'string') {
        return (data as { error: string }).error;
      }
    }

    return 'An error occurred';
  }

  /**
   * Extract field-level validation errors from API response.
   */
  private extractValidationErrors(data: unknown): Record<string, string[]> | undefined {
    if (!data || typeof data !== 'object' || !('detail' in data)) {
      return undefined;
    }

    const detail = (data as { detail: unknown }).detail;
    if (!Array.isArray(detail)) {
      return undefined;
    }

    const errors: Record<string, string[]> = {};

    for (const error of detail) {
      if (typeof error === 'object' && error !== null && 'loc' in error && 'msg' in error) {
        const { loc, msg } = error as { loc: unknown[]; msg: string };
        // loc is typically ['body', 'field_name']
        const field = String(loc[loc.length - 1] ?? 'unknown');
        if (!errors[field]) {
          errors[field] = [];
        }
        errors[field].push(msg);
      }
    }

    return Object.keys(errors).length > 0 ? errors : undefined;
  }

  /**
   * Attempt to refresh the access token using the refresh token.
   */
  private async attemptTokenRefresh(): Promise<void> {
    // If already refreshing, wait for the existing refresh to complete
    if (this.isRefreshing && this.refreshPromise) {
      await this.refreshPromise;
      return;
    }

    this.isRefreshing = true;

    this.refreshPromise = (async () => {
      try {
        const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh_token: this.refreshToken }),
        });

        if (!response.ok) {
          // Refresh failed, clear tokens
          this.clearTokens();
          throw new AuthenticationError('Token refresh failed');
        }

        const data = (await response.json()) as {
          access_token: string;
          refresh_token: string;
        };

        this.accessToken = data.access_token;
        this.refreshToken = data.refresh_token;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    await this.refreshPromise;
  }
}

// Import SyftHubError for type checking
import { SyftHubError } from './errors.js';
