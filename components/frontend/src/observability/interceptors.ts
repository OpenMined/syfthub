/**
 * Request interceptors for observability.
 *
 * Provides utilities to attach correlation IDs to outgoing requests.
 */

import { CORRELATION_ID_HEADER, getOrCreateCorrelationId } from './correlation';
import { logger } from './logger';

/**
 * Attach correlation ID to a fetch RequestInit config.
 *
 * @param config - The fetch RequestInit configuration
 * @returns Updated configuration with correlation ID header
 *
 * @example
 * const response = await fetch('/api/users', attachCorrelationId({
 *   method: 'GET',
 * }));
 */
export function attachCorrelationId(config: RequestInit = {}): RequestInit {
  const correlationId = getOrCreateCorrelationId();

  const headers = new Headers(config.headers);
  headers.set(CORRELATION_ID_HEADER, correlationId);

  return {
    ...config,
    headers
  };
}

/**
 * Create a fetch wrapper that automatically attaches correlation IDs.
 *
 * @param baseFetch - The fetch function to wrap (defaults to global fetch)
 * @returns Wrapped fetch function
 *
 * @example
 * const tracedFetch = createObservabilityInterceptor();
 * const response = await tracedFetch('/api/users');
 */
export function createObservabilityInterceptor(baseFetch: typeof fetch = fetch): typeof fetch {
  return async function tracedFetch(
    input: RequestInfo | URL,
    init?: RequestInit
  ): Promise<Response> {
    const correlationId = getOrCreateCorrelationId();
    const startTime = performance.now();

    // Prepare request with correlation ID
    const headers = new Headers(init?.headers);
    headers.set(CORRELATION_ID_HEADER, correlationId);

    const config: RequestInit = {
      ...init,
      headers
    };

    // Extract URL for logging
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

    const method = config.method ?? 'GET';

    logger.debug('http.request.started', {
      url,
      method
    });

    try {
      const response = await baseFetch(input, config);
      const duration = Math.round(performance.now() - startTime);

      // Log based on status code
      if (response.ok) {
        logger.debug('http.request.completed', {
          url,
          method,
          status: response.status,
          durationMs: duration
        });
      } else {
        logger.warn('http.request.failed', {
          url,
          method,
          status: response.status,
          durationMs: duration
        });
      }

      return response;
    } catch (error) {
      const duration = Math.round(performance.now() - startTime);

      logger.error(
        'http.request.error',
        {
          url,
          method,
          durationMs: duration
        },
        error instanceof Error ? error : new Error(String(error))
      );

      throw error;
    }
  };
}

/**
 * Headers helper to add correlation ID to existing headers.
 *
 * @param existingHeaders - Existing headers (optional)
 * @returns Headers with correlation ID added
 */
export function withCorrelationId(existingHeaders?: HeadersInit): Headers {
  const headers = new Headers(existingHeaders);
  headers.set(CORRELATION_ID_HEADER, getOrCreateCorrelationId());
  return headers;
}
