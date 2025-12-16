/* eslint-disable sonarjs/deprecation, @typescript-eslint/no-deprecated */
/**
 * Aggregator API types for the frontend.
 *
 * @deprecated These types are kept for reference only.
 * The frontend now uses the TypeScript SDK for chat functionality.
 * See: @/lib/sdk-client and @syfthub/sdk
 *
 * For new code, use the SDK types instead:
 * - EndpointReference → EndpointRef from @syfthub/sdk
 * - AggregatorChatRequest → ChatOptions from @syfthub/sdk
 * - AggregatorChatResponse → ChatResponse from @syfthub/sdk
 * - AggregatorStreamEvent → ChatStreamEvent from @syfthub/sdk
 *
 * Usage:
 * ```typescript
 * import { syftClient } from '@/lib/sdk-client';
 * import type { EndpointRef } from '@/lib/sdk-client';
 *
 * // Streaming chat
 * for await (const event of syftClient.chat.stream({
 *   prompt: 'Hello',
 *   model: modelRef,
 *   dataSources: [sourceRef],
 * })) {
 *   if (event.type === 'token') {
 *     console.log(event.content);
 *   }
 * }
 * ```
 */

// =============================================================================
// Legacy Types (Deprecated - use SDK types instead)
// =============================================================================

/**
 * @deprecated Use EndpointRef from @syfthub/sdk instead
 */
export interface EndpointReference {
  url: string;
  slug: string;
  name: string;
  tenant_name?: string;
}

/**
 * @deprecated Use ChatOptions from @syfthub/sdk instead
 */
export interface AggregatorChatRequest {
  prompt: string;
  user_email: string;
  model: EndpointReference;
  data_sources: EndpointReference[];
  top_k?: number;
  stream?: boolean;
  max_tokens?: number;
  temperature?: number;
  similarity_threshold?: number;
}

/**
 * @deprecated Use SourceInfo from @syfthub/sdk instead
 */
export interface AggregatorSourceInfo {
  path: string;
  documents_retrieved: number;
  status: 'success' | 'error' | 'timeout';
  error_message?: string;
}

/**
 * @deprecated Use ChatMetadata from @syfthub/sdk instead
 */
export interface AggregatorResponseMetadata {
  retrieval_time_ms: number;
  generation_time_ms: number;
  total_time_ms: number;
}

/**
 * @deprecated Use ChatResponse from @syfthub/sdk instead
 */
export interface AggregatorChatResponse {
  response: string;
  sources: AggregatorSourceInfo[];
  metadata: AggregatorResponseMetadata;
}

/**
 * @deprecated Use ChatStreamEvent from @syfthub/sdk instead
 */
export type AggregatorStreamEventType =
  | 'retrieval_start'
  | 'source_complete'
  | 'retrieval_complete'
  | 'generation_start'
  | 'token'
  | 'done'
  | 'error';

/**
 * @deprecated Use ChatStreamEvent from @syfthub/sdk instead
 */
export interface AggregatorStreamEvent {
  event: AggregatorStreamEventType;
  data: Record<string, unknown>;
}
