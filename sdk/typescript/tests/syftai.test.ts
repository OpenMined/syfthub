/**
 * Unit tests for SyftAIResource.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SyftHubClient } from '../src/client.js';
import { SyftAIResource, RetrievalError, GenerationError } from '../src/index.js';
import type { EndpointRef, Message } from '../src/models/index.js';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('SyftAIResource', () => {
  const baseUrl = 'https://test.syfthub.com';
  const syftaiUrl = 'http://syftai-space:8080';
  let client: SyftHubClient;

  const modelEndpoint: EndpointRef = {
    url: syftaiUrl,
    slug: 'test-model',
    name: 'Test Model',
    tenantName: 'default',
  };

  const dataSourceEndpoint: EndpointRef = {
    url: syftaiUrl,
    slug: 'test-docs',
    name: 'Test Docs',
    tenantName: 'default',
  };

  beforeEach(() => {
    mockFetch.mockReset();
    client = new SyftHubClient({ baseUrl });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('queryDataSource()', () => {
    it('should query data source successfully', async () => {
      const mockResponse = {
        documents: [
          {
            content: 'Machine learning is a type of AI.',
            score: 0.95,
            metadata: { source: 'ml-intro.txt' },
          },
          {
            content: 'Deep learning uses neural networks.',
            score: 0.87,
            metadata: { source: 'dl-basics.txt' },
          },
        ],
      };

      mockFetch.mockResolvedValueOnce(new Response(JSON.stringify(mockResponse), { status: 200 }));

      const docs = await client.syftai.queryDataSource({
        endpoint: dataSourceEndpoint,
        query: 'What is machine learning?',
        userEmail: 'test@example.com',
        topK: 5,
      });

      expect(docs).toHaveLength(2);
      expect(docs[0].content).toBe('Machine learning is a type of AI.');
      expect(docs[0].score).toBe(0.95);
      expect(docs[0].metadata.source).toBe('ml-intro.txt');
    });

    it('should send X-Tenant-Name header', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ documents: [] }), { status: 200 })
      );

      await client.syftai.queryDataSource({
        endpoint: dataSourceEndpoint,
        query: 'test',
        userEmail: 'test@example.com',
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/endpoints/test-docs/query'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Tenant-Name': 'default',
          }),
        })
      );
    });

    it('should handle empty results', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ documents: [] }), { status: 200 })
      );

      const docs = await client.syftai.queryDataSource({
        endpoint: dataSourceEndpoint,
        query: 'obscure query',
        userEmail: 'test@example.com',
      });

      expect(docs).toHaveLength(0);
    });

    it('should throw RetrievalError on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Internal server error' }), { status: 500 })
      );

      await expect(
        client.syftai.queryDataSource({
          endpoint: dataSourceEndpoint,
          query: 'test',
          userEmail: 'test@example.com',
        })
      ).rejects.toThrow(RetrievalError);
    });

    it('should throw RetrievalError on connection error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection refused'));

      await expect(
        client.syftai.queryDataSource({
          endpoint: dataSourceEndpoint,
          query: 'test',
          userEmail: 'test@example.com',
        })
      ).rejects.toThrow(RetrievalError);
    });
  });

  describe('queryModel()', () => {
    it('should query model successfully', async () => {
      const mockResponse = {
        message: {
          role: 'assistant',
          content: 'Hello! How can I help you today?',
        },
      };

      mockFetch.mockResolvedValueOnce(new Response(JSON.stringify(mockResponse), { status: 200 }));

      const messages: Message[] = [{ role: 'user', content: 'Hello!' }];

      const response = await client.syftai.queryModel({
        endpoint: modelEndpoint,
        messages,
        userEmail: 'test@example.com',
      });

      expect(response).toBe('Hello! How can I help you today?');
    });

    it('should send correct request body', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ message: { content: 'Response' } }), { status: 200 })
      );

      const messages: Message[] = [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: 'What are you?' },
      ];

      await client.syftai.queryModel({
        endpoint: modelEndpoint,
        messages,
        userEmail: 'test@example.com',
        maxTokens: 512,
        temperature: 0.5,
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"max_tokens":512'),
        })
      );

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"temperature":0.5'),
        })
      );
    });

    it('should throw GenerationError on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), { status: 429 })
      );

      await expect(
        client.syftai.queryModel({
          endpoint: modelEndpoint,
          messages: [{ role: 'user', content: 'Hi' }],
          userEmail: 'test@example.com',
        })
      ).rejects.toThrow(GenerationError);
    });

    it('should throw GenerationError on connection error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection refused'));

      await expect(
        client.syftai.queryModel({
          endpoint: modelEndpoint,
          messages: [{ role: 'user', content: 'Hi' }],
          userEmail: 'test@example.com',
        })
      ).rejects.toThrow(GenerationError);
    });
  });

  describe('queryModelStream()', () => {
    it('should stream model response', async () => {
      const sseContent =
        'data: {"content": "Hello"}\n\n' +
        'data: {"content": " world"}\n\n' +
        'data: {"content": "!"}\n\n' +
        'data: [DONE]\n\n';

      mockFetch.mockResolvedValueOnce(
        new Response(sseContent, {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        })
      );

      const chunks: string[] = [];
      for await (const chunk of client.syftai.queryModelStream({
        endpoint: modelEndpoint,
        messages: [{ role: 'user', content: 'Say hello' }],
        userEmail: 'test@example.com',
      })) {
        chunks.push(chunk);
      }

      expect(chunks.join('')).toBe('Hello world!');
    });

    it('should handle OpenAI-style response format', async () => {
      const sseContent =
        'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n' +
        'data: {"choices": [{"delta": {"content": " there"}}]}\n\n' +
        'data: [DONE]\n\n';

      mockFetch.mockResolvedValueOnce(
        new Response(sseContent, {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        })
      );

      const chunks: string[] = [];
      for await (const chunk of client.syftai.queryModelStream({
        endpoint: modelEndpoint,
        messages: [{ role: 'user', content: 'Hi' }],
        userEmail: 'test@example.com',
      })) {
        chunks.push(chunk);
      }

      expect(chunks.join('')).toBe('Hi there');
    });

    it('should throw GenerationError on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Service unavailable' }), { status: 503 })
      );

      const generator = client.syftai.queryModelStream({
        endpoint: modelEndpoint,
        messages: [{ role: 'user', content: 'Hi' }],
        userEmail: 'test@example.com',
      });

      // Need to consume the generator to trigger the error
      await expect(async () => {
        for await (const _event of generator) {
          // consume
        }
      }).rejects.toThrow(GenerationError);
    });
  });

  describe('SyftAIResource integration', () => {
    it('should be accessible from client', () => {
      expect(client.syftai).toBeInstanceOf(SyftAIResource);
    });

    it('should be cached (same instance)', () => {
      const resource1 = client.syftai;
      const resource2 = client.syftai;

      expect(resource1).toBe(resource2);
    });
  });
});
