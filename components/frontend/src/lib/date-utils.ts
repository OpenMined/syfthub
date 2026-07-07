/**
 * Date formatting utilities shared across the frontend.
 *
 * Consolidates formatRelativeTime and formatDate which were previously
 * duplicated across endpoint-utils, search-service, api-tokens-settings-tab,
 * security-settings-tab, and profile-view.
 */

/**
 * Format a date as a short absolute date string.
 * Example: "Dec 1, 2024"
 */
export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

/**
 * Format a date as a long absolute date string.
 * Example: "December 1, 2024"
 */
export function formatDateLong(date: Date | string): string {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
}

/**
 * Format a date as a human-readable relative time string.
 * Examples: "just now", "2 minutes ago", "3 hours ago", "5 days ago",
 *           "2 weeks ago", "3 months ago"
 */
export function formatRelativeTime(date: Date | string): string {
  const d = new Date(date);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${String(diffMins)} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${String(diffHours)} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${String(diffDays)} day${diffDays === 1 ? '' : 's'} ago`;

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffDays < 30) return `${String(diffWeeks)} week${diffWeeks === 1 ? '' : 's'} ago`;

  const diffMonths = Math.floor(diffDays / 30);
  return `${String(diffMonths)} month${diffMonths === 1 ? '' : 's'} ago`;
}
