/**
 * SearchInput Component
 *
 * Composed chat input with an auto-growing textarea, inline action buttons
 * (context pill, source selector), and a submit button. All interactive
 * elements share a unified focus container with a focus-within ring.
 *
 * @example
 * ```tsx
 * <SearchInput
 *   onSubmit={(query) => console.log(query)}
 *   placeholder="Ask anything..."
 * />
 * ```
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import ArrowUp from 'lucide-react/dist/esm/icons/arrow-up';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

import { ContextPill } from './context-pill';
import { SourceSelector } from './source-selector';

// =============================================================================
// Types
// =============================================================================

export interface SearchInputProps {
  /** Callback when user submits a query */
  onSubmit: (query: string) => void;
  /** Whether the input is disabled (e.g., during processing) */
  disabled?: boolean;
  /** Whether a request is currently processing (shows loading indicator) */
  isProcessing?: boolean;
  /** Placeholder text for the textarea */
  placeholder?: string;
  /** Callback when the "@ Add context" pill is clicked */
  onContextClick?: () => void;
  /** Additional CSS classes for the outer wrapper */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

export function SearchInput({
  onSubmit,
  disabled = false,
  isProcessing = false,
  placeholder = 'Ask anything...',
  onContextClick,
  className
}: Readonly<SearchInputProps>) {
  const [value, setValue] = useState('');
  const [mode, setMode] = useState('auto');
  const [sourceFilter, setSourceFilter] = useState('all');
  const textareaReference = useRef<HTMLTextAreaElement>(null);

  const hasContent = value.trim().length > 0;

  // Auto-grow textarea based on content
  useEffect(() => {
    const textarea = textareaReference.current;
    if (!textarea) return;

    // Reset height to auto to get accurate scrollHeight
    textarea.style.height = 'auto';
    // Set to scrollHeight, capped at max-height via CSS
    textarea.style.height = `${String(textarea.scrollHeight)}px`;
  }, [value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;

    onSubmit(trimmed);
    setValue('');

    // Reset textarea height after clearing
    if (textareaReference.current) {
      textareaReference.current.style.height = 'auto';
    }
  }, [value, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter without Shift submits; Shift+Enter inserts newline
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleChange = useCallback((event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(event.target.value);
  }, []);

  const handleContextClick = useCallback(() => {
    onContextClick?.();
  }, [onContextClick]);

  return (
    <div
      className={cn(
        'border-border bg-background focus-within:ring-ring/50 rounded-3xl border p-4 shadow-sm transition-shadow focus-within:ring-[3px]',
        className
      )}
    >
      {/* Visually hidden label for accessibility */}
      <label htmlFor='search-input-textarea' className='sr-only'>
        Chat message
      </label>

      {/* Auto-growing Textarea */}
      <Textarea
        id='search-input-textarea'
        ref={textareaReference}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className='max-h-[200px] min-h-0 resize-none overflow-y-auto border-0 p-0 text-base shadow-none focus-visible:ring-0'
      />

      {/* Bottom Toolbar */}
      <div className='mt-3 flex items-center justify-between'>
        {/* Left: Action buttons */}
        <div className='flex items-center gap-1'>
          <ContextPill onClick={handleContextClick} disabled={disabled} />
          <SourceSelector
            mode={mode}
            onModeChange={setMode}
            sourceFilter={sourceFilter}
            onSourceFilterChange={setSourceFilter}
            disabled={disabled}
          />
        </div>

        {/* Right: Submit button */}
        <Button
          type='button'
          size='icon'
          onClick={handleSubmit}
          disabled={!hasContent || disabled}
          aria-label={isProcessing ? 'Processing...' : 'Send message'}
          className={cn(
            'h-10 w-10 shrink-0 rounded-full transition-colors',
            hasContent
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground'
          )}
        >
          {isProcessing ? (
            <Loader2 className='h-5 w-5 animate-spin' aria-hidden='true' />
          ) : (
            <ArrowUp className='h-5 w-5' aria-hidden='true' />
          )}
        </Button>
      </div>
    </div>
  );
}
