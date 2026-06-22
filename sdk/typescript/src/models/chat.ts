/**
 * Chat-related types for the SyftHub SDK.
 *
 * These types are used for interacting with the Aggregator service
 * for RAG (Retrieval-Augmented Generation) workflows.
 */

/**
 * Reference to a SyftAI-Space endpoint with connection details.
 *
 * Can be constructed directly or resolved from an EndpointPublic object.
 *
 * @example
 * const ref: EndpointRef = {
 *   url: 'http://syftai-space:8080',
 *   slug: 'my-model',
 *   name: 'My Model',
 *   ownerUsername: 'alice',
 * };
 */
export interface EndpointRef {
  /** Base URL of the SyftAI-Space instance */
  url: string;
  /** Endpoint slug for the API path */
  slug: string;
  /** Display name of the endpoint */
  name?: string;
  /** Tenant name for X-Tenant-Name header */
  tenantName?: string;
  /** Owner's username - used as the audience for satellite token authentication */
  ownerUsername?: string;
}

/**
 * A document retrieved from a data source.
 */
export interface Document {
  /** The document content */
  content: string;
  /** Relevance score (0-1) */
  score: number;
  /** Additional metadata */
  metadata: Record<string, unknown>;
}

/**
 * Status of a data source query.
 */
export type SourceStatus = 'success' | 'error' | 'timeout' | 'payment_failed' | 'access_denied';

/**
 * Information about a data source retrieval (metadata).
 */
export interface SourceInfo {
  /** Endpoint path (owner/slug) */
  path: string;
  /** Number of documents retrieved from this source */
  documentsRetrieved: number;
  /** Query status */
  status: SourceStatus;
  /** Error message if status is error/timeout */
  errorMessage?: string;
}

/**
 * A document source entry with endpoint path and content.
 * Used in the sources dict of ChatResponse, keyed by document title.
 */
export interface DocumentSource {
  /** Endpoint path (owner/slug) where document was retrieved */
  slug: string;
  /** The actual document content */
  content: string;
}

/**
 * Timing metadata for chat response.
 */
export interface ChatMetadata {
  /** Time spent retrieving documents (ms) */
  retrievalTimeMs: number;
  /** Time spent generating response (ms) */
  generationTimeMs: number;
  /** Total request time (ms) */
  totalTimeMs: number;
}

/**
 * Token usage information from model generation.
 */
export interface TokenUsage {
  /** Number of tokens in the prompt */
  promptTokens: number;
  /** Number of tokens in the completion */
  completionTokens: number;
  /** Total tokens used */
  totalTokens: number;
}

/**
 * The "to whom" of a billing entry — the endpoint owner / publisher.
 *
 * All fields are optional; `walletAddress` is a public MPP address only and
 * never a private key.
 */
export interface Recipient {
  /** Endpoint owner / publisher username */
  username?: string;
  /** Recipient email */
  email?: string;
  /** Public MPP wallet address (never a private key) */
  walletAddress?: string;
}

/**
 * A rail-native transaction reference for a billing entry.
 *
 * `id` is the rail-native identifier (Tempo tx hash for `mpp`; the ledger
 * transaction id for `xendit` / `stripe`); `rail` is the discriminator.
 */
export interface Transaction {
  /** Payment rail discriminator (mpp, xendit, stripe, ...) */
  rail: string;
  /** Rail-native transaction id */
  id: string;
  /** Secondary reference (e.g. MPP external_id) */
  reference?: string;
}

/**
 * A single policy-metadata entry from a queried source.
 *
 * Emitted by both payment and non-payment policies. When surfaced via the
 * aggregated {@link Billing} block, `source` carries the `owner/slug` of the
 * source that produced the entry; on the direct path it is absent.
 */
export interface BillingEntry {
  /** Source endpoint path (owner/slug); absent if direct */
  source?: string;
  /** Policy type (e.g. mpp_per_request, rate_limit, pii_filter) */
  policyType: string;
  /** Policy kind (payment, access, transform, rate_limit) */
  kind: string;
  /** Outcome status (charged, refunded, free, rejected, applied, skipped) */
  status: string;
  /** Charged amount, if any */
  amount?: number;
  /** Currency code, if any */
  currency?: string;
  /** Who the payment is owed to, if any */
  recipient?: Recipient;
  /** Rail-native transaction reference, if any */
  transaction?: Transaction;
  /** Machine-readable reason code (e.g. PAYMENT_REQUIRED) */
  reasonCode?: string;
  /** Human-readable reason message */
  reason?: string;
  /** Extra structured details (e.g. { documents: 3 }) */
  details: Record<string, unknown>;
}

/**
 * Aggregated billing block surfaced on chat and search responses.
 *
 * `totalCost` is the sum of entries with `status === "charged"` (null if none
 * charged); `currency` is the common currency or null if mixed. No FX
 * conversion is performed — each entry keeps its own currency.
 */
export interface Billing {
  /** Sum of charged entries; null if nothing charged */
  totalCost: number | null;
  /** Common currency, or null if mixed */
  currency: string | null;
  /** Per-source policy-metadata entries */
  entries: BillingEntry[];
}

