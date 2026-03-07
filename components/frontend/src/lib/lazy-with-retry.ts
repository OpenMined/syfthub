import { lazy } from 'react';

import type { ComponentType } from 'react';

const RETRY_KEY = 'chunk-reload-ts';
const RETRY_WINDOW_MS = 10_000; // 10 seconds

/**
 * Wrapper around React.lazy that auto-reloads the page on chunk load failure.
 *
 * After a deployment, old chunk files (with content hashes) no longer exist.
 * Users with the app already open will fail to load lazy chunks on navigation.
 * This wrapper detects that failure and reloads the page once to fetch the
 * fresh index.html (which references the new chunk filenames).
 *
 * Uses sessionStorage with a timestamp to prevent infinite reload loops:
 * if a reload happened within the last 10 seconds and the chunk still fails,
 * the error is thrown to the error boundary instead of reloading again.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyWithRetry<T extends ComponentType<any>>(
  importFunction: () => Promise<{ default: T }>
) {
  return lazy(async () => {
    try {
      const module = await importFunction();
      // Chunk loaded successfully — clear any reload flag
      sessionStorage.removeItem(RETRY_KEY);
      return module;
    } catch (error) {
      const lastReload = Number(sessionStorage.getItem(RETRY_KEY) ?? '0');
      const recentlyReloaded = Date.now() - lastReload < RETRY_WINDOW_MS;

      if (!recentlyReloaded) {
        // First failure — reload to get fresh chunk manifest
        sessionStorage.setItem(RETRY_KEY, String(Date.now()));
        globalThis.location.reload();
        // Return a never-resolving promise so the error boundary doesn't flash
        // eslint-disable-next-line @typescript-eslint/no-empty-function
        return new Promise<never>(() => {});
      }

      // Already reloaded recently and chunk still fails — give up
      sessionStorage.removeItem(RETRY_KEY);
      throw error;
    }
  });
}
