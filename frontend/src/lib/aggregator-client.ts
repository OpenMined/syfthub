/**
 * Aggregator API client for the frontend.
 * Handles chat requests and streaming responses from the RAG orchestration service.
 */

// Endpoint reference with URL for direct access
export interface EndpointReference {
  url: string; // Base URL of the endpoint (aggregator appends /chat or /query)
  name: string; // Display name for attribution/logging
}

// Request schema matching aggregator/src/aggregator/schemas/requests.py
export interface AggregatorChatRequest {
  prompt: string;
  model: EndpointReference; // Model endpoint with URL
  data_sources: EndpointReference[]; // Data source endpoints with URLs
  top_k?: number; // 1-20, default 5
  stream?: boolean;
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
    let done = false;
    while (!done) {
      const result = await reader.read();
      done = result.done;

      if (done) {
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });

      // Parse SSE events from buffer
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? ''; // Keep incomplete line in buffer

      let currentEvent: string | null = null;

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ') && currentEvent) {
          try {
            const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
            yield {
              event: currentEvent as AggregatorStreamEventType,
              data
            };
          } catch {
            // Skip malformed data
          }
          currentEvent = null;
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
  model: EndpointReference,
  dataSources: EndpointReference[],
  options: { topK?: number; stream?: boolean } = {}
): AggregatorChatRequest {
  return {
    prompt,
    model: model,
    data_sources: dataSources,
    top_k: options.topK ?? 5,
    stream: options.stream ?? false
  };
}
