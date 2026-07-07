/**
 * Unit tests for SearchResource (retrieval-only via the Aggregator).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SyftHubClient } from '../src/client.js';
import type { EndpointRef } from '../src/models/index.js';
import { AggregatorError, SearchResource } from '../src/index.js';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('SearchResource', () => {
  const baseUrl = 'https://test.syfthub.com';
  let client: SyftHubClient;

  const mockSearchResponse = {
    response: '',
    sources: {
      'EPFL News #1': { slug: 'epfl-news/epfl-news', content: 'First story.' },
      'EPFL News #2': { slug: 'epfl-news/epfl-news', content: 'Second story.' },
    },
    retrieval_info: [{ path: 'epfl-news/epfl-news', documents_retrieved: 2, status: 'success' }],
    metadata: { retrieval_time_ms: 120, generation_time_ms: 0, total_time_ms: 120 },
  };

  const dataSource: EndpointRef = {
    url: 'http://20.0.5.93:8081',
    slug: 'epfl-news',
    ownerUsername: 'epfl-news',
  };

  /** Default handler: satellite token + aggregator /chat. */
  function installDefaultFetch(): void {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/token')) {
        return new Response(JSON.stringify({ target_token: 'sat-tok' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      if (url.includes('/chat') && !url.includes('/stream')) {
        return new Response(JSON.stringify(mockSearchResponse), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response('Not found', { status: 404 });
    });
  }

  /** Pull the JSON body sent to the aggregator /chat endpoint. */
  function lastChatRequestBody(): Record<string, unknown> {
    const call = mockFetch.mock.calls.find(
      ([url]) => String(url).includes('/chat') && !String(url).includes('/stream')
    );
    if (!call) throw new Error('no /chat request was made');
    return JSON.parse((call[1] as RequestInit).body as string) as Record<string, unknown>;
  }

  beforeEach(() => {
    mockFetch.mockReset();
    client = new SyftHubClient({ baseUrl });
    client.setTokens({ accessToken: 'fake-access-token', refreshToken: 'fake-refresh-token' });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns parsed documents', async () => {
    installDefaultFetch();

    const result = await client.search.query({
      prompt: 'What happened?',
      dataSources: [dataSource],
    });

    expect(result.documents).toHaveLength(2);
    expect(result.documents.map((d) => d.content).sort()).toEqual([
      'First story.',
      'Second story.',
    ]);
    expect(result.documents[0].slug).toBe('epfl-news/epfl-news');
    expect(result.documents[0].title).toContain('EPFL News');
    expect(result.retrievalInfo[0].documentsRetrieved).toBe(2);
    expect(result.metadata.generationTimeMs).toBe(0);
  });

  it('sends retrieval_only and forwards the user token', async () => {
    installDefaultFetch();

    await client.search.query({ prompt: 'hi', dataSources: [dataSource] });

    const body = lastChatRequestBody();
    expect(body['retrieval_only']).toBe(true);
    expect(body['user_token']).toBe('fake-access-token');
    // Placeholder model present but empty (never contacted by the aggregator).
    expect((body['model'] as Record<string, unknown>)['url']).toBe('');
    expect((body['model'] as Record<string, unknown>)['slug']).toBe('');
  });

  it('omits user token in guest mode', async () => {
    installDefaultFetch();

    await client.search.query({ prompt: 'hi', dataSources: [dataSource], guestMode: true });

    const body = lastChatRequestBody();
    expect(body['retrieval_only']).toBe(true);
    expect(body['user_token']).toBeUndefined();
  });

  it('throws AggregatorError on failure', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/token')) {
        return new Response(JSON.stringify({ target_token: 'sat-tok' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ message: 'boom' }), {
        status: 500,
        headers: { 'content-type': 'application/json' },
      });
    });

    await expect(client.search.query({ prompt: 'hi', dataSources: [dataSource] })).rejects.toThrow(
      AggregatorError
    );
  });

  it('exposes a cached SearchResource', () => {
    expect(client.search).toBeInstanceOf(SearchResource);
    expect(client.search).toBe(client.search);
  });
});
