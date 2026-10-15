// Per-key caches. Every request runs these over every key; the key-set is
// small (tens to low hundreds across a process lifetime) so an unbounded Map
// is fine and saves repeated regex work on hot paths.
const snakeToCamelCache = new Map<string, string>();
const camelToSnakeCache = new Map<string, string>();

/**
 * Convert a snake_case string to camelCase.
 *
 * @example
 * snakeToCamel('created_at') // 'createdAt'
 * snakeToCamel('full_name') // 'fullName'
 */
export function snakeToCamel(str: string): string {
  const cached = snakeToCamelCache.get(str);
  if (cached !== undefined) return cached;
  const result = str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
  snakeToCamelCache.set(str, result);
  return result;
}

/**
 * Convert a camelCase string to snake_case.
 *
 * @example
 * camelToSnake('createdAt') // 'created_at'
 * camelToSnake('fullName') // 'full_name'
 */
export function camelToSnake(str: string): string {
  const cached = camelToSnakeCache.get(str);
  if (cached !== undefined) return cached;
  const result = str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
  camelToSnakeCache.set(str, result);
  return result;
}

/**
 * Regular expression to match ISO 8601 date strings.
 */
const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

/**
 * Check if a value looks like an ISO date string.
 */
function isISODateString(value: unknown): value is string {
  return typeof value === 'string' && ISO_DATE_REGEX.test(value);
}

/**
 * Recursively transform object keys using the provided transformer function.
 * Optionally parses ISO date strings to Date objects.
 *
 * @param obj - The object to transform
 * @param keyTransformer - Function to transform each key
 * @param parseDates - Whether to parse ISO date strings to Date objects
 */
export function transformKeys<T>(
  obj: unknown,
  keyTransformer: (key: string) => string,
  parseDates = true
): T {
  // Handle null and undefined
  if (obj === null || obj === undefined) {
    return obj as T;
  }

  // Handle arrays
  if (Array.isArray(obj)) {
    return obj.map((item) => transformKeys(item, keyTransformer, parseDates)) as T;
  }

  // Serialize Date objects to ISO strings. Must come before the object branch,
  // which would otherwise enumerate a Date's (empty) own properties.
  if (obj instanceof Date) {
    return obj.toISOString() as T;
  }

  // Handle date strings
  if (parseDates && isISODateString(obj)) {
    return new Date(obj) as T;
  }

  // Handle objects
  if (typeof obj === 'object') {
    const transformed: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      transformed[keyTransformer(key)] = transformKeys(value, keyTransformer, parseDates);
    }
    return transformed as T;
  }

  // Return primitives as-is
  return obj as T;
}

/**
 * Convert all keys in an object from camelCase to snake_case.
 * Does not parse dates (for request bodies).
 */
export function toSnakeCase<T>(obj: unknown): T {
  return transformKeys<T>(obj, camelToSnake, false);
}

/**
 * Convert all keys in an object from snake_case to camelCase.
 * Parses ISO date strings to Date objects (for response bodies).
 */
export function toCamelCase<T>(obj: unknown): T {
  return transformKeys<T>(obj, snakeToCamel, true);
}

/**
 * Build URL search params from an object, filtering out undefined values.
 */
export function buildSearchParams(params: Record<string, unknown>): URLSearchParams {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      searchParams.append(camelToSnake(key), String(value));
    }
  }

  return searchParams;
}

/**
 * Parse a Server-Sent Events stream into event/data pairs.
 *
 * - Yields `{event, data}` on blank-line boundaries (SSE framing) OR after any
 *   `data:` line when no preceding `event:` has been seen (tolerates servers
 *   that emit only `data:` lines — fall back to `"message"`).
 * - Does NOT JSON.parse; callers parse their own schema.
 * - Flushes any pending event when the stream ends.
 */
export async function* readSSEEvents(
  response: Response
): AsyncGenerator<{ event: string; data: string }> {
  if (!response.body) return;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent: string | null = null;
  let currentData = '';

  const flush = function* (): Generator<{ event: string; data: string }> {
    if (currentData) {
      yield { event: currentEvent ?? 'message', data: currentData };
    }
    currentEvent = null;
    currentData = '';
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();

        if (!trimmed) {
          yield* flush();
          continue;
        }

        if (trimmed.startsWith('event:')) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith('data:')) {
          // If we already have buffered data without a blank-line terminator,
          // emit it now so data-only streams (no event: header) still flow.
          if (currentData && currentEvent === null) {
            yield* flush();
          }
          currentData = trimmed.slice(5).trim();
        }
      }
    }

    // Process any trailing line still in the buffer.
    const trailing = buffer.trim();
    if (trailing) {
      if (trailing.startsWith('event:')) {
        currentEvent = trailing.slice(6).trim();
      } else if (trailing.startsWith('data:')) {
        if (currentData && currentEvent === null) {
          yield* flush();
        }
        currentData = trailing.slice(5).trim();
      }
    }
    yield* flush();
  } finally {
    reader.releaseLock();
  }
}
