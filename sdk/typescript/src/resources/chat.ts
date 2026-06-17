/**
 * Chat resource for RAG-augmented conversations via the Aggregator service.
 *
 * This resource handles satellite token authentication automatically:
 * - Resolves endpoints and extracts owner information
 * - Exchanges Hub access tokens for satellite tokens (one per unique owner)
 * - Sends tokens to the aggregator for forwarding to SyftAI-Space
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

import type { EndpointPublic } from '../models/index.js';
import type {
  ChatMetadata,
  ChatOptions,
  ChatResponse,
  ChatStreamEvent,
  DocumentSource,
  EndpointRef,
  Message,
  SearchDocument,
  SearchQueryOptions,
  SearchResponse,
  SourceInfo,
  SourceStatus,
  TokenUsage,
} from '../models/chat.js';
import { SyftHubError } from '../errors.js';
import { readSSEEvents } from '../utils.js';
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
    private readonly hub: HubResource,
    private readonly auth: AuthResource,
    private readonly aggregatorUrl: string
  ) {}

  /**
   * Check if an endpoint type matches the expected type.
   * A model_data_source endpoint matches both 'model' and 'data_source'.
   */
  private static typeMatches(actualType: string, expectedType: string): boolean {
    if (actualType === expectedType) return true;
    if (actualType === EndpointType.MODEL_DATA_SOURCE) {
      return expectedType === EndpointType.MODEL || expectedType === EndpointType.DATA_SOURCE;
    }
    // Agent endpoints can be used where model endpoints are expected
    if (actualType === EndpointType.AGENT && expectedType === EndpointType.MODEL) {
      return true;
    }
    return false;
  }

  /**
   * Convert any endpoint format to EndpointRef with URL and owner info.
   * The ownerUsername is critical for satellite token authentication.
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
      // Validate type if expected (model_data_source matches both model and data_source)
      if (expectedType && !ChatResource.typeMatches(endpoint.type, expectedType)) {
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
            ownerUsername: endpoint.ownerUsername, // Capture owner for satellite token
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
   * Collect unique owner usernames from all endpoints.
   * Used to determine which satellite tokens need to be fetched.
   */
  private collectUniqueOwners(modelRef: EndpointRef, dataSourceRefs: EndpointRef[]): string[] {
    const owners = new Set<string>();

    if (modelRef.ownerUsername) {
      owners.add(modelRef.ownerUsername);
    }

    for (const ds of dataSourceRefs) {
      if (ds.ownerUsername) {
        owners.add(ds.ownerUsername);
      }
    }

    return [...owners];
  }

  /**
   * Get satellite tokens for all unique endpoint owners.
   * Returns a map of owner username to satellite token.
   *
   * @param owners - Array of unique owner usernames
   * @param guestMode - If true, fetch guest tokens (no auth required)
   */
  private async getSatelliteTokensForOwners(
    owners: string[],
    guestMode = false
  ): Promise<Record<string, string>> {
    if (owners.length === 0) {
      return {};
    }

    const tokenMap = guestMode
      ? await this.auth.getGuestSatelliteTokens(owners)
      : await this.auth.getSatelliteTokens(owners);
    const result: Record<string, string> = {};

    for (const [owner, token] of tokenMap) {
      result[owner] = token;
    }

    return result;
  }

  /**
   * Get the user's Hub access token for MPP payment flow.
   * Returns null if in guest mode or not authenticated.
   */
  private getUserToken(): string | null {
    return this.auth.getAccessToken();
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

  private static readonly COLLECTIVE_PREFIX = 'collective/';
  private static readonly TUNNELING_PREFIX = 'tunneling:';

  /**
   * Expand any `collective/<slug>` (or `collective/<slug>/<shared-slug>`)
   * entries in the data-sources list into the individual `owner/slug` paths
   * of the collective's approved members.
   *
   * Path forms recognised:
   * - `collective/<slug>` → every approved member (backward-compatible)
   * - `collective/<slug>/all` → equivalent alias of the above
   * - `collective/<slug>/<shared-slug>` → the named subset, intersected with
   *   the collective's currently approved members
   *
   * Non-collective entries pass through unchanged. String paths are
   * deduplicated so a regular endpoint that also belongs to a selected
   * collective is not queried twice.
   */
  private async expandCollectivePaths(
    dataSources: (string | EndpointRef | EndpointPublic)[]
  ): Promise<(string | EndpointRef | EndpointPublic)[]> {
    const expanded: (string | EndpointRef | EndpointPublic)[] = [];
    const seenPaths = new Set<string>();

    for (const ds of dataSources) {
      if (typeof ds === 'string' && ds.startsWith(ChatResource.COLLECTIVE_PREFIX)) {
        const rest = ds.slice(ChatResource.COLLECTIVE_PREFIX.length);
        const slashAt = rest.indexOf('/');
        const collectiveSlug = slashAt < 0 ? rest : rest.slice(0, slashAt);
        // `all` is the implicit alias of "every approved member" and maps to
        // the same hub route as the no-subset form, so the SDK normalises it
        // away rather than round-tripping a degenerate identifier.
        const rawShared = slashAt < 0 ? undefined : rest.slice(slashAt + 1);
        const sharedSlug = rawShared && rawShared !== 'all' ? rawShared : undefined;

        if (!collectiveSlug) {
          throw new EndpointResolutionError(`Malformed collective path: ${ds}`, ds);
        }

        let memberPaths: string[];
        try {
          memberPaths = await this.hub.getCollectiveEndpointPaths(collectiveSlug, sharedSlug);
        } catch (error) {
          const target = sharedSlug ? `${collectiveSlug}/${sharedSlug}` : collectiveSlug;
          throw new EndpointResolutionError(
            `Failed to resolve collective '${target}': ${error instanceof Error ? error.message : String(error)}`,
            ds
          );
        }
        for (const path of memberPaths) {
          if (!seenPaths.has(path)) {
            seenPaths.add(path);
            expanded.push(path);
          }
        }
      } else if (typeof ds === 'string') {
        if (!seenPaths.has(ds)) {
          seenPaths.add(ds);
          expanded.push(ds);
        }
      } else {
        // EndpointRef or EndpointPublic — pass through without dedup
        expanded.push(ds);
      }
    }

    return expanded;
  }

  /**
   * Check if any endpoints use tunneling URLs and extract target usernames.
   */
  private collectTunnelingUsernames(
    modelRef: EndpointRef,
    dataSourceRefs: EndpointRef[]
  ): string[] {
    const usernames = new Set<string>();

    if (modelRef.url.startsWith(ChatResource.TUNNELING_PREFIX)) {
      usernames.add(modelRef.url.slice(ChatResource.TUNNELING_PREFIX.length));
    }

    for (const ds of dataSourceRefs) {
      if (ds.url.startsWith(ChatResource.TUNNELING_PREFIX)) {
        usernames.add(ds.url.slice(ChatResource.TUNNELING_PREFIX.length));
      }
    }

    return [...usernames];
  }

  /**
   * Shared request preparation for complete() and stream().
   * Resolves endpoints, fetches tokens, and builds the aggregator request body.
   * Returns the request body and the resolved aggregator URL.
   */
  private async prepareRequest(
    options: ChatOptions,
    stream: boolean,
    retrievalOnly = false
  ): Promise<{ requestBody: Record<string, unknown>; effectiveAggregatorUrl: string }> {
    const modelRef = await this.resolveEndpointRef(options.model, 'model');

    // Expand any collective/<slug> paths into their approved member endpoint paths.
    const expandedDataSources = await this.expandCollectivePaths(options.dataSources ?? []);

    const dsRefs: EndpointRef[] = [];
    for (const ds of expandedDataSources) {
      dsRefs.push(await this.resolveEndpointRef(ds, 'data_source'));
    }

    const uniqueOwners = this.collectUniqueOwners(modelRef, dsRefs);
    const guestMode = options.guestMode ?? false;
    const endpointTokens = await this.getSatelliteTokensForOwners(uniqueOwners, guestMode);
    const userToken = guestMode ? null : this.getUserToken();

    let peerToken = options.peerToken;
    let peerChannel = options.peerChannel;
    if (!peerToken) {
      const tunnelingUsernames = this.collectTunnelingUsernames(modelRef, dsRefs);
      if (tunnelingUsernames.length > 0) {
        const peerResponse = guestMode
          ? await this.auth.getGuestPeerToken(tunnelingUsernames)
          : await this.auth.getPeerToken(tunnelingUsernames);
        peerToken = peerResponse.peerToken;
        peerChannel = peerResponse.peerChannel;
      }
    }

    const requestBody = this.buildRequestBody(
      options.prompt,
      modelRef,
      dsRefs,
      endpointTokens,
      userToken,
      {
        topK: options.topK,
        maxTokens: options.maxTokens,
        temperature: options.temperature,
        similarityThreshold: options.similarityThreshold,
        stream,
        messages: options.messages,
        peerToken,
        peerChannel,
        retrievalOnly,
      }
    );

    const effectiveAggregatorUrl = (options.aggregatorUrl ?? this.aggregatorUrl).replace(
      /\/+$/,
      ''
    );

    return { requestBody, effectiveAggregatorUrl };
  }

  /**
   * Parse an error response from the aggregator into an AggregatorError.
   */
  private async handleAggregatorErrorResponse(response: Response): Promise<never> {
    let message = `HTTP ${response.status}`;
    try {
      const data = (await response.json()) as Record<string, unknown>;
      message = String(data['message'] ?? data['error'] ?? message);
    } catch {
      // Use default message
    }
    throw new AggregatorError(`Aggregator error: ${message}`, response.status);
  }

  /**
   * Build the request body for the aggregator.
   * Includes endpoint_tokens mapping for satellite token authentication.
   * Includes user_token for MPP payment callback authorization.
   * User identity is derived from satellite tokens, not passed in request body.
   */
  private buildRequestBody(
    prompt: string,
    modelRef: EndpointRef,
    dataSourceRefs: EndpointRef[],
    endpointTokens: Record<string, string>,
    userToken: string | null,
    options: {
      topK?: number;
      maxTokens?: number;
      temperature?: number;
      similarityThreshold?: number;
      stream?: boolean;
      messages?: Message[];
      peerToken?: string;
      peerChannel?: string;
      retrievalOnly?: boolean;
    }
  ): Record<string, unknown> {
    const body: Record<string, unknown> = {
      prompt,
      model: {
        url: modelRef.url,
        slug: modelRef.slug,
        name: modelRef.name ?? '',
        tenant_name: modelRef.tenantName ?? null,
        owner_username: modelRef.ownerUsername ?? null,
      },
      data_sources: dataSourceRefs.map((ds) => ({
        url: ds.url,
        slug: ds.slug,
        name: ds.name ?? '',
        tenant_name: ds.tenantName ?? null,
        owner_username: ds.ownerUsername ?? null,
      })),
      endpoint_tokens: endpointTokens,
      top_k: options.topK ?? 5,
      max_tokens: options.maxTokens ?? 1024,
      temperature: options.temperature ?? 0.7,
      similarity_threshold: options.similarityThreshold ?? 0.5,
      stream: options.stream ?? false,
    };

    // Include user token for MPP payment flow
    if (userToken) {
      body['user_token'] = userToken;
    }

    if (options.messages && options.messages.length > 0) {
      body.messages = options.messages.map((m) => ({ role: m.role, content: m.content }));
    }

    // Include peer token fields for NATS tunneling
    if (options.peerToken) {
      body['peer_token'] = options.peerToken;
    }
    if (options.peerChannel) {
      body['peer_channel'] = options.peerChannel;
    }

    // Retrieval-only: aggregator skips reranking + generation.
    if (options.retrievalOnly) {
      body['retrieval_only'] = true;
    }

    return body;
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
   * Parse TokenUsage from raw data.
   */
  private parseUsage(data: Record<string, unknown>): TokenUsage {
    return {
      promptTokens: Number(data['prompt_tokens'] ?? 0),
      completionTokens: Number(data['completion_tokens'] ?? 0),
      totalTokens: Number(data['total_tokens'] ?? 0),
    };
  }

  /**
   * Parse document sources from raw data.
   * The new format is a dict mapping document title to {slug, content}.
   */
  private parseDocumentSources(
    data: Record<string, unknown> | undefined
  ): Record<string, DocumentSource> {
    const sources: Record<string, DocumentSource> = {};
    if (!data || typeof data !== 'object') {
      return sources;
    }

    for (const [title, value] of Object.entries(data)) {
      if (value && typeof value === 'object') {
        const source = value as Record<string, unknown>;
        sources[title] = {
          slug: String(source['slug'] ?? ''),
          content: String(source['content'] ?? ''),
        };
      }
    }
    return sources;
  }

  /**
   * Parse retrieval info (SourceInfo array) from raw data.
   */
  private parseRetrievalInfo(data: Record<string, unknown>[] | undefined): SourceInfo[] {
    const retrievalInfo: SourceInfo[] = [];
    if (!Array.isArray(data)) {
      return retrievalInfo;
    }

    for (const item of data) {
      retrievalInfo.push(this.parseSourceInfo(item));
    }
    return retrievalInfo;
  }

  /**
   * Send a chat request and get the complete response.
   *
   * This method automatically:
   * 1. Resolves endpoints and extracts owner information
   * 2. Exchanges Hub tokens for satellite tokens (one per unique owner)
   * 3. Passes the user's Hub access token for MPP payment authorization
   * 4. Sends tokens to the aggregator for forwarding to SyftAI-Space
   *
   * @param options - Chat completion options
   * @returns ChatResponse with response text, sources, and metadata
   * @throws {EndpointResolutionError} If endpoint cannot be resolved
   * @throws {AggregatorError} If aggregator service fails
   */
  async complete(options: ChatOptions): Promise<ChatResponse> {
    const { requestBody, effectiveAggregatorUrl } = await this.prepareRequest(options, false);

    const response = await fetch(`${effectiveAggregatorUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      return this.handleAggregatorErrorResponse(response);
    }

    const data = (await response.json()) as Record<string, unknown>;

    // Parse document sources (new format: dict of title -> {slug, content})
    const sourcesData = data['sources'] as Record<string, unknown> | undefined;
    const sources = this.parseDocumentSources(sourcesData);

    // Parse retrieval info (metadata about each data source retrieval)
    const retrievalInfoData = data['retrieval_info'] as Record<string, unknown>[] | undefined;
    const retrievalInfo = this.parseRetrievalInfo(retrievalInfoData);

    const metadataData = data['metadata'] as Record<string, unknown> | undefined;
    const metadata = this.parseMetadata(metadataData ?? {});

    // Parse usage if available
    const usageData = data['usage'] as Record<string, unknown> | undefined;
    const usage = usageData ? this.parseUsage(usageData) : undefined;

    // Parse profit share if available
    const profitShare = data['profit_share'] as Record<string, number> | undefined;

    return {
      response: String(data['response'] ?? ''),
      sources,
      retrievalInfo,
      metadata,
      usage,
      profitShare,
    };
  }

  /**
   * Placeholder model for retrieval-only requests. The aggregator requires a
   * `model` field on every request, but short-circuits before dereferencing it
   * when `retrieval_only` is set, so an empty ref is never contacted.
   */
  private static readonly RETRIEVAL_ONLY_MODEL: EndpointRef = {
    url: '',
    slug: '',
    name: 'retrieval-only',
  };

  /**
   * Retrieve documents from data sources without model generation.
   *
   * Drives the aggregator's retrieval-only path: data sources are queried in
   * parallel (with satellite-token auth and MPP payment handled server-side,
   * exactly like {@link complete}), but no model is invoked.
   *
   * Prefer the symmetric `client.search.query(...)` facade; this is the
   * underlying primitive.
   *
   * @param options - Search options
   * @returns SearchResponse with retrieved documents and per-source metadata
   * @throws {EndpointResolutionError} If a data source cannot be resolved
   * @throws {AggregatorError} If the aggregator service fails
   */
  async retrieve(options: SearchQueryOptions): Promise<SearchResponse> {
    const chatOptions: ChatOptions = {
      prompt: options.prompt,
      model: ChatResource.RETRIEVAL_ONLY_MODEL,
      dataSources: options.dataSources,
      topK: options.topK,
      similarityThreshold: options.similarityThreshold,
      aggregatorUrl: options.aggregatorUrl,
      guestMode: options.guestMode,
    };

    const { requestBody, effectiveAggregatorUrl } = await this.prepareRequest(
      chatOptions,
      false,
      true
    );

    const response = await fetch(`${effectiveAggregatorUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });

    if (!response.ok) {
      return this.handleAggregatorErrorResponse(response);
    }

    const data = (await response.json()) as Record<string, unknown>;

    const sources = this.parseDocumentSources(
      data['sources'] as Record<string, unknown> | undefined
    );
    const documents: SearchDocument[] = Object.entries(sources).map(([title, source]) => ({
      title,
      slug: source.slug,
      content: source.content,
    }));

    const retrievalInfo = this.parseRetrievalInfo(
      data['retrieval_info'] as Record<string, unknown>[] | undefined
    );
    const metadata = this.parseMetadata((data['metadata'] as Record<string, unknown>) ?? {});

    return { documents, retrievalInfo, metadata };
  }

  /**
   * Send a chat request and stream response events.
   *
   * This method automatically:
   * 1. Resolves endpoints and extracts owner information
   * 2. Exchanges Hub tokens for satellite tokens (one per unique owner)
   * 3. Passes the user's Hub access token for MPP payment authorization
   * 4. Sends tokens to the aggregator for forwarding to SyftAI-Space
   *
   * @param options - Chat completion options
   * @yields ChatStreamEvent objects as they arrive
   */
  async *stream(options: ChatOptions): AsyncGenerator<ChatStreamEvent, void, unknown> {
    const { requestBody, effectiveAggregatorUrl } = await this.prepareRequest(options, true);

    const response = await fetch(`${effectiveAggregatorUrl}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });

    if (!response.ok) {
      return this.handleAggregatorErrorResponse(response);
    }

    if (!response.body) {
      throw new AggregatorError('No response body from aggregator');
    }

    for await (const { event: eventName, data: dataStr } of readSSEEvents(response)) {
      if (eventName === 'message') continue; // chat protocol always names events
      try {
        const data = JSON.parse(dataStr) as Record<string, unknown>;
        const event = this.parseSSEEvent(eventName, data);
        if (event) {
          yield event;
        }
      } catch {
        yield { type: 'error', message: `Failed to parse SSE data: ${dataStr}` };
      }
    }
  }

  /**
   * Parse an SSE event into a typed event object.
   */
  private parseSSEEvent(eventType: string, data: Record<string, unknown>): ChatStreamEvent | null {
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

      case 'reranking_start':
        return {
          type: 'reranking_start',
          documents: Number(data['documents'] ?? 0),
        };

      case 'reranking_complete':
        return {
          type: 'reranking_complete',
          documents: Number(data['documents'] ?? 0),
          timeMs: Number(data['time_ms'] ?? 0),
        };

      case 'generation_start':
        return { type: 'generation_start' };

      case 'generation_heartbeat':
        return {
          type: 'generation_heartbeat',
          elapsedMs: Number(data['elapsed_ms'] ?? 0),
        };

      case 'token':
        return {
          type: 'token',
          content: String(data['content'] ?? ''),
        };

      case 'done': {
        // Parse document sources (new format: dict of title -> {slug, content})
        const sourcesData = data['sources'] as Record<string, unknown> | undefined;
        const sources = this.parseDocumentSources(sourcesData);

        // Parse retrieval info (metadata about each data source retrieval)
        const retrievalInfoData = data['retrieval_info'] as Record<string, unknown>[] | undefined;
        const retrievalInfo = this.parseRetrievalInfo(retrievalInfoData);

        const metadataData = data['metadata'] as Record<string, unknown> | undefined;
        const metadata = this.parseMetadata(metadataData ?? {});

        // Parse usage if available (only from non-streaming mode)
        const usageData = data['usage'] as Record<string, unknown> | undefined;
        const usage = usageData ? this.parseUsage(usageData) : undefined;

        // Parse profit share if available
        const profitShare = data['profit_share'] as Record<string, number> | undefined;

        // Parse clean response (cite-tag-stripped) if attribution ran
        const response = data['response'] as string | undefined;

        return { type: 'done', sources, retrievalInfo, metadata, usage, profitShare, response };
      }

      case 'error':
        return {
          type: 'error',
          message: String(data['message'] ?? 'Unknown error'),
        };

      default:
        console.warn(`[SyftHub] Unknown SSE event type received from aggregator: ${eventType}`);
        return {
          type: 'error',
          message: `Unknown event type: ${eventType}`,
        };
    }
  }

  private async getAvailableEndpoints(
    endpointType: EndpointType,
    limit: number
  ): Promise<EndpointPublic[]> {
    const results: EndpointPublic[] = [];

    for await (const endpoint of this.hub.browse()) {
      if (results.length >= limit) break;
      if (endpoint.type !== endpointType) continue;
      if (endpoint.connect.some((conn) => conn.enabled && conn.config['url'])) {
        results.push(endpoint);
      }
    }

    return results;
  }

  /**
   * Get model endpoints that have connection URLs configured.
   *
   * @param limit - Maximum number of results (default: 20)
   * @returns Array of EndpointPublic objects for models with URLs
   */
  async getAvailableModels(limit = 20): Promise<EndpointPublic[]> {
    return this.getAvailableEndpoints(EndpointType.MODEL, limit);
  }

  /**
   * Get data source endpoints that have connection URLs configured.
   *
   * @param limit - Maximum number of results (default: 20)
   * @returns Array of EndpointPublic objects for data sources with URLs
   */
  async getAvailableDataSources(limit = 20): Promise<EndpointPublic[]> {
    return this.getAvailableEndpoints(EndpointType.DATA_SOURCE, limit);
  }
}