/**
 * Raw policy-metadata block returned on the direct syft-space path.
 *
 * Unlike the aggregated {@link Billing} block, this is the per-source object
 * exactly as the syft-space `/query` response carries it: an `outcome` string
 * plus the list of {@link BillingEntry} items (whose `source` key is absent on
 * the direct path). No aggregation or total is applied.
 */
export interface PolicyMetadata {
  /** Query outcome (e.g. success, payment_required) */
  outcome: string;
  /** Per-policy metadata entries */
  entries: BillingEntry[];
}

/**
 * Response from a chat completion request.
 */
export interface ChatResponse {
  /** The generated response text */
  response: string;
  /** Retrieved documents keyed by title, with endpoint slug and content */
  sources: Record<string, DocumentSource>;
  /** Metadata about each data source retrieval (status, count, errors) */
  retrievalInfo: SourceInfo[];
  /** Timing metadata */
  metadata: ChatMetadata;
  /** Token usage if available */
  usage?: TokenUsage;
  /** Normalized contribution scores per source (owner/slug to fraction 0-1) */
  profitShare?: Record<string, number>;
  /** Aggregated payment-policy metadata across queried sources */
  billing?: Billing;
}

/**
 * A chat message for model queries.
 */
export interface Message {
  /** Message role (system, user, assistant) */
  role: 'system' | 'user' | 'assistant';
  /** Message content */
  content: string;
}

/**
 * Options for chat completion.
 */
export interface ChatOptions {
  /** The user's question or prompt */
  prompt: string;
  /** Model endpoint (path string, EndpointRef, or EndpointPublic) */
  model: string | EndpointRef;
  /** Optional list of data source endpoints for context */
  dataSources?: (string | EndpointRef)[];
  /** Number of documents to retrieve per source (default: 5) */
  topK?: number;
  /** Maximum tokens to generate (default: 1024) */
  maxTokens?: number;
  /** Generation temperature (default: 0.7) */
  temperature?: number;
  /** Minimum similarity for retrieved docs (default: 0.5) */
  similarityThreshold?: number;
  /** AbortSignal for request cancellation */
  signal?: AbortSignal;
  /** Custom aggregator URL to use instead of the default */
  aggregatorUrl?: string;
  /** Peer token for NATS tunneling (auto-fetched if tunneling endpoints detected) */
  peerToken?: string;
  /** Peer channel for NATS replies (auto-fetched if tunneling endpoints detected) */
  peerChannel?: string;
  /** Use guest mode for unauthenticated access to policy-free endpoints */
  guestMode?: boolean;
  /** Conversation history (prior turns) for multi-turn context */
  messages?: Message[];
}

/**
 * A single document returned by a retrieval-only search.
 *
 * Unlike {@link Document} (the low-level direct-query shape), this carries the
 * document title and the source endpoint path, matching the aggregated
 * `sources` map returned by the aggregator's retrieval-only path.
 */
export interface SearchDocument {
  /** Document title (key in the sources map) */
  title: string;
  /** Source endpoint path (owner/slug) the document came from */
  slug: string;
  /** The document content */
  content: string;
}

/**
 * Options for a retrieval-only search via the Aggregator.
 *
 * Symmetric to {@link ChatOptions} minus the model: data sources are queried
 * for relevant documents, but no model is invoked.
 */
export interface SearchQueryOptions {
  /** The search query */
  prompt: string;
  /** Data source endpoints (paths, EndpointRefs, or `collective/<slug>` paths) */
  dataSources?: (string | EndpointRef)[];
  /** Number of documents to retrieve per source (default: 5) */
  topK?: number;
  /** Minimum similarity for retrieved docs (default: 0.5) */
  similarityThreshold?: number;
  /** Custom aggregator URL to use instead of the default */
  aggregatorUrl?: string;
  /** Use guest mode for unauthenticated access to policy-free endpoints */
  guestMode?: boolean;
  /** AbortSignal for request cancellation */
  signal?: AbortSignal;
}

/**
 * Response from a retrieval-only search via the Aggregator.
 *
 * Mirrors {@link ChatResponse} minus the generated text: retrieval runs across
 * the data sources (with satellite-token auth and MPP payment handled by the
 * aggregator), but no model is invoked.
 */
export interface SearchResponse {
  /** Retrieved documents across all data sources */
  documents: SearchDocument[];
  /** Metadata about each data source retrieval (status, count, errors) */
  retrievalInfo: SourceInfo[];
  /** Timing metadata */
  metadata: ChatMetadata;
  /** Aggregated payment-policy metadata across queried sources */
  billing?: Billing;
}

/**
 * Result of a direct data-source query (`client.syftai.queryDataSource`).
 *
 * Carries the retrieved documents plus the raw `policyMetadata` block from the
 * syft-space `/query` response (Boundary A), so direct-query callers get the
 * same authoritative payment/policy metadata the aggregator surfaces.
 */
export interface DataSourceQueryResult {
  /** Retrieved documents */
  documents: Document[];
  /** Raw policy metadata from the syft-space response, if present */
  policyMetadata?: PolicyMetadata;
}

