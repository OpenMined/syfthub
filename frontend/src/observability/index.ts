/**
 * Observability module for SyftHub frontend.
 *
 * Provides correlation ID management, structured logging,
 * error boundary components, and error reporting.
 *
 * @example
 * import { generateCorrelationId, logger } from '@/observability';
 *
 * const correlationId = generateCorrelationId();
 * logger.info('user.action', { correlationId, action: 'click' });
 */

export {
  generateCorrelationId,
  getOrCreateCorrelationId,
  setCorrelationId,
  getCorrelationId,
  clearCorrelationId,
  CORRELATION_ID_HEADER
} from './correlation';

export { logger, LogLevel, type LogContext } from './logger';

export { ErrorBoundary, type ErrorBoundaryProps, type ErrorFallbackProps } from './error-boundary';

export { attachCorrelationId, createObservabilityInterceptor } from './interceptors';

export { reportError, type ErrorReport, type ErrorContext } from './reporter';
