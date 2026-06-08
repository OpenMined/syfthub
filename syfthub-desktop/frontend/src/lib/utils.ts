import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Display labels for endpoint types. */
export const typeLabels: Record<string, string> = {
  model: 'Model',
  data_source: 'Data Source',
  model_data_source: 'Model + Data Source',
  agent: 'Agent',
};

/** Short labels for compact spaces (sidebar badges). */
export const typeLabelsShort: Record<string, string> = {
  model: 'Model',
  data_source: 'Source',
  model_data_source: 'Hybrid',
  agent: 'Agent',
};

/** Check whether a string is a valid URL. */
export function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

// Non-backtracking pattern (no nested quantifiers) — a UX gate only; the
// backend's EmailStr is the real validator.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_PATTERN.test(email.trim());
}

/** Default SyftHub server URL used by onboarding. */
export const DEFAULT_SYFTHUB_URL = 'https://syfthub-dev.openmined.org';

/** Env var keys that need multiline (textarea) rendering in forms. */
export const MULTILINE_ENV_KEYS = new Set(['SYSTEM_PROMPT']);

/** Extract a human-readable message from an unknown caught error. */
export function extractErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** Format an ISO timestamp as a full, human-readable date-time. Returns the
 *  input unchanged when it is not a parseable date. */
export function formatFullTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** Format a byte count in human-readable units (B/KB/MB/GB). */
export function formatBytes(n?: number): string {
  if (!n || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return v.toFixed(v < 10 ? 1 : 0) + ' ' + units[i];
}
