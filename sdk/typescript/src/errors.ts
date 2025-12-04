/**
 * Base error class for all SyftHub SDK errors.
 */
export class SyftHubError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SyftHubError';
    // Maintains proper stack trace for where error was thrown (V8 engines)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }
}

/**
 * Error thrown when an API request fails with an error status code.
 */
export class APIError extends SyftHubError {
  constructor(
    message: string,
    public readonly status: number,
    public readonly data?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }
}

/**
 * Error thrown when authentication is required but not provided,
 * or when credentials are invalid (HTTP 401).
 */
export class AuthenticationError extends SyftHubError {
  constructor(message: string = 'Authentication required') {
    super(message);
    this.name = 'AuthenticationError';
  }
}

/**
 * Error thrown when the user doesn't have permission to access
 * a resource (HTTP 403).
 */
export class AuthorizationError extends SyftHubError {
  constructor(message: string = 'Permission denied') {
    super(message);
    this.name = 'AuthorizationError';
  }
}

/**
 * Error thrown when a requested resource is not found (HTTP 404).
 */
export class NotFoundError extends SyftHubError {
  constructor(message: string = 'Resource not found') {
    super(message);
    this.name = 'NotFoundError';
  }
}

/**
 * Error thrown when request validation fails (HTTP 422).
 * Contains field-level error details when available.
 */
export class ValidationError extends SyftHubError {
  constructor(
    message: string,
    public readonly errors?: Record<string, string[]>
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Error thrown when a network request fails (connection errors, timeouts).
 */
export class NetworkError extends SyftHubError {
  constructor(
    message: string = 'Network request failed',
    public readonly cause?: Error
  ) {
    super(message);
    this.name = 'NetworkError';
  }
}