/**
 * Options for querying a data source directly.
 */
export interface QueryDataSourceOptions {
  /** EndpointRef with URL and slug */
  endpoint: EndpointRef;
  /** The search query */
  query: string;
  /** User email for visibility/policy checks */
  userEmail: string;
  /** Number of documents to retrieve (default: 5) */
  topK?: number;
  /** Minimum similarity score (default: 0.5) */
  similarityThreshold?: number;
  /**
   * Pre-minted satellite token to send as `Authorization: Bearer`. If omitted,
   * one is minted automatically when an owner is known (see `ownerUsername` /
   * `endpoint.ownerUsername`).
   */
  authorizationToken?: string;
  /**
   * Endpoint owner username used as the satellite-token audience. Falls back to
   * `endpoint.ownerUsername`.
   */
  ownerUsername?: string;
  /**
   * If true, settle an MPP `402 Payment Required` challenge via the Hub wallet
   * and retry. If false (default), a `402` throws a `RetrievalError`.
   */
  pay?: boolean;
}

/**
 * Options for querying a model directly.
 */
export interface QueryModelOptions {
  /** EndpointRef with URL and slug */
  endpoint: EndpointRef;
  /** List of chat messages */
  messages: Message[];
  /** User email for visibility/policy checks */
  userEmail: string;
  /** Maximum tokens to generate (default: 1024) */
  maxTokens?: number;
  /** Generation temperature (default: 0.7) */
  temperature?: number;
}

// =============================================================================
// Streaming Event Types
// =============================================================================

/**
 * Fired when retrieval begins.
 */
export interface RetrievalStartEvent {
  type: 'retrieval_start';
  sourceCount: number;
}

/**
 * Fired when a single source finishes querying.
 */
export interface SourceCompleteEvent {
  type: 'source_complete';
  path: string;
  status: string;
  documentsRetrieved: number;
}

/**
 * Fired when all retrieval is done.
 */
export interface RetrievalCompleteEvent {
  type: 'retrieval_complete';
  totalDocuments: number;
  timeMs: number;
}

/**
 * Fired when document reranking begins (after all sources complete).
 */
export interface RerankingStartEvent {
  type: 'reranking_start';
  /** Number of documents being reranked */
  documents: number;
}

/**
 * Fired when document reranking completes.
 */
export interface RerankingCompleteEvent {
  type: 'reranking_complete';
  /** Number of documents after reranking */
  documents: number;
  /** Time taken for reranking in milliseconds */
  timeMs: number;
}

/**
 * Fired when model generation begins.
 */
export interface GenerationStartEvent {
  type: 'generation_start';
}

/**
 * Fired periodically during non-streaming model generation to indicate progress.
 * Emitted every ~3 seconds while waiting for the model response.
 */
export interface GenerationHeartbeatEvent {
  type: 'generation_heartbeat';
  /** Milliseconds elapsed since generation_start */
  elapsedMs: number;
}

/**
 * Fired for each token from the model.
 */
export interface TokenEvent {
  type: 'token';
  content: string;
}

/**
 * Fired when generation completes successfully.
 */
export interface DoneEvent {
  type: 'done';
  /** Retrieved documents keyed by title, with endpoint slug and content */
  sources: Record<string, DocumentSource>;
  /** Metadata about each data source retrieval (status, count, errors) */
  retrievalInfo: SourceInfo[];
  metadata: ChatMetadata;
  /** Token usage if available (only from non-streaming mode) */
  usage?: TokenUsage;
  /** Normalized contribution scores per source (owner/slug to fraction 0-1) */
  profitShare?: Record<string, number>;
  /** Aggregated payment-policy metadata across queried sources */
  billing?: Billing;
  /**
   * Clean response text with attribution markers stripped.
   * Present when attribution ran (data sources were used). Frontends should
   * replace the streamed content with this field to remove raw <cite:[N]> tags.
   */
  response?: string;
}

/**
 * Fired on error.
 */
export interface ErrorEvent {
  type: 'error';
  message: string;
  /**
   * Billing surfaced on the error path: a paid query may be REJECTED yet still
   * carry policy/billing metadata (e.g. a charge that must be refunded).
   */
  billing?: Billing;
}

/**
 * Discriminated union of all streaming event types.
 *
 * Use type narrowing to handle each event type:
 *
 * @example
 * for await (const event of client.chat.stream(options)) {
 *   switch (event.type) {
 *     case 'token':
 *       process.stdout.write(event.content);
 *       break;
 *     case 'done':
 *       console.log(`\nCompleted in ${event.metadata.totalTimeMs}ms`);
 *       break;
 *     case 'error':
 *       console.error(`Error: ${event.message}`);
 *       break;
 *   }
 * }
 */
export type ChatStreamEvent =
  | RetrievalStartEvent
  | SourceCompleteEvent
  | RetrievalCompleteEvent
  | RerankingStartEvent
  | RerankingCompleteEvent
  | GenerationStartEvent
  | GenerationHeartbeatEvent
  | TokenEvent
  | DoneEvent
  | ErrorEvent;
