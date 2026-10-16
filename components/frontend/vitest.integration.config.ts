import path from 'node:path';

import { defineConfig } from 'vitest/config';

/**
 * The API client's integration tests. They need a running Hub, named by SYFTHUB_URL, and run
 * under node rather than jsdom: `npx vitest run --config vitest.integration.config.ts`.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.integration.ts'],
    testTimeout: 30_000
  }
});
