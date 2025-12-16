/**
 * Chat resource for RAG-augmented conversations via the Aggregator service.
 *
 * @example
 * // Simple chat completion
 * const response = await client.chat.complete({
 *   prompt: 'What is machine learning?',
 *   model: 'alice/gpt-model',
 *   dataSources: ['bob/ml-docs'],
 * });
 * console.log(response.response);
 *
 * // Streaming chat
 * for await (const event of client.chat.stream(options)) {
 *   if (event.type === 'token') {
 *     process.stdout.write(event.content);
 *   }
 * }
 */

import type { HTTPClient } from '../http.js';
import type { EndpointPublic } from '../models/index.js';
import type {
  ChatMetadata,
  ChatOptions,
  ChatResponse,
  ChatStreamEvent,
  EndpointRef,
  SourceInfo,
  SourceStatus,
} from '../models/chat.js';
import { AuthenticationError, SyftHubError } from '../errors.js';
import type { HubResource } from './hub.js';
import type { AuthResource } from './auth.js';
import { EndpointType } from '../models/index.js';

/**
 * Error thrown when the aggregator service is unavailable or returns an error.
 */
export class AggregatorError extends SyftHubError {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = 'AggregatorError';
  }
}

/**
 * Error thrown when an endpoint cannot be resolved.
 */
export class EndpointResolutionError extends SyftHubError {
  constructor(
    message: string,
    public readonly endpointPath?: string
  ) {
    super(message);
    this.name = 'EndpointResolutionError';
  }
}

/**
 * Chat resource for RAG-augmented conversations via the Aggregator.
 *
 * This resource provides high-level chat functionality that:
 * - Queries data sources for relevant context (retrieval)
 * - Sends prompts with context to model endpoints (generation)
 * - Supports both synchronous and streaming responses
 */
export class ChatResource {
  constructor(
    private readonly http: HTTPClient,
    private readonly hub: HubResource,
    private readonly auth: AuthResource,
    private readonly aggregatorUrl: string
  ) {}

  /**
   * Get the current authenticated user's email.
   */
  private async getUserEmail(): Promise<string> {
    if (!this.http.hasTokens()) {
      throw new AuthenticationError('Must be authenticated to use chat');
    }
    const user = await this.auth.me();
    return user.email;
  }

  /**
   * Convert any endpoint format to EndpointRef with URL.
   */
  private async resolveEndpointRef(
    endpoint: string | EndpointRef | EndpointPublic,
    expectedType?: 'model' | 'data_source'
  ): Promise<EndpointRef> {
    // Already an EndpointRef
    if (this.isEndpointRef(endpoint)) {
      return endpoint;
    }

    // EndpointPublic object
    if (this.isEndpointPublic(endpoint)) {
      // Validate type if expected
      if (expectedType && endpoint.type !== expectedType) {
        throw new Error(
          `Expected endpoint type '${expectedType}', got '${endpoint.type}' for '${endpoint.slug}'`
        );
      }

      // Find first enabled connection with URL
      for (const conn of endpoint.connect) {
        if (conn.enabled && conn.config['url']) {
          return {
            url: String(conn.config['url']),
            slug: endpoint.slug,
            name: endpoint.name,
            tenantName: conn.config['tenant_name'] as string | undefined,
          };
        }
      }

      throw new EndpointResolutionError(
        `Endpoint '${endpoint.slug}' has no connection with URL configured`,
        `${endpoint.ownerUsername}/${endpoint.slug}`
      );
    }

    // String path format "owner/slug"
    if (typeof endpoint === 'string') {
      let ep: EndpointPublic;
      try {
        ep = await this.hub.get(endpoint);
      } catch (error) {
        throw new EndpointResolutionError(
          `Failed to fetch endpoint '${endpoint}': ${error instanceof Error ? error.message : String(error)}`,
          endpoint
        );
      }
      return this.resolveEndpointRef(ep, expectedType);
    }

    throw new TypeError(`Cannot resolve endpoint from type: ${typeof endpoint}`);
  }

  /**
   * Type guard for EndpointRef.
   */
  private isEndpointRef(value: unknown): value is EndpointRef {
    return (
      typeof value === 'object' &&
      value !== null &&
      'url' in value &&
      'slug' in value &&
      typeof (value as EndpointRef).url === 'string' &&
      typeof (value as EndpointRef).slug === 'string'
    );
  }

