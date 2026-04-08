/**
 * SyftHub TypeScript SDK
 *
 * A TypeScript client library for the SyftHub API.
 *
 * @example
 * import { SyftHubClient, EndpointType, Visibility } from '@syfthub/sdk';
 *
 * const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });
 *
 * // Login
 * const user = await client.auth.login('alice', 'password');
 *
 * // Create an endpoint
 * const endpoint = await client.myEndpoints.create({
 *   name: 'My Model',
 *   type: EndpointType.MODEL,
 *   visibility: Visibility.PUBLIC,
 * });
 *
 * // Browse the hub
 * for await (const ep of client.hub.browse()) {
 *   console.log(ep.name);
 * }
 *
 * // Chat with RAG via aggregator
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
 *
 * @packageDocumentation
 */

// Main client
export { SyftHubClient } from './client.js';
export type { SyftHubClientOptions } from './client.js';

// HTTP types (for advanced usage)
export type { AuthTokens } from './http.js';

// Errors
export {
  SyftHubError,
  APIError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  NetworkError,
  ConfigurationError,
  // User registration errors
  UserAlreadyExistsError,
} from './errors.js';

// Chat-specific errors
export { AggregatorError, EndpointResolutionError } from './resources/chat.js';
export { RetrievalError, GenerationError } from './resources/syftai.js';

// Pagination
export { PageIterator } from './pagination.js';
export type { PageFetcher } from './pagination.js';

// Models - Enums and constants
export {
  Visibility,
  EndpointType,
  UserRole,
  OrganizationRole,
} from './models/index.js';

// Models - Types
export type {
  // User types
  User,
  UserRegisterInput,
  UserUpdateInput,
  PasswordChangeInput,
  RegisterResult,
  VerifyOTPInput,
  PasswordResetRequestInput,
  PasswordResetConfirmInput,
  AuthConfig,
  AccountingCredentials,
  HeartbeatInput,
  HeartbeatResponse,
  UserAggregator,
  UserAggregatorCreateInput,
  UserAggregatorUpdateInput,
  // Endpoint types
  Policy,
  Connection,
  Endpoint,
  EndpointPublic,
  EndpointCreateInput,
  EndpointUpdateInput,
  SyncEndpointsResponse,
  // API Token types
  APIToken,
  APITokenScope,
  APITokenCreateResponse,
  CreateAPITokenInput,
  UpdateAPITokenInput,
  APITokenListResponse,
  // Wallet types
  WalletInfo,
  WalletBalance,
  WalletTransaction,
  TransactionTokensResponse,
  // Chat types
  EndpointRef,
  Document,
  DocumentSource,
  SourceStatus,
  SourceInfo,
  ChatMetadata,
  ChatResponse,
  Message,
  ChatOptions,
  QueryDataSourceOptions,
  QueryModelOptions,
  // Chat streaming events
  ChatStreamEvent,
  RetrievalStartEvent,
  SourceCompleteEvent,
  RetrievalCompleteEvent,
  GenerationStartEvent,
  TokenEvent,
  DoneEvent,
  ErrorEvent,
} from './models/index.js';

// Model helpers
export {
  getEndpointOwnerType,
  getEndpointPublicPath,
} from './models/index.js';

// Accounting Resource (MPP wallet operations)
export { AccountingResource, createAccountingResource } from './resources/accounting.js';
export type { AccountingResourceOptions, TransactionsOptions } from './resources/accounting.js';

// Agent Resource and types
export { AgentResource, AgentSessionClient, AgentSessionError } from './resources/agent.js';
export type {
  AgentEvent,
  AgentSessionState,
  AgentSessionOptions,
  AgentConfig,
  AgentHistoryMessage,
  ThinkingEvent as AgentThinkingEvent,
  ToolCallEvent as AgentToolCallEvent,
  ToolResultEvent as AgentToolResultEvent,
  AgentMessageEvent,
  TokenEvent as AgentTokenEvent,
  StatusEvent as AgentStatusEvent,
  RequestInputEvent as AgentRequestInputEvent,
  SessionCreatedEvent as AgentSessionCreatedEvent,
  SessionCompletedEvent as AgentSessionCompletedEvent,
  SessionFailedEvent as AgentSessionFailedEvent,
  AgentErrorEvent,
} from './models/agent.js';

// Chat Resource (for type hints)
export { ChatResource } from './resources/chat.js';

// SyftAI Resource (for type hints)
export { SyftAIResource } from './resources/syftai.js';

// API Tokens Resource (for type hints)
export { APITokensResource } from './resources/api-tokens.js';

// Aggregators Resource (for type hints)
export { AggregatorsResource } from './resources/aggregators.js';

// Resource option types (for type-safe usage)
export type { ListEndpointsOptions } from './resources/my-endpoints.js';
export type { BrowseOptions, TrendingOptions } from './resources/hub.js';
