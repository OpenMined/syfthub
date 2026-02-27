/**
 * TypeScript types for the desktop chat feature.
 *
 * These mirror the Go types in types.go and are consumed by the
 * useChatWorkflow hook and ChatView component.
 */

// =============================================================================
// Wails Event Payload
// =============================================================================

/** Discriminated union for the "chat:stream-event" Wails event payload. */
export type ChatStreamEvent =
  | RetrievalStartEvent
  | SourceCompleteEvent
  | RetrievalCompleteEvent
  | GenerationStartEvent
  | TokenEvent
  | DoneEvent
  | ErrorEvent;

export interface RetrievalStartEvent {
  type: 'retrieval_start';
  sourceCount: number;
}

export interface SourceCompleteEvent {
  type: 'source_complete';
  path: string;
  status: 'success' | 'error' | 'timeout';
  documentsRetrieved: number;
}

export interface RetrievalCompleteEvent {
  type: 'retrieval_complete';
  totalDocuments: number;
  timeMs: number;
}

export interface GenerationStartEvent {
  type: 'generation_start';
}

export interface TokenEvent {
  type: 'token';
  content: string;
}

export interface DoneEvent {
  type: 'done';
  sources: Record<string, ChatDocumentSource>;
  /** Position-annotated response with [cite:N-start:end] markers. */
  response?: string;
  profitShare?: Record<string, number>;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

// =============================================================================
// Request Types (sent to Go StreamChat)
// =============================================================================

export interface ChatEndpointRef {
  url: string;
  slug: string;
  name: string;
  tenantName?: string;
  ownerUsername?: string;
}

export interface ChatRequestPayload {
  prompt: string;
  model: ChatEndpointRef;
  dataSources: ChatEndpointRef[];
  messages?: { role: string; content: string }[];
  topK?: number;
  maxTokens?: number;
  temperature?: number;
}

// =============================================================================
// Workflow State Machine Types
// =============================================================================

export type WorkflowPhase =
  | 'idle'       // Ready for user input
  | 'preparing'  // Building and submitting request
  | 'streaming'  // Receiving SSE events
  | 'complete'   // Finished successfully
  | 'error';     // Failed

export interface SourceProgressInfo {
  path: string;
  displayName: string;
  status: 'pending' | 'success' | 'error' | 'timeout';
  documents: number;
}

export interface RetrievalProgress {
  completed: number;
  total: number;
  documentsFound: number;
}

export interface PipelineStep {
  id: string;
  label: string;
  description?: string;
  status: 'pending' | 'active' | 'complete';
}

export interface ProcessingStatus {
  phase: 'retrieving' | 'generating' | 'streaming' | 'error';
  message: string;
  retrieval?: RetrievalProgress;
  completedSources: SourceProgressInfo[];
  steps: PipelineStep[];
  generationElapsedMs?: number;
  timing?: {
    retrievalMs?: number;
  };
}

export interface ChatDocumentSource {
  slug: string;
  content: string;
}

export type SourcesData = Record<string, ChatDocumentSource>;

export interface WorkflowResult {
  query: string;
  content: string;
  sources: SourcesData;
  annotatedResponse?: string;
  profitShare?: Record<string, number>;
}

export interface WorkflowState {
  phase: WorkflowPhase;
  query: string | null;
  selectedSources: Set<string>;
  processingStatus: ProcessingStatus | null;
  streamedContent: string;
  aggregatorSources: SourcesData;
  error: string | null;
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

// =============================================================================
// Reducer Actions
// =============================================================================

export type WorkflowAction =
  | { type: 'START_EXECUTING'; query: string; sourceIds: Set<string> }
  | { type: 'START_STREAMING'; status: ProcessingStatus }
  | { type: 'STREAM_EVENT'; event: ChatStreamEvent }
  | { type: 'UPDATE_CONTENT'; content: string }
  | { type: 'COMPLETE'; sources: SourcesData; annotatedResponse?: string; profitShare?: Record<string, number> }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET' };
