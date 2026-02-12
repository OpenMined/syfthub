/**
 * Error reporter for sending frontend errors to the backend.
 */

import { CORRELATION_ID_HEADER, getOrCreateCorrelationId } from './correlation';
import { logger } from './logger';

/** Error context information */
export interface ErrorContext {
  /** Current page URL */
  url?: string;
  /** Browser user agent */
  userAgent?: string;
  /** Relevant app state at time of error */
  appState?: Record<string, unknown>;
}

/** Error report payload */
export interface ErrorReport {
  /** Correlation ID for tracing */
  correlationId?: string;
  /** When the error occurred */
  timestamp: string;
  /** Event name (e.g., 'frontend.error.unhandled') */
  event: string;
  /** Human-readable error description */
  message: string;
  /** Error details */
  error: {
    type: string;
    message?: string;
    stackTrace?: string;
    componentStack?: string;
  };
  /** Error context */
  context?: ErrorContext;
}

/**
 * Check if running in a browser environment.
 */
function isBrowser(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, sonarjs/different-types-comparison -- SSR check
  return globalThis.window !== undefined;
}

/**
 * Get the API base URL for error reporting.
 */
function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;

  // If not set or is the proxy path, use same-origin
  if (!envUrl || envUrl === '/api/v1') {
    return '/api/v1';
  }

  // Ensure it ends with /api/v1
  if (envUrl.endsWith('/api/v1')) {
    return envUrl;
  }
  if (envUrl.endsWith('/api/v1/')) {
    return envUrl.slice(0, -1);
  }

  return `${envUrl}/api/v1`;
}

/**
 * Report an error to the backend for logging and analysis.
 *
 * @param error - The error to report
 * @param event - Event name (defaults to 'frontend.error.unhandled')
 * @param componentStack - React component stack trace (optional)
 * @param appState - Relevant app state at time of error (optional)
 *
 * @example
 * try {
 *   await someOperation();
 * } catch (error) {
 *   await reportError(error, 'feature.operation.failed');
 * }
 */
export async function reportError(
  error: unknown,
  event = 'frontend.error.unhandled',
  componentStack?: string,
  appState?: Record<string, unknown>
): Promise<void> {
  const correlationId = getOrCreateCorrelationId();

  // Normalize error
  const normalizedError = error instanceof Error ? error : new Error(String(error));

  const report: ErrorReport = {
    correlationId,
    timestamp: new Date().toISOString(),
    event,
    message: normalizedError.message || 'An error occurred',
    error: {
      type: normalizedError.name || 'Error',
      message: normalizedError.message,
      stackTrace: normalizedError.stack,
      componentStack
    },
    context: {
      url: isBrowser() ? globalThis.location.href : undefined,
      userAgent: isBrowser() ? navigator.userAgent : undefined,
      appState
    }
  };

  // Log locally first
  logger.error(
    event,
    {
      errorType: report.error.type,
      url: report.context?.url
    },
    normalizedError
  );

  // Send to backend (fire and forget, don't block on failure)
  try {
    const apiUrl = getApiBaseUrl();
    const response = await fetch(`${apiUrl}/errors/report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [CORRELATION_ID_HEADER]: correlationId
      },
      body: JSON.stringify({
        correlation_id: report.correlationId,
        timestamp: report.timestamp,
        event: report.event,
        message: report.message,
        error: {
          type: report.error.type,
          message: report.error.message,
          stack_trace: report.error.stackTrace,
          component_stack: report.error.componentStack
        },
        context: {
          url: report.context?.url,
          user_agent: report.context?.userAgent,
          app_state: report.context?.appState
        }
      })
    });

    if (!response.ok) {
      logger.warn('error.report.failed', {
        status: response.status
      });
    }
  } catch (reportingError) {
    // Don't throw - error reporting should never break the app
    logger.warn(
      'error.report.network_error',
      {},
      reportingError instanceof Error ? reportingError : undefined
    );
  }
}
