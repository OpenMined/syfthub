/**
 * Adaptive input field for agent sessions.
 * Adapts placeholder and enabled state based on workflow phase.
 */
import { useCallback, useState } from 'react';

import type { AgentSessionState } from '@syfthub/sdk';

interface AgentInputProps {
  readonly onSend: (content: string) => void;
  readonly phase: AgentSessionState;
  readonly disabled?: boolean;
}

export function AgentInput({ onSend, phase, disabled = false }: AgentInputProps) {
  const [input, setInput] = useState('');

  const getPlaceholder = (): string => {
    switch (phase) {
      case 'idle': {
        return 'Send a message to start the agent...';
      }
      case 'connecting': {
        return 'Connecting...';
      }
      case 'running': {
        return 'Send a follow-up message...';
      }
      case 'awaiting_input': {
        return 'The agent is waiting for your input...';
      }
      case 'completed': {
        return 'Session completed';
      }
      case 'failed': {
        return 'Session failed';
      }
      case 'cancelled': {
        return 'Session cancelled';
      }
      case 'error': {
        return 'An error occurred';
      }
      default: {
        return 'Type a message...';
      }
    }
  };

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || disabled) return;
      onSend(trimmed);
      setInput('');
    },
    [input, disabled, onSend]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
      }
    },
    [handleSubmit]
  );

  return (
    <form onSubmit={handleSubmit} className='border-t p-4'>
      <div className='flex items-end gap-2'>
        <textarea
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
          disabled={disabled}
          rows={1}
          className='bg-background placeholder:text-muted-foreground focus:ring-ring flex-1 resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50'
        />
        <button
          type='submit'
          disabled={disabled || !input.trim()}
          className='bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50'
        >
          Send
        </button>
      </div>
    </form>
  );
}
