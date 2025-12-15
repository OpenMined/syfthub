/**
 * Aggregator API client for the frontend.
 * Handles chat requests and streaming responses from the RAG orchestration service.
 */

// Endpoint reference with URL and slug for SyftAI-Space API
export interface EndpointReference {
  url: string; // Base URL of the SyftAI-Space instance
  slug: string; // Endpoint slug for API path construction
  name: string; // Display name for attribution/logging
  tenant_name?: string; // Tenant name for X-Tenant-Name header (SyftAI-Space multi-tenancy)
}

// Request schema matching aggregator/src/aggregator/schemas/requests.py
export interface AggregatorChatRequest {
  prompt: string;
  user_email: string; // Required for SyftAI-Space visibility/policy checks
  model: EndpointReference; // Model endpoint with URL and slug
  data_sources: EndpointReference[]; // Data source endpoints with URLs and slugs
  top_k?: number; // 1-20, default 5
  stream?: boolean;
  max_tokens?: number; // Optional LLM parameter, default 1024
  temperature?: number; // Optional LLM parameter, default 0.7
  similarity_threshold?: number; // Optional retrieval threshold, default 0.5
}

// Response schema matching aggregator/src/aggregator/schemas/responses.py
export interface AggregatorSourceInfo {
  path: string;
  documents_retrieved: number;
  status: 'success' | 'error' | 'timeout';
  error_message?: string;
}

export interface AggregatorResponseMetadata {
  retrieval_time_ms: number;
  generation_time_ms: number;
  total_time_ms: number;
}

export interface AggregatorChatResponse {
  response: string;
  sources: AggregatorSourceInfo[];
  metadata: AggregatorResponseMetadata;
}

// SSE Event types for streaming
export type AggregatorStreamEventType =
  | 'retrieval_start'
  | 'source_complete'
  | 'retrieval_complete'
  | 'generation_start'
  | 'token'
  | 'done'
  | 'error';

export interface AggregatorStreamEvent {
  event: AggregatorStreamEventType;
  data: Record<string, unknown>;
}

// Aggregator client configuration
const AGGREGATOR_BASE_URL = '/aggregator/api/v1';

// Error response type
interface ErrorResponse {
  detail?: string;
}

/**
 * Send a chat request to the aggregator (non-streaming).
 */
export async function sendChatRequest(
  request: AggregatorChatRequest,
  token?: string
): Promise<AggregatorChatResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${AGGREGATOR_BASE_URL}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...request, stream: false })
  });

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as ErrorResponse;
    throw new Error(errorData.detail ?? `Aggregator error: ${String(response.status)}`);
  }

  return response.json() as Promise<AggregatorChatResponse>;
}

/**
 * Parse a single SSE line and return the parsed event or updated state.
 */
function parseSSELine(
  line: string,
  currentEvent: string | null
): { parsed: AggregatorStreamEvent | null; nextEvent: string | null } {
  if (line.startsWith('event: ')) {
    return { parsed: null, nextEvent: line.slice(7).trim() };
  }

  if (line.startsWith('data: ') && currentEvent) {
    try {
      const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
      return {
        parsed: { event: currentEvent as AggregatorStreamEventType, data },
        nextEvent: null
      };
    } catch {
      return { parsed: null, nextEvent: null };
    }
  }

  return { parsed: null, nextEvent: currentEvent };
}

/**
 * Send a streaming chat request to the aggregator.
 * Returns an async generator that yields SSE events.
 */
export async function* streamChatRequest(
  request: AggregatorChatRequest,
  token?: string,
  signal?: AbortSignal
): AsyncGenerator<AggregatorStreamEvent, void, unknown> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${AGGREGATOR_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...request, stream: true }),
    signal
  });

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as ErrorResponse;
    throw new Error(errorData.detail ?? `Aggregator error: ${String(response.status)}`);
  }

  const body = response.body;
  if (!body) {
    throw new Error('No response body for streaming');
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const result = await reader.read();

      if (result.done) {
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });

      // Parse SSE events from buffer
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? ''; // Keep incomplete line in buffer

      let currentEvent: string | null = null;

      for (const line of lines) {
        const { parsed, nextEvent } = parseSSELine(line, currentEvent);
        currentEvent = nextEvent;
        if (parsed) {
          yield parsed;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Helper to build aggregator request from chat view state.
 */
export function buildChatRequest(
  prompt: string,
  userEmail: string,
  model: EndpointReference,
  dataSources: EndpointReference[],
  options: {
    topK?: number;
    stream?: boolean;
    maxTokens?: number;
    temperature?: number;
    similarityThreshold?: number;
  } = {}
): AggregatorChatRequest {
  return {
    prompt,
    user_email: userEmail,
    model: model,
    data_sources: dataSources,
    top_k: options.topK ?? 5,
    stream: options.stream ?? false,
    ...(options.maxTokens !== undefined && { max_tokens: options.maxTokens }),
    ...(options.temperature !== undefined && { temperature: options.temperature }),
    ...(options.similarityThreshold !== undefined && {
      similarity_threshold: options.similarityThreshold
    })
  };
}
