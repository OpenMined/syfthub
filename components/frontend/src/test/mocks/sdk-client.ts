/**
 * Mock SDK client for testing.
 *
 * Error classes are real (not mocks) so `instanceof` checks work correctly
 * in auth-context.tsx and use-chat-workflow.ts.
 */
import { vi } from 'vitest';

// ============================================================================
// Real Error Classes (for instanceof checks)
// ============================================================================

export class SyftHubError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SyftHubError';
  }
}

export class AuthenticationError extends SyftHubError {
  constructor(message = 'Authentication failed') {
    super(message);
    this.name = 'AuthenticationError';
  }
}

export class AggregatorError extends SyftHubError {
  constructor(message = 'Aggregator error') {
    super(message);
    this.name = 'AggregatorError';
  }
}

export class EndpointResolutionError extends SyftHubError {
  constructor(message = 'Endpoint resolution failed') {
    super(message);
    this.name = 'EndpointResolutionError';
  }
}

export class UserAlreadyExistsError extends SyftHubError {
  field?: string;
  constructor(message = 'User already exists', field?: string) {
    super(message);
    this.name = 'UserAlreadyExistsError';
    this.field = field;
  }
}

export class AccountingAccountExistsError extends SyftHubError {
  constructor(message = 'Accounting account exists') {
    super(message);
    this.name = 'AccountingAccountExistsError';
  }
}

export class InvalidAccountingPasswordError extends SyftHubError {
  constructor(message = 'Invalid accounting password') {
    super(message);
    this.name = 'InvalidAccountingPasswordError';
  }
}

export class ValidationError extends SyftHubError {
  constructor(message = 'Validation error') {
    super(message);
    this.name = 'ValidationError';
  }
}

export class NetworkError extends SyftHubError {
  constructor(message = 'Network error') {
    super(message);
    this.name = 'NetworkError';
  }
}

export class APIError extends SyftHubError {
  statusCode: number;
  constructor(message = 'API error', statusCode = 500) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
  }
}

export class AuthorizationError extends SyftHubError {
  constructor(message = 'Authorization failed') {
    super(message);
    this.name = 'AuthorizationError';
  }
}

export class NotFoundError extends SyftHubError {
  constructor(message = 'Not found') {
    super(message);
    this.name = 'NotFoundError';
  }
}

export class AccountingServiceUnavailableError extends SyftHubError {
  constructor(message = 'Accounting service unavailable') {
    super(message);
    this.name = 'AccountingServiceUnavailableError';
  }
}

// ============================================================================
// Mock SDK Client
// ============================================================================

function createPaginatedMock() {
  return vi.fn().mockReturnValue({
    firstPage: vi.fn().mockResolvedValue([]),
    all: vi.fn().mockResolvedValue([])
  });
}

export const syftClient = {
  auth: {
    login: vi.fn().mockRejectedValue(new AuthenticationError()),
    register: vi.fn().mockRejectedValue(new AuthenticationError()),
    logout: vi.fn().mockResolvedValue(null),
    me: vi.fn().mockRejectedValue(new AuthenticationError()),
    changePassword: vi.fn().mockResolvedValue(null)
  },
  hub: {
    browse: createPaginatedMock(),
    trending: createPaginatedMock(),
    guestAccessible: createPaginatedMock()
  },
  chat: {
    stream: vi.fn().mockReturnValue(
      (async function* () {
        // empty mock stream
      })()
    ),
    complete: vi.fn().mockResolvedValue({ content: '', sources: {} })
  },
  myEndpoints: {
    list: vi.fn().mockReturnValue({
      all: vi.fn().mockResolvedValue([])
    }),
    get: vi.fn().mockResolvedValue({}),
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(null)
  },
  users: {
    update: vi.fn().mockResolvedValue({}),
    checkUsername: vi.fn().mockResolvedValue(true),
    checkEmail: vi.fn().mockResolvedValue(true)
  },
  getTokens: vi.fn().mockReturnValue(null),
  setTokens: vi.fn(),
  isAuthenticated: false
};

// ============================================================================
// Token Helpers
// ============================================================================

export const persistTokens = vi.fn().mockReturnValue(true);
export const restoreTokens = vi.fn().mockReturnValue(false);
export const clearPersistedTokens = vi.fn();
export const hasPersistedTokens = vi.fn().mockReturnValue(false);
