/**
 * Correlation ID management for request tracing.
 *
 * Correlation IDs are propagated across frontend requests to enable
 * end-to-end request tracing in the backend.
 */

/** HTTP header name for correlation ID */
export const CORRELATION_ID_HEADER = 'X-Correlation-ID';

/** Storage key for current correlation ID */
const CORRELATION_ID_KEY = 'syft_correlation_id';

/**
 * Generate a new correlation ID using crypto.randomUUID().
 *
 * @returns A new UUID v4 correlation ID
 */
export function generateCorrelationId(): string {
  // Use native crypto.randomUUID() which is available in all modern browsers
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  // Fallback for older environments (very unlikely in modern browsers)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replaceAll(/[xy]/g, (c) => {
    const r = Math.trunc(Math.random() * 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Get or create a correlation ID for the current session.
 *
 * If a correlation ID exists in session storage, it is returned.
 * Otherwise, a new one is generated and stored.
 *
 * @returns The current correlation ID
 */
export function getOrCreateCorrelationId(): string {
  try {
    let correlationId = sessionStorage.getItem(CORRELATION_ID_KEY);
    if (!correlationId) {
      correlationId = generateCorrelationId();
      sessionStorage.setItem(CORRELATION_ID_KEY, correlationId);
    }
    return correlationId;
  } catch {
    // Fallback if sessionStorage is not available
    return generateCorrelationId();
  }
}

/**
 * Get the current correlation ID without generating a new one.
 *
 * @returns The current correlation ID or null if not set
 */
export function getCorrelationId(): string | null {
  try {
    return sessionStorage.getItem(CORRELATION_ID_KEY);
  } catch {
    return null;
  }
}

/**
 * Set a specific correlation ID.
 *
 * @param correlationId - The correlation ID to set
 */
export function setCorrelationId(correlationId: string): void {
  try {
    sessionStorage.setItem(CORRELATION_ID_KEY, correlationId);
  } catch {
    // Ignore if sessionStorage is not available
  }
}

/**
 * Clear the current correlation ID.
 *
 * Call this to generate a new correlation ID for the next request chain.
 */
export function clearCorrelationId(): void {
  try {
    sessionStorage.removeItem(CORRELATION_ID_KEY);
  } catch {
    // Ignore if sessionStorage is not available
  }
}

/**
 * Rotate the correlation ID.
 *
 * Generates a new correlation ID and returns it.
 * Use this when starting a new user action/flow.
 *
 * @returns The new correlation ID
 */
export function rotateCorrelationId(): string {
  const newId = generateCorrelationId();
  setCorrelationId(newId);
  return newId;
}
