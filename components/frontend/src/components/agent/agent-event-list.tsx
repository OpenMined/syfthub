/**
 * Scrollable list rendering event cards by type.
 * Tool calls and results are merged into a single prompt-kit Tool component.
 */
import { useEffect, useRef } from 'react';

import type { ToolPart } from '@/components/prompt-kit/tool';
import type {
  AgentEvent,
  AgentSessionState,
  AgentToolCallEvent,
  AgentToolResultEvent
} from '@syfthub/sdk';

import { Tool } from '@/components/prompt-kit/tool';

import { MessageBubble } from './event-cards/message-bubble';
import { AgentStatusBadge } from './event-cards/status-badge';
import { ThinkingBlock } from './event-cards/thinking-block';

interface AgentEventListProps {
  readonly events: AgentEvent[];
  readonly streamingContent: string;
  readonly onConfirm: (toolCallId: string) => void;
  readonly onDeny: (toolCallId: string) => void;
  readonly phase: AgentSessionState;
}

/** Build a result lookup from tool_call_id → tool_result event. */
function buildResultMap(events: AgentEvent[]): Map<string, AgentToolResultEvent> {
  const map = new Map<string, AgentToolResultEvent>();
  for (const event of events) {
    if (event.type === 'agent.tool_result') {
      map.set(event.payload.tool_call_id, event);
    }
  }
  return map;
}

/** Build a ToolPart from a tool_call event and its optional paired result. */
function buildToolPart(
  callEvent: AgentToolCallEvent,
  resultEvent: AgentToolResultEvent | undefined,
  phase: AgentSessionState
): ToolPart {
  const { tool_name, arguments: arguments_, tool_call_id } = callEvent.payload;

  if (resultEvent) {
    const { status, result, error } = resultEvent.payload;
    const isSuccess = status === 'success';
    let output: Record<string, unknown> | undefined;
    if (result != null) {
      output = typeof result === 'string' ? { result } : (result as Record<string, unknown>);
    }

    return {
      type: tool_name,
      state: isSuccess ? 'output-available' : 'output-error',
      input: arguments_,
      output,
      toolCallId: tool_call_id,
      errorText: isSuccess
        ? undefined
        : (error ?? (result == null ? status : JSON.stringify(result)))
    };
  }

  const isRunning = phase === 'running' || phase === 'connecting';
  return {
    type: tool_name,
    state: isRunning ? 'input-streaming' : 'input-available',
    input: arguments_,
    toolCallId: tool_call_id
  };
}

export function AgentEventList({
  events,
  streamingContent,
  onConfirm,
  onDeny,
  phase
}: AgentEventListProps) {
  const scrollReference = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (scrollReference.current) {
      scrollReference.current.scrollTop = scrollReference.current.scrollHeight;
    }
  }, [events.length, streamingContent]);

  if (events.length === 0 && phase === 'idle') {
    return (
      <div className='text-muted-foreground flex h-full items-center justify-center'>
        <p>Send a message to start an agent session</p>
      </div>
    );
  }

  if (events.length === 0 && phase === 'connecting') {
    return (
      <div className='flex h-full items-center justify-center'>
        <div className='text-muted-foreground flex items-center gap-2'>
          <div className='h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent' />
          <span>Connecting to agent...</span>
        </div>
      </div>
    );
  }

  // Build a lookup of tool_call_id → tool_result event for pairing
  const resultMap = buildResultMap(events);

  // Track which tool_call_ids have been confirmed (have a result)
  const confirmedToolCalls = new Set(resultMap.keys());

  let lastStatusIndex = -1;
  for (const [index, event] of events.entries()) {
    if (event.type === 'agent.status') lastStatusIndex = index;
  }

  return (
    <div ref={scrollReference} className='space-y-3 p-4'>
      {events.map((event, index) => {
        switch (event.type) {
          case 'agent.thinking': {
            return (
              <ThinkingBlock
                key={index}
                content={event.payload.content}
                isStreaming={event.payload.is_streaming}
              />
            );
          }

          case 'agent.tool_call': {
            const resultEvent = resultMap.get(event.payload.tool_call_id);
            const toolPart = buildToolPart(event, resultEvent, phase);
            const needsConfirmation =
              event.payload.requires_confirmation &&
              !confirmedToolCalls.has(event.payload.tool_call_id) &&
              phase !== 'completed' &&
              phase !== 'failed' &&
              phase !== 'cancelled';

            return (
              <div key={index}>
                <Tool toolPart={toolPart} className='mt-0' />
                {needsConfirmation && (
                  <div className='mt-2 ml-1 flex items-center gap-2'>
                    <button
                      type='button'
                      onClick={() => {
                        onConfirm(event.payload.tool_call_id);
                      }}
                      className='rounded-md bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700'
                    >
                      Confirm
                    </button>
                    <button
                      type='button'
                      onClick={() => {
                        onDeny(event.payload.tool_call_id);
                      }}
                      className='text-destructive hover:bg-destructive/10 rounded-md border px-3 py-1 text-sm font-medium'
                    >
                      Deny
                    </button>
                  </div>
                )}
              </div>
            );
          }

          // Skip tool_result events — they're merged into the tool_call rendering above
          case 'agent.tool_result': {
            return null;
          }

          case 'agent.message': {
            return (
              <MessageBubble
                key={index}
                content={event.payload.content}
                isComplete={event.payload.is_complete}
                role='assistant'
              />
            );
          }

          case 'agent.status': {
            // Hide internal "connected" handshake — noise for the user
            if (event.payload.status === 'connected') return null;
            return (
              <AgentStatusBadge
                key={index}
                status={event.payload.status}
                detail={event.payload.detail}
                progress={event.payload.progress}
                isActive={phase === 'running' && index === lastStatusIndex}
              />
            );
          }

          case 'agent.request_input': {
            return (
              <div key={index} className='rounded-lg border border-amber-200 bg-amber-50 p-3'>
                <p className='text-sm font-medium text-amber-800'>{event.payload.prompt}</p>
              </div>
            );
          }

          case 'session.completed': {
            return (
              <div key={index} className='rounded-lg border border-green-200 bg-green-50 p-3'>
                <p className='text-sm font-medium text-green-800'>Session completed</p>
              </div>
            );
          }

          case 'session.failed': {
            return (
              <div key={index} className='rounded-lg border border-red-200 bg-red-50 p-3'>
                <p className='text-sm font-medium text-red-800'>
                  Session failed: {event.payload.error}
                </p>
              </div>
            );
          }

          case 'agent.error': {
            return (
              <div key={index} className='rounded-lg border border-red-200 bg-red-50 p-3'>
                <p className='text-sm font-medium text-red-800'>
                  Error [{event.payload.code}]: {event.payload.message}
                </p>
              </div>
            );
          }

          default: {
            return null;
          }
        }
      })}

      {/* Show streaming content as it accumulates */}
      {streamingContent && (
        <MessageBubble content={streamingContent} isComplete={false} role='assistant' />
      )}
    </div>
  );
}
