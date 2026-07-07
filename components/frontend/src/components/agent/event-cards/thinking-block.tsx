/**
 * Collapsible reasoning/thinking display.
 */
import { useState } from 'react';

interface ThinkingBlockProps {
  readonly content: string;
  readonly isStreaming: boolean;
}

export function ThinkingBlock({ content, isStreaming }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className='bg-muted/30 rounded-lg border'>
      <button
        onClick={() => {
          setIsOpen(!isOpen);
        }}
        className='text-muted-foreground hover:text-foreground flex w-full items-center gap-2 px-3 py-2 text-sm'
      >
        {isStreaming ? (
          <div className='h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent' />
        ) : (
          <svg
            className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-90' : ''}`}
            fill='none'
            viewBox='0 0 24 24'
            stroke='currentColor'
          >
            <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M9 5l7 7-7 7' />
          </svg>
        )}
        <span className='font-medium'>{isStreaming ? 'Thinking...' : 'Thought'}</span>
      </button>
      {isOpen && (
        <div className='border-t px-3 py-2'>
          <p className='text-muted-foreground text-sm whitespace-pre-wrap'>{content}</p>
        </div>
      )}
    </div>
  );
}
