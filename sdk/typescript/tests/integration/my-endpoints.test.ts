/**
 * Integration tests for MyEndpointsResource.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  createAuthenticatedClient,
  generateTestEndpoint,
  isTestServerAvailable,
} from '../setup.js';
import { EndpointType, Visibility, NotFoundError } from '../../src/index.js';

describe('MyEndpointsResource', () => {
  beforeAll(async () => {
    const available = await isTestServerAvailable();
    if (!available) {
      console.warn('Test server not available, skipping integration tests');
    }
  });

  describe('create', () => {
    it('should create a new endpoint', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const endpoint = await client.myEndpoints.create(endpointData);

      expect(endpoint).toBeDefined();
      expect(endpoint.name).toBe(endpointData.name);
      expect(endpoint.type).toBe(endpointData.type);
      expect(endpoint.visibility).toBe(endpointData.visibility);
      expect(endpoint.description).toBe(endpointData.description);
      expect(endpoint.slug).toBeDefined();
      expect(endpoint.id).toBeDefined();
    });

    it('should create endpoint with custom slug', async () => {
      const { client } = await createAuthenticatedClient();
      const endpointData = {
        ...generateTestEndpoint(),
        slug: `custom-slug-${Date.now()}`,
      };

      const endpoint = await client.myEndpoints.create(endpointData);

      expect(endpoint.slug).toBe(endpointData.slug);
    });

    it('should create private endpoint', async () => {
      const { client } = await createAuthenticatedClient();
      const endpointData = {
        ...generateTestEndpoint(),
        visibility: Visibility.PRIVATE,
      };

      const endpoint = await client.myEndpoints.create(endpointData);

      expect(endpoint.visibility).toBe('private');
    });
  });

  describe('list', () => {
    it('should list user endpoints', async () => {
      const { client } = await createAuthenticatedClient();

      // Create a few endpoints
      await client.myEndpoints.create(generateTestEndpoint());
      await client.myEndpoints.create(generateTestEndpoint());

      const endpoints = await client.myEndpoints.list().all();

      expect(endpoints.length).toBeGreaterThanOrEqual(2);
    });

    it('should filter by visibility', async () => {
      const { client } = await createAuthenticatedClient();

      // Create public and private endpoints
      await client.myEndpoints.create({
        ...generateTestEndpoint(),
        visibility: Visibility.PUBLIC,
      });
      await client.myEndpoints.create({
        ...generateTestEndpoint(),
        visibility: Visibility.PRIVATE,
      });

      const publicEndpoints = await client.myEndpoints
        .list({ visibility: Visibility.PUBLIC })
        .all();

      for (const ep of publicEndpoints) {
        expect(ep.visibility).toBe('public');
      }
    });

    it('should paginate results', async () => {
      const { client } = await createAuthenticatedClient();

      // Create endpoints
      for (let i = 0; i < 5; i++) {
        await client.myEndpoints.create(generateTestEndpoint());
      }

      // Get first page with small page size
      const firstPage = await client.myEndpoints.list({ pageSize: 2 }).firstPage();

      expect(firstPage.length).toBeLessThanOrEqual(2);
    });

    it('should iterate through all pages', async () => {
      const { client } = await createAuthenticatedClient();

      // Create endpoints
      for (let i = 0; i < 5; i++) {
        await client.myEndpoints.create(generateTestEndpoint());
      }

      // Count using async iteration
      let count = 0;
      for await (const _ of client.myEndpoints.list({ pageSize: 2 })) {
        count++;
      }

      expect(count).toBeGreaterThanOrEqual(5);
    });
  });

  describe('get', () => {
    it('should get endpoint by path', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      const fetched = await client.myEndpoints.get(path);

      expect(fetched.id).toBe(created.id);
      expect(fetched.name).toBe(created.name);
    });

    it('should fail for non-existent endpoint', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const path = `${credentials.username}/nonexistent-endpoint-12345`;

      await expect(client.myEndpoints.get(path)).rejects.toThrow(NotFoundError);
    });
  });

  describe('update', () => {
    it('should update endpoint', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      const newDescription = 'Updated description';
      const updated = await client.myEndpoints.update(path, {
        description: newDescription,
      });

      expect(updated.description).toBe(newDescription);
      expect(updated.name).toBe(created.name); // Unchanged
    });

    it('should update visibility', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = {
        ...generateTestEndpoint(),
        visibility: Visibility.PUBLIC,
      };

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      const updated = await client.myEndpoints.update(path, {
        visibility: Visibility.PRIVATE,
      });

      expect(updated.visibility).toBe('private');
    });
  });

  describe('delete', () => {
    it('should delete endpoint', async () => {
      const { client, credentials } = await createAuthenticatedClient();
      const endpointData = generateTestEndpoint();

      const created = await client.myEndpoints.create(endpointData);
      const path = `${credentials.username}/${created.slug}`;

      await client.myEndpoints.delete(path);

      // Should not be able to get it anymore
      await expect(client.myEndpoints.get(path)).rejects.toThrow(NotFoundError);
    });
  });
});
