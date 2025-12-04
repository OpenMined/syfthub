/**
 * Test setup and utilities for integration tests.
 */

import { SyftHubClient } from '../src/index.js';

/**
 * Generate a random string for unique test data.
 */
export function randomString(length = 8): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * Generate unique test user data.
 */
export function generateTestUser() {
  const id = randomString(8);
  return {
    username: `testuser_${id}`,
    email: `testuser_${id}@test.example.com`,
    password: 'TestPassword123!',
    fullName: `Test User ${id}`,
  };
}

/**
 * Generate unique test endpoint data.
 */
export function generateTestEndpoint() {
  const id = randomString(8);
  return {
    name: `Test Endpoint ${id}`,
    type: 'model' as const,
    visibility: 'public' as const,
    description: `A test endpoint ${id}`,
    readme: `# Test Endpoint\n\nThis is a test endpoint ${id}.`,
  };
}

/**
 * Get the test server URL from environment.
 */
export function getTestServerUrl(): string | undefined {
  return process.env.SYFTHUB_URL || process.env.SYFTHUB_TEST_URL;
}

/**
 * Check if the test server is available.
 */
export async function isTestServerAvailable(): Promise<boolean> {
  const url = getTestServerUrl();
  if (!url) return false;

  try {
    const response = await fetch(`${url}/health`, { method: 'GET' });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Create a new client for testing.
 */
export function createTestClient(): SyftHubClient {
  const url = getTestServerUrl();
  if (!url) {
    throw new Error('SYFTHUB_URL or SYFTHUB_TEST_URL must be set for integration tests');
  }
  return new SyftHubClient({ baseUrl: url, timeout: 30000 });
}

/**
 * Create a client and register a new test user.
 * Returns the client (authenticated) and the user credentials.
 */
export async function createAuthenticatedClient() {
  const client = createTestClient();
  const credentials = generateTestUser();
  const user = await client.auth.register(credentials);
  return { client, user, credentials };
}
