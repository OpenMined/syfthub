/**
 * Main agent UI container.
 * Renders the agent session interface with event list and input.
 */
import { useCallback, useState } from 'react';

import { useAgentWorkflow } from '@/hooks/use-agent-workflow';

import { AgentEventList } from './agent-event-list';
import { AgentInput } from './agent-input';

interface AgentViewProps {
  readonly owner: string;
  readonly slug: string;
}

export function AgentView({ owner, slug }: AgentViewProps) {
  const { state, startSession, sendMessage, confirm, deny, cancel, reset } = useAgentWorkflow();
  const [, setInitialPrompt] = useState('');

  const endpoint = `${owner}/${slug}`;

  const handleSend = useCallback(
    (content: string) => {
      if (state.phase === 'idle') {
        setInitialPrompt(content);
        startSession(content, endpoint);
      } else {
        sendMessage(content);
      }
    },
    [state.phase, startSession, sendMessage, endpoint]
  );

  const handleConfirm = useCallback(
    (toolCallId: string) => {
      confirm(toolCallId);
    },
    [confirm]
  );

  const handleDeny = useCallback(
    (toolCallId: string) => {
      deny(toolCallId);
    },
    [deny]
  );

  return (
    <div className='flex h-full flex-col'>
      {/* Header */}
      <div className='flex items-center justify-between border-b px-4 py-3'>
        <div className='flex items-center gap-3'>
          <h2 className='text-lg font-semibold'>{slug}</h2>
          <span className='text-muted-foreground text-sm'>by {owner}</span>
          <span className='inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700'>
            agent
          </span>
        </div>
        <div className='flex items-center gap-2'>
          {state.phase !== 'idle' && (
            <span className='text-muted-foreground text-sm capitalize'>{state.phase}</span>
          )}
          {(state.phase === 'running' || state.phase === 'awaiting_input') && (
            <button
              onClick={cancel}
              className='text-destructive hover:bg-destructive/10 rounded-md border px-3 py-1 text-sm'
            >
              Cancel
            </button>
          )}
          {(state.phase === 'completed' ||
            state.phase === 'failed' ||
            state.phase === 'cancelled' ||
            state.phase === 'error') && (
            <button onClick={reset} className='hover:bg-accent rounded-md border px-3 py-1 text-sm'>
              New Session
            </button>
          )}
        </div>
      </div>

      {/* Event list */}
      <div className='flex-1 overflow-y-auto'>
        <AgentEventList
          events={state.events}
          streamingContent={state.streamingContent}
          onConfirm={handleConfirm}
          onDeny={handleDeny}
          phase={state.phase}
        />
      </div>

      {/* Input */}
      <AgentInput
        onSend={handleSend}
        phase={state.phase}
        disabled={
          state.phase === 'connecting' ||
          state.phase === 'completed' ||
          state.phase === 'failed' ||
          state.phase === 'cancelled' ||
          state.phase === 'error'
        }
      />
    </div>
  );
}
