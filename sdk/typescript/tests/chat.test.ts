/**
 * Unit tests for ChatResource.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SyftHubClient } from '../src/client.js';
import type { EndpointRef } from '../src/models/index.js';
import {
  AggregatorError,
  EndpointResolutionError,
  AuthenticationError,
} from '../src/index.js';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('ChatResource', () => {
  const baseUrl = 'https://test.syfthub.com';
  const _aggregatorUrl = `${baseUrl}/aggregator/api/v1`;
  let client: SyftHubClient;

  const mockUserResponse = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    full_name: 'Test User',
    is_active: true,
    role: 'user',
    created_at: new Date().toISOString(),
  };

  const mockEndpointPublic = {
    name: 'Test Model',
    slug: 'test-model',
    type: 'model',
    owner_username: 'alice',
    description: 'A test model',
    version: '1.0.0',
    stars_count: 10,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    connect: [
      {
        type: 'syftai',
        enabled: true,
        description: 'SyftAI Space connection',
        config: {
          url: 'http://syftai:8080',
          tenant_name: 'default',
        },
      },
    ],
  };

  const mockChatResponse = {
    response: 'Machine learning is a subset of AI that enables systems to learn from data.',
    sources: {
      'ML Overview': {
        slug: 'alice/docs',
        content: 'Machine learning is a subset of artificial intelligence...',
      },
    },
    retrieval_info: [
      {
        path: 'alice/docs',
        documents_retrieved: 3,
        status: 'success',
      },
    ],
    metadata: {
      retrieval_time_ms: 150,
      generation_time_ms: 500,
      total_time_ms: 650,
    },
  };

  beforeEach(() => {
    mockFetch.mockReset();
    client = new SyftHubClient({ baseUrl });
    // Set tokens to simulate authenticated state
    client.setTokens({
      accessToken: 'fake-access-token',
      refreshToken: 'fake-refresh-token',
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('complete()', () => {
    it('should complete chat with EndpointRef', async () => {
      // Mock auth/me endpoint
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/chat') && !url.includes('/stream')) {
          return new Response(JSON.stringify(mockChatResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const modelRef: EndpointRef = {
        url: 'http://syftai:8080',
        slug: 'test-model',
        name: 'Test Model',
      };

      const response = await client.chat.complete({
        prompt: 'What is machine learning?',
        model: modelRef,
      });

      expect(response.response).toContain('Machine learning');
      expect(Object.keys(response.sources)).toHaveLength(1);
      expect(response.sources['ML Overview'].slug).toBe('alice/docs');
      expect(response.retrievalInfo).toHaveLength(1);
      expect(response.metadata.totalTimeMs).toBe(650);
    });

    it('should complete chat with string endpoint path', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        // Hub.get uses /{owner}/{slug} path
        if (url.endsWith('/alice/test-model')) {
          return new Response(JSON.stringify(mockEndpointPublic), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.endsWith('/alice/docs')) {
          return new Response(
            JSON.stringify({ ...mockEndpointPublic, slug: 'docs', type: 'data_source' }),
            { status: 200, headers: { 'content-type': 'application/json' } }
          );
        }
        if (url.includes('/chat') && !url.includes('/stream')) {
          return new Response(JSON.stringify(mockChatResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const response = await client.chat.complete({
        prompt: 'What is machine learning?',
        model: 'alice/test-model',
        dataSources: ['alice/docs'],
      });

      expect(response.response).toContain('Machine learning');
    });

    it('should require authentication', async () => {
      // Create unauthenticated client
      const unauthClient = new SyftHubClient({ baseUrl });

      await expect(
        unauthClient.chat.complete({
          prompt: 'Hello',
          model: { url: 'http://test', slug: 'model' },
        })
      ).rejects.toThrow(AuthenticationError);
    });

    it('should throw AggregatorError on server error', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/chat')) {
          return new Response(
            JSON.stringify({ message: 'Internal server error' }),
            { status: 500, headers: { 'content-type': 'application/json' } }
          );
        }
        return new Response('Not found', { status: 404 });
      });

      const modelRef: EndpointRef = { url: 'http://syftai:8080', slug: 'model' };

      await expect(
        client.chat.complete({ prompt: 'Hello', model: modelRef })
      ).rejects.toThrow(AggregatorError);
    });

    it('should throw EndpointResolutionError when endpoint not found', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.endsWith('/alice/nonexistent')) {
          return new Response(JSON.stringify({ detail: 'Not found' }), {
            status: 404,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      await expect(
        client.chat.complete({ prompt: 'Hello', model: 'alice/nonexistent' })
      ).rejects.toThrow(EndpointResolutionError);
    });
  });

  describe('stream()', () => {
    it('should require authentication for streaming', async () => {
      const unauthClient = new SyftHubClient({ baseUrl });

      await expect(async () => {
        for await (const _event of unauthClient.chat.stream({
          prompt: 'Hello',
          model: { url: 'http://test', slug: 'model' },
        })) {
          // consume
        }
      }).rejects.toThrow(AuthenticationError);
    });
  });

  describe('getAvailableModels()', () => {
    it('should return model endpoints with URLs', async () => {
      const endpoints = [
        { ...mockEndpointPublic, slug: 'model-1', type: 'model' },
        { ...mockEndpointPublic, slug: 'model-2', type: 'model' },
        { ...mockEndpointPublic, slug: 'datasource-1', type: 'data_source' },
      ];

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify(endpoints), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const models = await client.chat.getAvailableModels(10);

      expect(models).toHaveLength(2);
      expect(models.every((m) => m.type === 'model')).toBe(true);
    });
  });

  describe('getAvailableDataSources()', () => {
    it('should return data source endpoints with URLs', async () => {
      const endpoints = [
        { ...mockEndpointPublic, slug: 'ds-1', type: 'data_source' },
        { ...mockEndpointPublic, slug: 'model-1', type: 'model' },
      ];

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify(endpoints), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const sources = await client.chat.getAvailableDataSources(10);

      expect(sources).toHaveLength(1);
      expect(sources[0].type).toBe('data_source');
    });
  });
});
