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

/** Extract a human-readable message from an unknown caught error. */
export function extractErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}
