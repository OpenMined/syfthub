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

// =============================================================================
// User Registration Errors
// =============================================================================

/**
 * Error thrown when username or email already exists in SyftHub (HTTP 409).
 *
 * This error indicates a duplicate user registration attempt.
 * The `field` property indicates which field caused the conflict.
 *
 * @example
 * ```typescript
 * try {
 *   await client.auth.register({ username: "john", email: "john@example.com", ... });
 * } catch (error) {
 *   if (error instanceof UserAlreadyExistsError) {
 *     console.log(`${error.field} is already taken`);
 *   }
 * }
 * ```
 */
export class UserAlreadyExistsError extends SyftHubError {
  /** The field that caused the conflict ("username" or "email") */
  public readonly field?: string;

  constructor(
    message: string = 'Username or email already exists',
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'UserAlreadyExistsError';
    // Extract field from detail if available
    if (detail && typeof detail === 'object' && 'field' in detail) {
      this.field = (detail as { field?: string }).field;
    }
  }
}

// =============================================================================
// Accounting-related Errors
// =============================================================================

/**
 * Error thrown when email already exists in the accounting service during registration.
 *
 * This error indicates that the user needs to provide their existing
 * accounting password to link their SyftHub account with their existing
 * accounting account.
 *
 * @example
 * ```typescript
 * try {
 *   await client.auth.register({ username: "john", email: "john@example.com", ... });
 * } catch (error) {
 *   if (error instanceof AccountingAccountExistsError) {
 *     // Prompt user for their existing accounting password
 *     const accountingPassword = prompt("Enter your existing accounting password:");
 *     // Retry registration with the password
 *     await client.auth.register({
 *       username: "john",
 *       email: "john@example.com",
 *       ...,
 *       accountingPassword
 *     });
 *   }
 * }
 * ```
 */
export class AccountingAccountExistsError extends SyftHubError {
  /** Indicates that the user needs to provide their existing accounting password */
  public readonly requiresAccountingPassword = true;

  constructor(
    message: string = 'This email already has an account in the accounting service',
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'AccountingAccountExistsError';
  }
}

/**
 * Error thrown when the provided accounting password is invalid.
 */
export class InvalidAccountingPasswordError extends SyftHubError {
  constructor(
    message: string = 'The provided accounting password is invalid',
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'InvalidAccountingPasswordError';
  }
}

/**
 * Error thrown when the accounting service is unavailable or returns an error.
 */
export class AccountingServiceUnavailableError extends SyftHubError {
  constructor(
    message: string = 'Accounting service is unavailable',
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'AccountingServiceUnavailableError';
  }
}
