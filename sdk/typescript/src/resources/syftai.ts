/**
 * SyftAI-Space resource for direct endpoint queries.
 *
 * This module provides low-level access to SyftAI-Space endpoints, allowing
 * users to build custom RAG pipelines or bypass the aggregator service.
 *
 * @example
 * // Query a data source directly
 * const docs = await client.syftai.queryDataSource({
 *   endpoint: { url: 'http://syftai:8080', slug: 'docs' },
 *   query: 'What is machine learning?',
 *   userEmail: 'alice@example.com',
 * });
 *
 * // Query a model directly
 * const response = await client.syftai.queryModel({
 *   endpoint: { url: 'http://syftai:8080', slug: 'gpt-model' },
 *   messages: [
 *     { role: 'system', content: 'You are a helpful assistant.' },
 *     { role: 'user', content: 'Hello!' },
 *   ],
 *   userEmail: 'alice@example.com',
 * });
 */

import type {
  Document,
  QueryDataSourceOptions,
  QueryModelOptions,
} from '../models/chat.js';
import { SyftHubError } from '../errors.js';

/**
 * Error thrown when data source retrieval fails.
 */
export class RetrievalError extends SyftHubError {
  constructor(
    message: string,
    public readonly sourcePath?: string,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'RetrievalError';
  }
}

/**
 * Error thrown when model generation fails.
 */
export class GenerationError extends SyftHubError {
  constructor(
    message: string,
    public readonly modelSlug?: string,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'GenerationError';
  }
}

/**
 * Low-level resource for direct SyftAI-Space endpoint queries.
 *
 * This resource provides direct access to SyftAI-Space endpoints without
 * going through the aggregator. Use this when you need:
 * - Custom RAG pipelines with specific retrieval strategies
 * - Direct model queries without data source context
 * - Fine-grained control over the query process
 *
 * For most use cases, prefer the higher-level `client.chat` API instead.
 */
export class SyftAIResource {
  // No dependencies - uses direct fetch to SyftAI-Space endpoints

  /**
   * Build headers for SyftAI-Space request.
   */
  private buildHeaders(tenantName?: string): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (tenantName) {
      headers['X-Tenant-Name'] = tenantName;
    }
    return headers;
  }

  /**
   * Query a data source endpoint directly.
   *
   * @param options - Query options
   * @returns Array of Document objects
   * @throws {RetrievalError} If the query fails
   */
  async queryDataSource(options: QueryDataSourceOptions): Promise<Document[]> {
    const { endpoint, query, userEmail, topK = 5, similarityThreshold = 0.5 } = options;

    const url = `${endpoint.url.replace(/\/$/, '')}/api/v1/endpoints/${endpoint.slug}/query`;

    const requestBody = {
      user_email: userEmail,
      messages: query, // SyftAI-Space expects "messages" for query text
      limit: topK,
      similarity_threshold: similarityThreshold,
    };

    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: this.buildHeaders(endpoint.tenantName),
        body: JSON.stringify(requestBody),
      });
    } catch (error) {
      throw new RetrievalError(
        `Failed to connect to data source '${endpoint.slug}': ${error instanceof Error ? error.message : String(error)}`,
        endpoint.slug,
        error
      );
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = (await response.json()) as Record<string, unknown>;
        message = String(data['detail'] ?? data['message'] ?? message);
      } catch {
        // Use default message
      }
      throw new RetrievalError(`Data source query failed: ${message}`, endpoint.slug);
    }

    const data = (await response.json()) as Record<string, unknown>;
    const documents: Document[] = [];

    const docsData = data['documents'] as Record<string, unknown>[] | undefined;
    if (Array.isArray(docsData)) {
      for (const doc of docsData) {
        documents.push({
          content: String(doc['content'] ?? ''),
          score: Number(doc['score'] ?? 0),
          metadata: (doc['metadata'] as Record<string, unknown>) ?? {},
        });
      }
    }

    return documents;
  }

  /**
   * Query a model endpoint directly.
   *
   * @param options - Query options
   * @returns Generated response text
   * @throws {GenerationError} If generation fails
   */
  async queryModel(options: QueryModelOptions): Promise<string> {
    const { endpoint, messages, userEmail, maxTokens = 1024, temperature = 0.7 } = options;

    const url = `${endpoint.url.replace(/\/$/, '')}/api/v1/endpoints/${endpoint.slug}/query`;

    const requestBody = {
      user_email: userEmail,
      messages: messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      })),
      max_tokens: maxTokens,
      temperature,
      stream: false,
    };

    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: this.buildHeaders(endpoint.tenantName),
        body: JSON.stringify(requestBody),
      });
    } catch (error) {
      throw new GenerationError(
        `Failed to connect to model '${endpoint.slug}': ${error instanceof Error ? error.message : String(error)}`,
        endpoint.slug,
        error
      );
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = (await response.json()) as Record<string, unknown>;
        message = String(data['detail'] ?? data['message'] ?? message);
      } catch {
        // Use default message
      }
      throw new GenerationError(`Model query failed: ${message}`, endpoint.slug);
    }

    const data = (await response.json()) as Record<string, unknown>;
    const messageData = data['message'] as Record<string, unknown> | undefined;
    return String(messageData?.['content'] ?? '');
  }

  /**
   * Stream a model response directly.
   *
   * @param options - Query options
   * @yields Response text chunks as they arrive
   * @throws {GenerationError} If generation fails
   */
  async *queryModelStream(options: QueryModelOptions): AsyncGenerator<string, void, unknown> {
    const { endpoint, messages, userEmail, maxTokens = 1024, temperature = 0.7 } = options;

    const url = `${endpoint.url.replace(/\/$/, '')}/api/v1/endpoints/${endpoint.slug}/query`;

    const requestBody = {
      user_email: userEmail,
      messages: messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      })),
      max_tokens: maxTokens,
      temperature,
      stream: true,
    };

    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: {
          ...this.buildHeaders(endpoint.tenantName),
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(requestBody),
      });
    } catch (error) {
      throw new GenerationError(
        `Failed to connect to model '${endpoint.slug}': ${error instanceof Error ? error.message : String(error)}`,
        endpoint.slug,
        error
      );
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = (await response.json()) as Record<string, unknown>;
        message = String(data['detail'] ?? data['message'] ?? message);
      } catch {
        // Use default message
      }
      throw new GenerationError(`Model stream failed: ${message}`, endpoint.slug);
    }

    if (!response.body) {
      throw new GenerationError('No response body from model', endpoint.slug);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmedLine = line.trim();

          if (!trimmedLine || trimmedLine.startsWith('event:')) {
            continue;
          }

          if (trimmedLine.startsWith('data:')) {
            const dataStr = trimmedLine.slice(5).trim();
            if (dataStr === '[DONE]') {
              return;
            }

            try {
              const data = JSON.parse(dataStr) as Record<string, unknown>;

              // Extract content from various response formats
              if (typeof data['content'] === 'string') {
                yield data['content'];
              } else if (Array.isArray(data['choices'])) {
                // OpenAI-style response
                for (const choice of data['choices'] as Record<string, unknown>[]) {
                  const delta = choice['delta'] as Record<string, unknown> | undefined;
                  if (delta && typeof delta['content'] === 'string') {
                    yield delta['content'];
                  }
                }
              }
            } catch {
              // Skip malformed data
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}