  /**
   * Type guard for EndpointPublic.
   */
  private isEndpointPublic(value: unknown): value is EndpointPublic {
    return (
      typeof value === 'object' &&
      value !== null &&
      'connect' in value &&
      'ownerUsername' in value &&
      Array.isArray((value as EndpointPublic).connect)
    );
  }

  /**
   * Build the request body for the aggregator.
   */
  private buildRequestBody(
    prompt: string,
    userEmail: string,
    modelRef: EndpointRef,
    dataSourceRefs: EndpointRef[],
    options: {
      topK?: number;
      maxTokens?: number;
      temperature?: number;
      similarityThreshold?: number;
      stream?: boolean;
    }
  ): Record<string, unknown> {
    return {
      prompt,
      user_email: userEmail,
      model: {
        url: modelRef.url,
        slug: modelRef.slug,
        name: modelRef.name ?? '',
        tenant_name: modelRef.tenantName ?? null,
      },
      data_sources: dataSourceRefs.map((ds) => ({
        url: ds.url,
        slug: ds.slug,
        name: ds.name ?? '',
        tenant_name: ds.tenantName ?? null,
      })),
      top_k: options.topK ?? 5,
      max_tokens: options.maxTokens ?? 1024,
      temperature: options.temperature ?? 0.7,
      similarity_threshold: options.similarityThreshold ?? 0.5,
      stream: options.stream ?? false,
    };
  }

  /**
   * Parse a SourceInfo from raw data.
   */
  private parseSourceInfo(data: Record<string, unknown>): SourceInfo {
    return {
      path: String(data['path'] ?? ''),
      documentsRetrieved: Number(data['documents_retrieved'] ?? 0),
      status: (data['status'] as SourceStatus) ?? 'success',
      errorMessage: data['error_message'] as string | undefined,
    };
  }

  /**
   * Parse ChatMetadata from raw data.
   */
  private parseMetadata(data: Record<string, unknown>): ChatMetadata {
    return {
      retrievalTimeMs: Number(data['retrieval_time_ms'] ?? 0),
      generationTimeMs: Number(data['generation_time_ms'] ?? 0),
      totalTimeMs: Number(data['total_time_ms'] ?? 0),
    };
  }

