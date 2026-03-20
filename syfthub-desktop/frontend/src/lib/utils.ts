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
