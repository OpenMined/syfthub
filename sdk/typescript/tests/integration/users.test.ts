/**
 * Integration tests for UsersResource.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  createTestClient,
  createAuthenticatedClient,
  isTestServerAvailable,
  randomString,
} from '../setup.js';
import { AuthenticationError } from '../../src/index.js';

describe('UsersResource', () => {
  beforeAll(async () => {
    const available = await isTestServerAvailable();
    if (!available) {
      console.warn('Test server not available, skipping integration tests');
    }
  });

  describe('update', () => {
    it('should update user profile', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const newFullName = `Updated Name ${randomString(4)}`;

      const updated = await client.users.update({
        fullName: newFullName,
      });

      expect(updated.fullName).toBe(newFullName);
      expect(updated.username).toBe(credentials.username); // Unchanged
    });

    it('should update avatar URL', async () => {
      const { client } = await createAuthenticatedClient();
      const avatarUrl = 'https://example.com/avatar.jpg';

      const updated = await client.users.update({
        avatarUrl,
      });

      expect(updated.avatarUrl).toBe(avatarUrl);
    });

    it('should fail when not authenticated', async () => {
      const client = createTestClient();

      await expect(client.users.update({ fullName: 'Test' })).rejects.toThrow(AuthenticationError);
    });
  });

  describe('checkUsername', () => {
    it('should return true for available username', async () => {
      const client = createTestClient();
      const username = `available_${randomString(10)}`;

      const available = await client.users.checkUsername(username);

      expect(available).toBe(true);
    });

    it('should return false for taken username', async () => {
      const { client, credentials } = await createAuthenticatedClient();

      // Check the username we just registered
      const available = await client.users.checkUsername(credentials.username);

      expect(available).toBe(false);
    });
  });

  describe('checkEmail', () => {
    it('should return true for available email', async () => {
      const client = createTestClient();
      const email = `available_${randomString(10)}@test.example.com`;

      const available = await client.users.checkEmail(email);

      expect(available).toBe(true);
    });

    it('should return false for taken email', async () => {
      const { client, credentials } = await createAuthenticatedClient();

      // Check the email we just registered
      const available = await client.users.checkEmail(credentials.email);

      expect(available).toBe(false);
    });
  });
});
