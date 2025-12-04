/**
 * Convert a snake_case string to camelCase.
 *
 * @example
 * snakeToCamel('created_at') // 'createdAt'
 * snakeToCamel('full_name') // 'fullName'
 */
export function snakeToCamel(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

/**
 * Convert a camelCase string to snake_case.
 *
 * @example
 * camelToSnake('createdAt') // 'created_at'
 * camelToSnake('fullName') // 'full_name'
 */
export function camelToSnake(str: string): string {
  return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
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
