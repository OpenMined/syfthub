/**
 * Integration tests for HubResource.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  createTestClient,
  createAuthenticatedClient,
  generateTestEndpoint,
  isTestServerAvailable,
} from '../setup.js';
import { Visibility } from '../../src/index.js';

describe('HubResource', () => {
  beforeAll(async () => {
    const available = await isTestServerAvailable();
    if (!available) {
      console.warn('Test server not available, skipping integration tests');
    }
  });

  describe('browse', () => {
    it('should browse public endpoints without auth', async () => {
      // First, create some public endpoints
      const { client: authClient, credentials } = await createAuthenticatedClient();
      await authClient.myEndpoints.create({
        ...generateTestEndpoint(),
        visibility: Visibility.PUBLIC,
      });

      // Browse without auth
      const client = createTestClient();
      const endpoints = await client.hub.browse().take(10);

      // Should get some endpoints
      expect(Array.isArray(endpoints)).toBe(true);
    });

    it('should paginate browse results', async () => {
      const client = createTestClient();

      const firstPage = await client.hub.browse({ pageSize: 5 }).firstPage();

      expect(firstPage.length).toBeLessThanOrEqual(5);
    });

    it('should iterate through pages', async () => {
      const client = createTestClient();

      // Get first 10 endpoints
      const endpoints = await client.hub.browse({ pageSize: 5 }).take(10);

      expect(endpoints.length).toBeLessThanOrEqual(10);
    });
  });

  describe('trending', () => {
    it('should get trending endpoints', async () => {
      const client = createTestClient();

      const trending = await client.hub.trending().take(10);

      expect(Array.isArray(trending)).toBe(true);
    });

    it('should filter by minimum stars', async () => {
      const client = createTestClient();

      const trending = await client.hub.trending({ minStars: 0 }).take(10);

      // All should have at least 0 stars (trivial but tests the param)
      for (const ep of trending) {
        expect(ep.starsCount).toBeGreaterThanOrEqual(0);
      }
    });
  });

  describe('get', () => {
    it('should get endpoint by path', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      // Get via hub (public access)
      const hubClient = createTestClient();
      const fetched = await hubClient.hub.get(path);

      expect(fetched.name).toBe(created.name);
      expect(fetched.slug).toBe(created.slug);
      expect(fetched.ownerUsername).toBe(credentials.username);
    });

    it('should include path helper', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      const hubClient = createTestClient();
      const fetched = await hubClient.hub.get(path);

      // Test the path property
      expect(`${fetched.ownerUsername}/${fetched.slug}`).toBe(path);
    });
  });

  describe('star/unstar', () => {
    it('should star an endpoint', async () => {
      // Create endpoint with one user
      const { client: creator, credentials: creatorCreds } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();
      const created = await creator.myEndpoints.create(endpointData);
      const path = `${creatorCreds.username}/${created.slug}`;

      // Star with another user
      const { client: starrer } = await createAuthenticatedClient();

      await starrer.hub.star(path);

      const isStarred = await starrer.hub.isStarred(path);
      expect(isStarred).toBe(true);
    });

    it('should unstar an endpoint', async () => {
      // Create endpoint with one user
      const { client: creator, credentials: creatorCreds } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();
      const created = await creator.myEndpoints.create(endpointData);
      const path = `${creatorCreds.username}/${created.slug}`;

      // Star then unstar with another user
      const { client: starrer } = await createAuthenticatedClient();

      await starrer.hub.star(path);
      expect(await starrer.hub.isStarred(path)).toBe(true);

      await starrer.hub.unstar(path);
      expect(await starrer.hub.isStarred(path)).toBe(false);
    });

    it('should check if starred', async () => {
      // Create endpoint
      const { client: creator, credentials: creatorCreds } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();
      const created = await creator.myEndpoints.create(endpointData);
      const path = `${creatorCreds.username}/${created.slug}`;

      // Check with another user (not starred yet)
      const { client: checker } = await createAuthenticatedClient();

      const isStarred = await checker.hub.isStarred(path);
      expect(isStarred).toBe(false);
    });
  });
});
