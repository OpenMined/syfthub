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
  DataSourceQueryResult,
  Document,
  PolicyMetadata,
  QueryDataSourceOptions,
  QueryModelOptions,
} from '../models/chat.js';
import type { HTTPClient } from '../http.js';
import { SyftHubError } from '../errors.js';
import { readSSEEvents } from '../utils.js';
import { ChatResource } from './chat.js';

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
  /**
   * @param http - Hub HTTP client, used to mint satellite tokens and settle
   *   MPP payments. Endpoint queries themselves use direct `fetch`, since the
   *   SyftAI-Space URL is arbitrary and not the Hub base URL.
   */
  constructor(private readonly http: HTTPClient) {}

  /**
   * Mint a satellite token for `audience` (the endpoint owner's username).
   *
   * Mirrors the aggregator's token coordination layer: try an authenticated
   * token first, then fall back to a guest token. Returns `undefined` if both
   * fail, so the caller can still attempt an unauthenticated request.
   */
  private async mintSatelliteToken(audience: string): Promise<string | undefined> {
    if (this.http.hasTokens()) {
      try {
        const res = await this.http.get<{ targetToken?: string }>('/api/v1/token', {
          aud: audience,
        });
        if (res.targetToken) return res.targetToken;
      } catch {
        // fall through to guest
      }
    }
    try {
      const res = await this.http.get<{ targetToken?: string }>(
        '/api/v1/token/guest',
        { aud: audience },
        { includeAuth: false }
      );
      return res.targetToken;
    } catch {
      return undefined;
    }
  }

  /**
   * Pay an MPP `402` challenge via the Hub wallet, returning an X-Payment credential.
   *
   * Mirrors the aggregator's `handleMppPayment`: the `WWW-Authenticate`
   * challenge is forwarded verbatim to the Hub's `/api/v1/wallet/pay`, which
   * parses it and returns an `x_payment` string to attach to a retry.
   */
  private async payMpp(wwwAuthenticate: string, slug: string): Promise<string | undefined> {
    if (!wwwAuthenticate) return undefined;
    const res = await this.http.post<{ xPayment?: string }>('/api/v1/wallet/pay', {
      wwwAuthenticate,
      endpointSlug: slug,
    });
    return res.xPayment;
  }

  /**
   * Build headers for SyftAI-Space request.
   */
  private buildHeaders(tenantName?: string, authorizationToken?: string): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (tenantName) {
      headers['X-Tenant-Name'] = tenantName;
    }
    if (authorizationToken) {
      headers['Authorization'] = `Bearer ${authorizationToken}`;
    }
    return headers;
  }

  /**
   * Parse documents from a SyftAI-Space query response.
   *
   * Mirrors the aggregator's `DataSourceClient._parse_syftai_response`: the
   * canonical shape nests documents under `references.documents` and names the
   * score `similarity_score`. A legacy top-level `documents` list (with
   * `score`) is still honoured for backward compatibility.
   */
  private parseDocuments(data: Record<string, unknown>): Document[] {
    const references = data['references'] as Record<string, unknown> | undefined;
    let rawDocs: Record<string, unknown>[] | undefined;
    let scoreKey = 'score';
    if (references && typeof references === 'object') {
      rawDocs = references['documents'] as Record<string, unknown>[] | undefined;
      scoreKey = 'similarity_score';
    } else {
      rawDocs = data['documents'] as Record<string, unknown>[] | undefined;
    }

    const documents: Document[] = [];
    if (Array.isArray(rawDocs)) {
      for (const doc of rawDocs) {
        documents.push({
          content: String(doc['content'] ?? ''),
          score: Number(doc[scoreKey] ?? doc['score'] ?? 0),
          metadata: (doc['metadata'] as Record<string, unknown>) ?? {},
        });
      }
    }
    return documents;
  }

  /**
   * Parse the raw `policy_metadata` block from a syft-space response.
   *
   * The direct path (Boundary A) carries a top-level `policy_metadata` object
   * shaped `{ outcome, entries: [...] }`. Entries reuse the {@link BillingEntry}
   * shape (with `source` absent), so this delegates entry parsing to
   * {@link ChatResource.parseBillingEntry}. The wire keys are snake_case.
   */
  private parsePolicyMetadata(data: Record<string, unknown>): PolicyMetadata | undefined {
    const pm = data['policy_metadata'];
    if (!pm || typeof pm !== 'object') {
      return undefined;
    }
    const meta = pm as Record<string, unknown>;
    const entriesRaw = Array.isArray(meta['entries']) ? meta['entries'] : [];
    return {
      outcome: String(meta['outcome'] ?? ''),
      entries: (entriesRaw as Record<string, unknown>[]).map((e) =>
        ChatResource.parseBillingEntry(e)
      ),
    };
  }

  /**
   * Query a data source endpoint directly.
   *
   * Authentication mirrors the aggregator: SyftAI-Space endpoints expect a
   * satellite bearer token whose audience is the endpoint owner's username. If
   * `authorizationToken` is not supplied, one is minted automatically when an
   * owner is known (`ownerUsername` option or `endpoint.ownerUsername`).
   *
   * @param options - Query options
   * @returns DataSourceQueryResult — the retrieved documents plus the raw
   *   `policyMetadata` block from the syft-space response (price, recipient,
   *   transaction, status).
   * @throws {RetrievalError} If the query fails
   */
  async queryDataSource(options: QueryDataSourceOptions): Promise<DataSourceQueryResult> {
    const {
      endpoint,
      query,
      userEmail,
      topK = 5,
      similarityThreshold = 0.5,
      authorizationToken,
      ownerUsername,
      pay = false,
    } = options;

    const url = `${endpoint.url.replace(/\/$/, '')}/api/v1/endpoints/${endpoint.slug}/query`;

    const requestBody = {
      user_email: userEmail,
      messages: query, // SyftAI-Space expects "messages" for query text
      limit: topK,
      similarity_threshold: similarityThreshold,
    };

    // Resolve a satellite token: caller-supplied, else mint from the owner.
    let token = authorizationToken;
    if (!token) {
      const audience = ownerUsername ?? endpoint.ownerUsername;
      if (audience) {
        token = await this.mintSatelliteToken(audience);
      }
    }
    const headers = this.buildHeaders(endpoint.tenantName, token);

    const postQuery = async (extraHeaders?: Record<string, string>): Promise<Response> => {
      try {
        return await fetch(url, {
          method: 'POST',
          headers: { ...headers, ...extraHeaders },
          body: JSON.stringify(requestBody),
        });
      } catch (error) {
        throw new RetrievalError(
          `Failed to connect to data source '${endpoint.slug}': ${error instanceof Error ? error.message : String(error)}`,
          endpoint.slug,
          error
        );
      }
    };

    let response = await postQuery();

    // MPP 402 payment flow: pay via the Hub wallet, then retry with X-Payment.
    if (response.status === 402 && pay) {
      let xPayment: string | undefined;
      try {
        xPayment = await this.payMpp(response.headers.get('www-authenticate') ?? '', endpoint.slug);
      } catch (error) {
        throw new RetrievalError(
          `Payment failed for data source '${endpoint.slug}': ${error instanceof Error ? error.message : String(error)}`,
          endpoint.slug,
          error
        );
      }
      if (xPayment) {
        response = await postQuery({ 'X-Payment': xPayment });
      }
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

    return {
      documents: this.parseDocuments(data),
      policyMetadata: this.parsePolicyMetadata(data),
    };
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

    for await (const { data: dataStr } of readSSEEvents(response)) {
      if (dataStr === '[DONE]') return;

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
