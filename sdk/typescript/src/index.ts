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
} from './errors.js';

// Chat-specific errors
export {
  AggregatorError,
  EndpointResolutionError,
} from './resources/chat.js';
export {
  RetrievalError,
  GenerationError,
} from './resources/syftai.js';

// Pagination
export { PageIterator } from './pagination.js';
export type { PageFetcher } from './pagination.js';

// Models - Enums and constants
export {
  Visibility,
  EndpointType,
  UserRole,
  OrganizationRole,
  // Accounting enums
  TransactionStatus,
  CreatorType,
} from './models/index.js';

// Models - Types
export type {
  // User types
  User,
  UserRegisterInput,
  UserUpdateInput,
  PasswordChangeInput,
  // Endpoint types
  Policy,
  Connection,
  Endpoint,
  EndpointPublic,
  EndpointCreateInput,
  EndpointUpdateInput,
  // Accounting types
  AccountingUser,
  Transaction,
  CreateTransactionInput,
  CreateDelegatedTransactionInput,
  UpdatePasswordInput,
  TransactionResponse,
  TransactionTokenResponse,
  // Backward compatibility (deprecated)
  AccountingBalance,
  AccountingTransaction,
  // Chat types
  EndpointRef,
  Document,
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
  // Accounting helpers
  parseTransaction,
  isTransactionPending,
  isTransactionCompleted,
  isTransactionCancelled,
} from './models/index.js';

// Accounting Resource (standalone client for external accounting service)
export {
  AccountingResource,
  createAccountingResource,
} from './resources/accounting.js';
export type {
  AccountingResourceOptions,
  TransactionsOptions,
} from './resources/accounting.js';

// Chat Resource (for type hints)
export { ChatResource } from './resources/chat.js';

// SyftAI Resource (for type hints)
export { SyftAIResource } from './resources/syftai.js';

// Resource option types (for type-safe usage)
export type { ListEndpointsOptions } from './resources/my-endpoints.js';
export type { BrowseOptions, TrendingOptions } from './resources/hub.js';
