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
export type SourceStatus = 'success' | 'error' | 'timeout';

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
 * Fired when model generation begins.
 */
export interface GenerationStartEvent {
  type: 'generation_start';
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
}

/**
 * Fired on error.
 */
export interface ErrorEvent {
  type: 'error';
  message: string;
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
  | GenerationStartEvent
  | TokenEvent
  | DoneEvent
  | ErrorEvent;
