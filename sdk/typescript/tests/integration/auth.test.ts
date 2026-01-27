/**
 * Integration tests for AuthResource.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  createTestClient,
  createAuthenticatedClient,
  generateTestUser,
  isTestServerAvailable,
} from '../setup.js';
import { AuthenticationError, ValidationError } from '../../src/index.js';

describe('AuthResource', () => {
  beforeAll(async () => {
    const available = await isTestServerAvailable();
    if (!available) {
      console.warn('Test server not available, skipping integration tests');
    }
  });

  describe('register', () => {
    it('should register a new user', async () => {
      const client = createTestClient();
      const userData = generateTestUser();

      const user = await client.auth.register(userData);

      expect(user).toBeDefined();
      expect(user.username).toBe(userData.username);
      expect(user.email).toBe(userData.email);
      expect(user.fullName).toBe(userData.fullName);
      expect(client.isAuthenticated).toBe(true);
    });

    it('should fail with duplicate username', async () => {
      const client = createTestClient();
      const userData = generateTestUser();

      // Register first user
      await client.auth.register(userData);

      // Create new client and try to register with same username
      const client2 = createTestClient();
      const duplicateData = {
        ...generateTestUser(),
        username: userData.username, // Same username
      };

      await expect(client2.auth.register(duplicateData)).rejects.toThrow();
    });

    it('should fail with invalid password', async () => {
      const client = createTestClient();
      const userData = generateTestUser();
      userData.password = 'short'; // Too short

      await expect(client.auth.register(userData)).rejects.toThrow(ValidationError);
    });
  });

  describe('login', () => {
    it('should login with valid credentials', async () => {
      const client = createTestClient();
      const userData = generateTestUser();

      // Register first
      await client.auth.register(userData);

      // Logout
      await client.auth.logout();
      expect(client.isAuthenticated).toBe(false);

      // Login again
      const user = await client.auth.login(userData.username, userData.password);

      expect(user).toBeDefined();
      expect(user.username).toBe(userData.username);
      expect(client.isAuthenticated).toBe(true);
    });

    it('should login with email', async () => {
      const client = createTestClient();
      const userData = generateTestUser();

      await client.auth.register(userData);
      await client.auth.logout();

      // Login with email instead of username
      const user = await client.auth.login(userData.email, userData.password);

      expect(user).toBeDefined();
      expect(user.email).toBe(userData.email);
    });

    it('should fail with wrong password', async () => {
      const client = createTestClient();
      const userData = generateTestUser();

      await client.auth.register(userData);
      await client.auth.logout();

      await expect(client.auth.login(userData.username, 'wrongpassword')).rejects.toThrow(
        AuthenticationError
      );
    });

    it('should fail with non-existent user', async () => {
      const client = createTestClient();

      await expect(client.auth.login('nonexistent_user_12345', 'password123')).rejects.toThrow(
        AuthenticationError
      );
    });
  });

  describe('me', () => {
    it('should return current user', async () => {
      const { client, user: _registeredUser, credentials } = await createAuthenticatedClient();

      const me = await client.auth.me();

      expect(me).toBeDefined();
      expect(me.username).toBe(credentials.username);
      expect(me.email).toBe(credentials.email);
    });

    it('should fail when not authenticated', async () => {
      const client = createTestClient();

      await expect(client.auth.me()).rejects.toThrow(AuthenticationError);
    });
  });

  describe('logout', () => {
    it('should clear authentication', async () => {
      const { client } = await createAuthenticatedClient();

      expect(client.isAuthenticated).toBe(true);

      await client.auth.logout();

      expect(client.isAuthenticated).toBe(false);
    });
  });

  describe('changePassword', () => {
    it('should change password successfully', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const newPassword = 'NewPassword456!';

      await client.auth.changePassword(credentials.password, newPassword);

      // Logout and login with new password
      await client.auth.logout();
      const user = await client.auth.login(credentials.username, newPassword);

      expect(user).toBeDefined();
    });

    it('should fail with wrong current password', async () => {
      const { client } = await createAuthenticatedClient();

      await expect(
        client.auth.changePassword('wrongpassword', 'NewPassword456!')
      ).rejects.toThrow();
    });
  });

  describe('token persistence', () => {
    it('should save and restore tokens', async () => {
      const { client, credentials } = await createAuthenticatedClient();

      // Get tokens
      const tokens = client.getTokens();
      expect(tokens).not.toBeNull();
      expect(tokens?.accessToken).toBeDefined();
      expect(tokens?.refreshToken).toBeDefined();

      // Create new client and set tokens
      const client2 = createTestClient();
      expect(client2.isAuthenticated).toBe(false);

      client2.setTokens(tokens!);
      expect(client2.isAuthenticated).toBe(true);

      // Should be able to get current user
      const me = await client2.auth.me();
      expect(me.username).toBe(credentials.username);
    });
  });
});
