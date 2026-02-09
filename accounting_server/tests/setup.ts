/**
 * Jest Test Setup
 *
 * Global setup for all tests.
 */

// Set test environment
process.env['NODE_ENV'] = 'test';

// Global fetch mock setup (can be overridden in individual tests)
// Skip mocking for integration tests that need real HTTP calls
if (process.env['RUN_INTEGRATION_TESTS'] !== 'true') {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn();
}
