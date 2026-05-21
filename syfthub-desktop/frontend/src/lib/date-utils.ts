// Shared date/time formatting utilities. Three concerns live here:
//
//   - formatRelativeTime: human-friendly "Nm ago" buckets for recency.
//     Rolls over to an absolute time once entries are old enough that a
//     relative count loses meaning. Always uses Math.floor so a value
//     never rounds up into the next bucket and lies about freshness.
//   - formatShortTime: compact absolute formatting that elides redundant
//     parts (time only when same day; year only when different year).
//   - formatFullTimestamp: re-exported from ./utils so callers have one
//     import surface for "all date formatting".

import { formatFullTimestamp } from './utils';

export type DateInput = Date | string | number;

export interface RelativeTimeOptions {
  /** Reference instant for "now". Defaults to Date.now(). Exposed so tests
   *  and snapshots can pin time without mocking globals. */
  now?: number;
  /** Returned when the input fails to parse to a valid Date. Defaults to ''. */
  fallback?: string;
}

function toDate(input: DateInput): Date {
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);
  // Date.parse accepts ISO strings and many other shapes; new Date() forwards
  // them through the same parser but returns a Date directly.
  return new Date(input);
}

/** Format a date as a relative-time string with same-bucket honesty:
 *  always rounds down so "59s" never becomes "1m". Entries older than 24h
 *  roll over to formatShortTime so the value stays meaningful when the
 *  count would otherwise be misleading. */
export function formatRelativeTime(
  input: DateInput,
  opts?: RelativeTimeOptions,
): string {
  const fallback = opts?.fallback ?? '';
  const date = toDate(input);
  if (Number.isNaN(date.getTime())) return fallback;

  const now = opts?.now ?? Date.now();
  const seconds = Math.floor((now - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return formatShortTime(input, { now, fallback });
}

/** Format a date as a short absolute string. Same calendar day → HH:MM
 *  24-hour, e.g. "14:32". Same year → "Mon DD", e.g. "Mar 5". Else
 *  "Mon DD, YYYY", e.g. "Mar 5, 2024". */
export function formatShortTime(
  input: DateInput,
  opts?: { now?: number; fallback?: string },
): string {
  const fallback = opts?.fallback ?? '';
  const date = toDate(input);
  if (Number.isNaN(date.getTime())) return fallback;

  const nowDate = new Date(opts?.now ?? Date.now());
  const sameDay = date.toDateString() === nowDate.toDateString();
  if (sameDay) {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  const sameYear = date.getFullYear() === nowDate.getFullYear();
  return date.toLocaleDateString(
    'en-US',
    sameYear
      ? { month: 'short', day: 'numeric' }
      : { year: 'numeric', month: 'short', day: 'numeric' },
  );
}

export { formatFullTimestamp };
