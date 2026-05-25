/**
 * Unit tests for ChatResource.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SyftHubClient } from '../src/client.js';
import type { EndpointRef } from '../src/models/index.js';
import { AggregatorError, ChatResource, EndpointResolutionError } from '../src/index.js';

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
      // Create mock endpoints for browse to return (use camelCase as HTTP client transforms responses)
      const mockModelEndpoint = {
        ...mockEndpointPublic,
        ownerUsername: 'alice',
        slug: 'test-model',
        type: 'model',
      };
      const mockDataSourceEndpoint = {
        ...mockEndpointPublic,
        ownerUsername: 'alice',
        slug: 'docs',
        type: 'data_source',
      };

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        // Hub.get uses browse() which calls /api/v1/endpoints/public - returns array directly
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify([mockModelEndpoint, mockDataSourceEndpoint]), {
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

      // Mock to return 401 for unauthenticated requests
      mockFetch.mockImplementation(async () => {
        return new Response(JSON.stringify({ detail: 'Not authenticated' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        });
      });

      // Chat methods throw AggregatorError for 401 (not AuthenticationError)
      await expect(
        unauthClient.chat.complete({
          prompt: 'Hello',
          model: { url: 'http://test', slug: 'model' },
        })
      ).rejects.toThrow(AggregatorError);
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
          return new Response(JSON.stringify({ message: 'Internal server error' }), {
            status: 500,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const modelRef: EndpointRef = { url: 'http://syftai:8080', slug: 'model' };

      await expect(client.chat.complete({ prompt: 'Hello', model: modelRef })).rejects.toThrow(
        AggregatorError
      );
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

      // Mock to return 401 for unauthenticated requests
      mockFetch.mockImplementation(async () => {
        return new Response(JSON.stringify({ detail: 'Not authenticated' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        });
      });

      // Chat methods throw AggregatorError for 401 (not AuthenticationError)
      await expect(async () => {
        for await (const _event of unauthClient.chat.stream({
          prompt: 'Hello',
          model: { url: 'http://test', slug: 'model' },
        })) {
          // consume
        }
      }).rejects.toThrow(AggregatorError);
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

  describe('tunneling detection', () => {
    it('should auto-fetch peer token for tunneling endpoints', async () => {
      const mockPeerTokenResponse = {
        peerToken: 'pt_test123',
        peerChannel: 'peer_abc',
        expiresIn: 120,
        natsUrl: 'ws://localhost:8080/nats',
      };

      mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/api/v1/peer-token')) {
          return new Response(JSON.stringify(mockPeerTokenResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/chat') && !url.includes('/stream')) {
          // Verify peer token is included in request body
          const body = JSON.parse(init?.body as string);
          expect(body.peer_token).toBe('pt_test123');
          expect(body.peer_channel).toBe('peer_abc');
          return new Response(JSON.stringify(mockChatResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const modelRef: EndpointRef = {
        url: 'tunneling:alice',
        slug: 'test-model',
        name: 'Tunneled Model',
        ownerUsername: 'alice',
      };

      const response = await client.chat.complete({
        prompt: 'Hello via tunnel',
        model: modelRef,
      });

      expect(response.response).toContain('Machine learning');

      // Verify peer-token endpoint was called
      const peerTokenCall = mockFetch.mock.calls.find(
        (call: unknown[]) => (call[0] as string).includes('/api/v1/peer-token')
      );
      expect(peerTokenCall).toBeDefined();
    });

    it('should not fetch peer token for non-tunneling endpoints', async () => {
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
      };

      await client.chat.complete({
        prompt: 'Hello',
        model: modelRef,
      });

      // Verify peer-token endpoint was NOT called
      const peerTokenCall = mockFetch.mock.calls.find(
        (call: unknown[]) => (call[0] as string).includes('/api/v1/peer-token')
      );
      expect(peerTokenCall).toBeUndefined();
    });

    it('should use provided peer token instead of auto-fetching', async () => {
      mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
        if (url.includes('/api/v1/auth/me')) {
          return new Response(JSON.stringify(mockUserResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/chat') && !url.includes('/stream')) {
          const body = JSON.parse(init?.body as string);
          expect(body.peer_token).toBe('custom_token');
          expect(body.peer_channel).toBe('custom_channel');
          return new Response(JSON.stringify(mockChatResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      const modelRef: EndpointRef = {
        url: 'tunneling:alice',
        slug: 'test-model',
      };

      await client.chat.complete({
        prompt: 'Hello',
        model: modelRef,
        peerToken: 'custom_token',
        peerChannel: 'custom_channel',
      });

      // Verify peer-token endpoint was NOT called (since token was provided)
      const peerTokenCall = mockFetch.mock.calls.find(
        (call: unknown[]) => (call[0] as string).includes('/api/v1/peer-token')
      );
      expect(peerTokenCall).toBeUndefined();
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

  // ============================================================================
  // parseSSEEvent - new event types
  // ============================================================================

  describe('parseSSEEvent — new event types', () => {
    /**
     * Build a ReadableStream<Uint8Array> from an array of SSE event descriptors,
     * followed by a done event so the generator terminates cleanly.
     */
    function makeSseStream(
      events: { event: string; data: Record<string, unknown> }[]
    ): ReadableStream<Uint8Array> {
      const encoder = new TextEncoder();
      const donePayload = {
        sources: {},
        retrieval_info: [],
        metadata: { retrieval_time_ms: 0, generation_time_ms: 0, total_time_ms: 0 },
      };
      const allEvents = [
        ...events,
        { event: 'done', data: donePayload },
      ];
      const sseText = allEvents
        .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
        .join('');
      return new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(sseText));
          controller.close();
        },
      });
    }

    /**
     * Mock fetch to return a SSE stream and collect all yielded events.
     */
    async function collectParseEvents(
      events: { event: string; data: Record<string, unknown> }[]
    ) {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/chat/stream')) {
          return new Response(makeSseStream(events), {
            status: 200,
            headers: { 'content-type': 'text/event-stream' },
          });
        }
        // Satisfy any auth calls in guest mode (should be none but just in case)
        return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
      });

      const collected = [];
      for await (const event of client.chat.stream({
        prompt: 'test query',
        model: { url: 'http://syftai:8080', slug: 'test-model' },
        guestMode: true,
        aggregatorUrl: baseUrl + '/aggregator/api/v1',
      })) {
        collected.push(event);
      }
      return collected;
    }

    it('parses reranking_start event with documents field', async () => {
      const events = await collectParseEvents([
        { event: 'retrieval_start', data: { sources: 1 } },
        { event: 'reranking_start', data: { documents: 7 } },
        { event: 'generation_start', data: {} },
        { event: 'token', data: { content: 'Hello' } },
      ]);

      const rerankingStart = events.find((e) => e.type === 'reranking_start');
      expect(rerankingStart).toBeDefined();
      expect(rerankingStart?.type).toBe('reranking_start');
      if (rerankingStart?.type === 'reranking_start') {
        expect(rerankingStart.documents).toBe(7);
      }
    });

    it('parses reranking_complete event with documents and timeMs fields', async () => {
      const events = await collectParseEvents([
        { event: 'reranking_start', data: { documents: 5 } },
        { event: 'reranking_complete', data: { documents: 5, time_ms: 1234 } },
        { event: 'generation_start', data: {} },
        { event: 'token', data: { content: 'Hi' } },
      ]);

      const rerankingComplete = events.find((e) => e.type === 'reranking_complete');
      expect(rerankingComplete).toBeDefined();
      expect(rerankingComplete?.type).toBe('reranking_complete');
      if (rerankingComplete?.type === 'reranking_complete') {
        expect(rerankingComplete.documents).toBe(5);
        expect(rerankingComplete.timeMs).toBe(1234);
      }
    });

    it('parses generation_heartbeat event with elapsedMs field (camelCased from elapsed_ms)', async () => {
      const events = await collectParseEvents([
        { event: 'generation_start', data: {} },
        { event: 'generation_heartbeat', data: { elapsed_ms: 3000 } },
        { event: 'generation_heartbeat', data: { elapsed_ms: 6000 } },
        { event: 'token', data: { content: 'Result' } },
      ]);

      const heartbeats = events.filter((e) => e.type === 'generation_heartbeat');
      expect(heartbeats).toHaveLength(2);
      if (heartbeats[0]?.type === 'generation_heartbeat') {
        expect(heartbeats[0].elapsedMs).toBe(3000);
      }
      if (heartbeats[1]?.type === 'generation_heartbeat') {
        expect(heartbeats[1].elapsedMs).toBe(6000);
      }
    });
  });

  // ============================================================================
  // collective path expansion
  // ============================================================================

  describe('collective path expansion', () => {
    const guestModel: EndpointRef = { url: 'http://syftai:8080', slug: 'test-model' };
    const guestOpts = {
      guestMode: true as const,
      aggregatorUrl: `${baseUrl}/aggregator/api/v1`,
    };

    it('should expand a single collective path to member endpoints', async () => {
      const mockAliceDocs = {
        name: 'Alice Docs',
        slug: 'docs',
        type: 'data_source',
        ownerUsername: 'alice',
        description: 'Alice data source',
        version: '1.0.0',
        stars_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        connect: [
          {
            type: 'syftai',
            enabled: true,
            description: 'Alice DS connection',
            config: { url: 'http://alice-ds:8080' },
          },
        ],
      };

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/collectives/by-slug/my-collective/endpoint-paths')) {
          return new Response(JSON.stringify(['alice/docs']), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify([mockAliceDocs]), {
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

      const response = await client.chat.complete({
        prompt: 'What is machine learning?',
        model: guestModel,
        dataSources: ['collective/my-collective'],
        ...guestOpts,
      });

      expect(response.response).toContain('Machine learning');

      // Collective endpoint-paths was called
      const collectiveCall = mockFetch.mock.calls.find((call: unknown[]) =>
        (call[0] as string).includes('/api/v1/collectives/by-slug/my-collective/endpoint-paths')
      );
      expect(collectiveCall).toBeDefined();
    });

    it('should throw EndpointResolutionError when collective slug is not found', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/collectives/by-slug/unknown-collective/endpoint-paths')) {
          return new Response(JSON.stringify({ detail: 'Collective not found' }), {
            status: 404,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response('Not found', { status: 404 });
      });

      await expect(
        client.chat.complete({
          prompt: 'Hello',
          model: guestModel,
          dataSources: ['collective/unknown-collective'],
          ...guestOpts,
        })
      ).rejects.toThrow(EndpointResolutionError);
    });

    it('should deduplicate paths when collective member appears as direct source', async () => {
      const mockAliceDocs = {
        name: 'Alice Docs',
        slug: 'docs',
        type: 'data_source',
        ownerUsername: 'alice',
        description: 'Alice data source',
        version: '1.0.0',
        stars_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        connect: [
          {
            type: 'syftai',
            enabled: true,
            description: 'Alice DS connection',
            config: { url: 'http://alice-ds:8080' },
          },
        ],
      };

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/collectives/by-slug/my-coll/endpoint-paths')) {
          return new Response(JSON.stringify(['alice/docs']), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify([mockAliceDocs]), {
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

      await client.chat.complete({
        prompt: 'Hello',
        model: guestModel,
        // alice/docs appears once via the collective and once as a direct path
        dataSources: ['collective/my-coll', 'alice/docs'],
        ...guestOpts,
      });

      // /api/v1/endpoints/public should only have been called once (deduplication)
      const publicCalls = mockFetch.mock.calls.filter((call: unknown[]) =>
        (call[0] as string).includes('/api/v1/endpoints/public')
      );
      expect(publicCalls).toHaveLength(1);
    });

    it('should pass non-collective string paths through unchanged', async () => {
      const mockAliceDocs = {
        name: 'Alice Docs',
        slug: 'docs',
        type: 'data_source',
        ownerUsername: 'alice',
        description: 'Alice data source',
        version: '1.0.0',
        stars_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        connect: [
          {
            type: 'syftai',
            enabled: true,
            description: 'Alice DS connection',
            config: { url: 'http://alice-ds:8080' },
          },
        ],
      };

      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify([mockAliceDocs]), {
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

      const response = await client.chat.complete({
        prompt: 'Hello',
        model: guestModel,
        dataSources: ['alice/docs'],
        ...guestOpts,
      });

      expect(response.response).toContain('Machine learning');

      // The collective endpoint-paths API must NOT have been called
      const collectiveCall = mockFetch.mock.calls.find((call: unknown[]) =>
        (call[0] as string).includes('/api/v1/collectives/by-slug/')
      );
      expect(collectiveCall).toBeUndefined();
    });

    it('should handle an empty collective (zero members)', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/collectives/by-slug/empty-coll/endpoint-paths')) {
          return new Response(JSON.stringify([]), {
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

      // Should complete without error even though collective has no members
      const response = await client.chat.complete({
        prompt: 'Hello',
        model: guestModel,
        dataSources: ['collective/empty-coll'],
        ...guestOpts,
      });

      expect(response.response).toContain('Machine learning');

      // The collective endpoint-paths API was called exactly once
      const collectiveCalls = mockFetch.mock.calls.filter((call: unknown[]) =>
        (call[0] as string).includes('/api/v1/collectives/by-slug/empty-coll/endpoint-paths')
      );
      expect(collectiveCalls).toHaveLength(1);
    });

    it('should expand collective/<slug>/<shared> to the shared-endpoint route', async () => {
      const mockAliceDocs = {
        name: 'Alice Docs',
        slug: 'docs',
        type: 'data_source',
        ownerUsername: 'alice',
        description: 'Alice data source',
        version: '1.0.0',
        stars_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        connect: [
          {
            type: 'syftai',
            enabled: true,
            description: 'Alice DS connection',
            config: { url: 'http://alice-ds:8080' },
          },
        ],
      };

      mockFetch.mockImplementation(async (url: string) => {
        if (
          url.includes(
            '/api/v1/collectives/by-slug/my-coll/shared-endpoints/health-news/endpoint-paths'
          )
        ) {
          return new Response(JSON.stringify(['alice/docs']), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          });
        }
        if (url.includes('/api/v1/endpoints/public')) {
          return new Response(JSON.stringify([mockAliceDocs]), {
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

      await client.chat.complete({
        prompt: 'Hello',
        model: guestModel,
        dataSources: ['collective/my-coll/health-news'],
        ...guestOpts,
      });

      const sharedCall = mockFetch.mock.calls.find((call: unknown[]) =>
        (call[0] as string).includes(
          '/api/v1/collectives/by-slug/my-coll/shared-endpoints/health-news/endpoint-paths'
        )
      );
      expect(sharedCall).toBeDefined();

      // The non-shared endpoint-paths route must NOT have been called.
      const defaultCall = mockFetch.mock.calls.find(
        (call: unknown[]) =>
          (call[0] as string).endsWith('/api/v1/collectives/by-slug/my-coll/endpoint-paths')
      );
      expect(defaultCall).toBeUndefined();
    });

    it('should treat collective/<slug>/all as an alias for the no-subset form', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (
          url.endsWith('/api/v1/collectives/by-slug/my-coll/endpoint-paths')
        ) {
          return new Response(JSON.stringify([]), {
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

      await client.chat.complete({
        prompt: 'Hello',
        model: guestModel,
        dataSources: ['collective/my-coll/all'],
        ...guestOpts,
      });

      // `/all` should NOT generate a shared-endpoints route — it falls back to
      // the no-subset endpoint-paths route so the backend can short-circuit.
      const sharedCall = mockFetch.mock.calls.find((call: unknown[]) =>
        (call[0] as string).includes(
          '/api/v1/collectives/by-slug/my-coll/shared-endpoints/all/endpoint-paths'
        )
      );
      expect(sharedCall).toBeUndefined();

      const defaultCall = mockFetch.mock.calls.find((call: unknown[]) =>
        (call[0] as string).endsWith('/api/v1/collectives/by-slug/my-coll/endpoint-paths')
      );
      expect(defaultCall).toBeDefined();
    });
  });
});

/**
 * Shared type-match test vectors — keep in sync across Go/Python/TypeScript SDKs.
 * These vectors ensure all three SDK implementations of typeMatches stay consistent.
 * Rules:
 *   1. Exact match always returns true
 *   2. model_data_source matches both model and data_source
 *   3. agent matches model (agents can be used where models are expected)
 *   4. All other cross-type combinations return false
 */
describe('typeMatches', () => {
  // Access the private static method via bracket notation for testing
  const typeMatches = (actualType: string, expectedType: string): boolean =>
    (ChatResource as unknown as Record<string, (a: string, b: string) => boolean>).typeMatches(
      actualType,
      expectedType
    );

  const testVectors: [string, string, boolean][] = [
    // Exact matches
    ['model', 'model', true],
    ['data_source', 'data_source', true],
    ['model_data_source', 'model_data_source', true],
    ['agent', 'agent', true],
    // model_data_source matches both model and data_source
    ['model_data_source', 'model', true],
    ['model_data_source', 'data_source', true],
    // agent matches model
    ['agent', 'model', true],
    // Cross-type mismatches
    ['model', 'data_source', false],
    ['data_source', 'model', false],
    ['model', 'agent', false],
    ['data_source', 'agent', false],
    ['model_data_source', 'agent', false],
    ['agent', 'data_source', false],
    ['model', 'model_data_source', false],
    ['data_source', 'model_data_source', false],
  ];

  it.each(testVectors)(
    'typeMatches(%s, %s) should return %s',
    (actualType, expectedType, want) => {
      expect(typeMatches(actualType, expectedType)).toBe(want);
    }
  );
});