  /**
   * Send a chat request and get the complete response.
   *
   * @param options - Chat completion options
   * @returns ChatResponse with response text, sources, and metadata
   * @throws {AuthenticationError} If not authenticated
   * @throws {EndpointResolutionError} If endpoint cannot be resolved
   * @throws {AggregatorError} If aggregator service fails
   */
  async complete(options: ChatOptions): Promise<ChatResponse> {
    const userEmail = await this.getUserEmail();
    const modelRef = await this.resolveEndpointRef(options.model, 'model');

    const dsRefs: EndpointRef[] = [];
    for (const ds of options.dataSources ?? []) {
      dsRefs.push(await this.resolveEndpointRef(ds, 'data_source'));
    }

    const requestBody = this.buildRequestBody(options.prompt, userEmail, modelRef, dsRefs, {
      topK: options.topK,
      maxTokens: options.maxTokens,
      temperature: options.temperature,
      similarityThreshold: options.similarityThreshold,
      stream: false,
    });

    const url = `${this.aggregatorUrl}/chat`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = (await response.json()) as Record<string, unknown>;
        message = String(data['message'] ?? data['error'] ?? message);
      } catch {
        // Use default message
      }
      throw new AggregatorError(`Aggregator error: ${message}`, response.status);
    }

    const data = (await response.json()) as Record<string, unknown>;

    const sources: SourceInfo[] = [];
    const sourcesData = data['sources'] as Record<string, unknown>[] | undefined;
    if (Array.isArray(sourcesData)) {
      for (const s of sourcesData) {
        sources.push(this.parseSourceInfo(s));
      }
    }

    const metadataData = data['metadata'] as Record<string, unknown> | undefined;
    const metadata = this.parseMetadata(metadataData ?? {});

    return {
      response: String(data['response'] ?? ''),
      sources,
      metadata,
    };
  }

  /**
   * Send a chat request and stream response events.
   *
   * @param options - Chat completion options
   * @yields ChatStreamEvent objects as they arrive
   */
  async *stream(options: ChatOptions): AsyncGenerator<ChatStreamEvent, void, unknown> {
    const userEmail = await this.getUserEmail();
    const modelRef = await this.resolveEndpointRef(options.model, 'model');

    const dsRefs: EndpointRef[] = [];
    for (const ds of options.dataSources ?? []) {
      dsRefs.push(await this.resolveEndpointRef(ds, 'data_source'));
    }

    const requestBody = this.buildRequestBody(options.prompt, userEmail, modelRef, dsRefs, {
      topK: options.topK,
      maxTokens: options.maxTokens,
      temperature: options.temperature,
      similarityThreshold: options.similarityThreshold,
      stream: true,
    });

    const url = `${this.aggregatorUrl}/chat/stream`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = (await response.json()) as Record<string, unknown>;
        message = String(data['message'] ?? data['error'] ?? message);
      } catch {
        // Use default message
      }
      throw new AggregatorError(`Aggregator error: ${message}`, response.status);
    }

    if (!response.body) {
      throw new AggregatorError('No response body from aggregator');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent: string | null = null;
    let currentData = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmedLine = line.trim();

          if (!trimmedLine) {
            // Empty line = end of event
            if (currentEvent && currentData) {
              try {
                const data = JSON.parse(currentData) as Record<string, unknown>;
                const event = this.parseSSEEvent(currentEvent, data);
                if (event) {
                  yield event;
                }
              } catch {
                // Skip malformed data
              }
            }
            currentEvent = null;
            currentData = '';
            continue;
          }

          if (trimmedLine.startsWith('event:')) {
            currentEvent = trimmedLine.slice(6).trim();
          } else if (trimmedLine.startsWith('data:')) {
            currentData = trimmedLine.slice(5).trim();
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /**
   * Parse an SSE event into a typed event object.
   */
  private parseSSEEvent(
    eventType: string,
    data: Record<string, unknown>
  ): ChatStreamEvent | null {
    switch (eventType) {
      case 'retrieval_start':
        return {
          type: 'retrieval_start',
          sourceCount: Number(data['sources'] ?? 0),
        };

      case 'source_complete':
        return {
          type: 'source_complete',
          path: String(data['path'] ?? ''),
          status: String(data['status'] ?? ''),
          documentsRetrieved: Number(data['documents'] ?? 0),
        };

      case 'retrieval_complete':
        return {
          type: 'retrieval_complete',
          totalDocuments: Number(data['total_documents'] ?? 0),
          timeMs: Number(data['time_ms'] ?? 0),
        };

      case 'generation_start':
        return { type: 'generation_start' };

      case 'token':
        return {
          type: 'token',
          content: String(data['content'] ?? ''),
        };

      case 'done': {
        const sources: SourceInfo[] = [];
        const sourcesData = data['sources'] as Record<string, unknown>[] | undefined;
        if (Array.isArray(sourcesData)) {
          for (const s of sourcesData) {
            sources.push(this.parseSourceInfo(s));
          }
        }

        const metadataData = data['metadata'] as Record<string, unknown> | undefined;
        const metadata = this.parseMetadata(metadataData ?? {});

        return { type: 'done', sources, metadata };
      }

      case 'error':
        return {
          type: 'error',
          message: String(data['message'] ?? 'Unknown error'),
        };

      default:
        return {
          type: 'error',
          message: `Unknown event type: ${eventType}`,
        };
    }
  }

  /**
   * Get model endpoints that have connection URLs configured.
   *
   * @param limit - Maximum number of results (default: 20)
   * @returns Array of EndpointPublic objects for models with URLs
   */
  async getAvailableModels(limit = 20): Promise<EndpointPublic[]> {
    const results: EndpointPublic[] = [];

    for await (const endpoint of this.hub.browse()) {
      if (results.length >= limit) break;

      if (endpoint.type !== EndpointType.MODEL) continue;

      const hasUrl = endpoint.connect.some(
        (conn) => conn.enabled && conn.config['url']
      );

      if (hasUrl) {
        results.push(endpoint);
      }
    }

    return results;
  }

  /**
   * Get data source endpoints that have connection URLs configured.
   *
   * @param limit - Maximum number of results (default: 20)
   * @returns Array of EndpointPublic objects for data sources with URLs
   */
  async getAvailableDataSources(limit = 20): Promise<EndpointPublic[]> {
    const results: EndpointPublic[] = [];

    for await (const endpoint of this.hub.browse()) {
      if (results.length >= limit) break;

      if (endpoint.type !== EndpointType.DATA_SOURCE) continue;

      const hasUrl = endpoint.connect.some(
        (conn) => conn.enabled && conn.config['url']
      );

      if (hasUrl) {
        results.push(endpoint);
      }
    }

    return results;
  }
}
