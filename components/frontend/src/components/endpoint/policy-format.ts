// Shared formatting helpers for policy config display, used by the generic
// policy card and the policy-item label fallback.

/** Format a cost value for display, scaling per-token/per-query for readability. */
export function formatCost(value: number, unit: string): string {
  if (unit === 'token' || unit === 'tokens') {
    // Convert per-token cost to per-million tokens for readability
    const perMillion = value * 1_000_000;
    if (perMillion < 0.01) {
      return `$${(perMillion * 1000).toFixed(2)} / 1B`;
    }
    return `$${perMillion.toFixed(2)} / 1M`;
  }
  if (unit === 'query' || unit === 'queries') {
    // Convert per-query cost to per-thousand queries
    const perThousand = value * 1000;
    return `$${perThousand.toFixed(2)} / 1K`;
  }
  // Default: show as-is with 6 decimal places
  return `$${value.toFixed(6)}`;
}

/** Humanize a snake_case / camelCase config key for display. */
export function formatConfigKey(key: string): string {
  return key
    .replaceAll('_', ' ')
    .replaceAll(/([A-Z])/g, ' $1')
    .replaceAll(/^./g, (firstChar) => firstChar.toUpperCase())
    .trim();
}
