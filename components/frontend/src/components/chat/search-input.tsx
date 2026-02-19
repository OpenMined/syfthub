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

import type { ChatSource } from '@/lib/types';

import ArrowUp from 'lucide-react/dist/esm/icons/arrow-up';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import X from 'lucide-react/dist/esm/icons/x';

import { EndpointPopover, OwnerPopover } from '@/components/query/mention-popover';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useMention } from '@/hooks/use-mention';
import { getMentionedSourceIds } from '@/lib/mention-utils';
import { cn } from '@/lib/utils';

import { ContextPill } from './context-pill';
import { ModelSelector } from './model-selector';

// =============================================================================
// Types
// =============================================================================

export interface ContextItem {
  id: string;
  label: string;
}

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
  /** Selected context items to display above the textarea */
  selectedContexts?: ContextItem[];
  /** Callback to remove a context item */
  onRemoveContext?: (id: string) => void;
  /** Currently selected model */
  selectedModel?: ChatSource | null;
  /** Callback when a model is selected */
  onModelSelect?: (model: ChatSource) => void;
  /** Available models for the model selector */
  models?: ChatSource[];
  /** Whether models are loading */
  isLoadingModels?: boolean;
  /** Enable @mention autocomplete for data sources */
  enableMentions?: boolean;
  /** Available data sources for mention autocomplete */
  sources?: ChatSource[];
  /** Callback when a mention is completed and source should be added to context */
  onMentionComplete?: (source: ChatSource) => void;
  /** Callback to sync mention sources — called with IDs of mentions currently in text */
  onMentionSync?: (mentionedIds: Set<string>) => void;
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
  placeholder = 'Start making queries, use @ for specific sources',
  onContextClick,
  selectedContexts = [],
  onRemoveContext,
  selectedModel = null,
  onModelSelect,
  models = [],
  isLoadingModels = false,
  enableMentions = false,
  sources = [],
  onMentionComplete,
  onMentionSync,
  className
}: Readonly<SearchInputProps>) {
  const [value, setValue] = useState('');
  const [cursorPosition, setCursorPosition] = useState(0);
  const textareaReference = useRef<HTMLTextAreaElement>(null);
  const popoverReference = useRef<HTMLDivElement>(null);

  const hasContent = value.trim().length > 0;

  // Initialize mention hook (always called, only active when enableMentions is true)
  const mention = useMention({
    sources: enableMentions ? sources : [],
    maxResults: 8
  });

  // Keep textarea at fixed height — content scrolls instead of growing
  useEffect(() => {
    const textarea = textareaReference.current;
    if (!textarea) return;
    textarea.style.height = '';
  }, []);

  // Update mention state when value or cursor changes
  useEffect(() => {
    if (enableMentions) {
      mention.updateMentionState(value, cursorPosition);
    }
  }, [enableMentions, value, cursorPosition, mention.updateMentionState]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;

    onSubmit(trimmed);
    setValue('');
    setCursorPosition(0);
    mention.reset();
  }, [value, disabled, onSubmit, mention]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Let mention hook handle navigation keys first
      if (enableMentions) {
        const result = mention.handleKeyDown(event, value, cursorPosition);
        if (result.handled) {
          if (result.newValue !== undefined) {
            setValue(result.newValue);
            const newCursorPos = result.newCursorPos ?? result.newValue.length;
            setCursorPosition(newCursorPos);
            setTimeout(() => {
              if (textareaReference.current) {
                textareaReference.current.setSelectionRange(newCursorPos, newCursorPos);
              }
            }, 0);
          }
          if (result.completedSource && onMentionComplete) {
            onMentionComplete(result.completedSource);
          }
          return;
        }
      }

      // Enter without Shift submits; Shift+Enter inserts newline
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [enableMentions, mention, value, cursorPosition, onMentionComplete, handleSubmit]
  );

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = event.target.value;
      setValue(newValue);
      setCursorPosition(event.target.selectionStart);

      // Sync mention sources — detect deleted mentions
      if (enableMentions && onMentionSync) {
        const mentionedIds = getMentionedSourceIds(newValue, sources);
        onMentionSync(mentionedIds);
      }
    },
    [enableMentions, onMentionSync, sources]
  );

  const handleSelect = useCallback((event: React.SyntheticEvent<HTMLTextAreaElement>) => {
    const target = event.target as HTMLTextAreaElement;
    setCursorPosition(target.selectionStart);
  }, []);

  const handleOwnerSelect = useCallback(
    (owner: string) => {
      const result = mention.selectOwner(owner, value, cursorPosition);
      setValue(result.newValue);
      setCursorPosition(result.newCursorPos);
      setTimeout(() => {
        if (textareaReference.current) {
          textareaReference.current.setSelectionRange(result.newCursorPos, result.newCursorPos);
          textareaReference.current.focus();
        }
      }, 0);
    },
    [mention, value, cursorPosition]
  );

  const handleEndpointSelect = useCallback(
    (endpoint: ChatSource) => {
      const result = mention.selectEndpoint(endpoint, value, cursorPosition);
      setValue(result.newValue);
      setCursorPosition(result.newCursorPos);
      if (onMentionComplete) {
        onMentionComplete(result.completedSource);
      }
      setTimeout(() => {
        if (textareaReference.current) {
          textareaReference.current.setSelectionRange(result.newCursorPos, result.newCursorPos);
          textareaReference.current.focus();
        }
      }, 0);
    },
    [mention, value, cursorPosition, onMentionComplete]
  );

  const handleContextClick = useCallback(() => {
    onContextClick?.();
  }, [onContextClick]);

  return (
    <div
      className={cn(
        'border-border bg-background focus-within:ring-ring/50 rounded-3xl border px-4 py-2 shadow-sm transition-shadow focus-within:ring-[3px]',
        className
      )}
    >
      {/* Context chips row — fixed height so the component size doesn't shift */}
      <div className='mb-2 flex h-4 items-center gap-1 overflow-x-auto'>
        {selectedContexts.map((ctx) => (
          <span
            key={ctx.id}
            className='border-border bg-muted text-muted-foreground inline-flex h-4 shrink-0 items-center gap-0.5 rounded-full border px-1.5 text-[10px] leading-none'
          >
            {ctx.label}
            {onRemoveContext && (
              <button
                type='button'
                onClick={() => {
                  onRemoveContext(ctx.id);
                }}
                className='text-muted-foreground hover:text-foreground -mr-0.5 flex items-center justify-center'
                aria-label={`Remove ${ctx.label}`}
              >
                <X className='h-2.5 w-2.5' aria-hidden='true' />
              </button>
            )}
          </span>
        ))}
      </div>

      {/* Visually hidden label for accessibility */}
      <label htmlFor='search-input-textarea' className='sr-only'>
        Chat message
      </label>

      {/* Textarea with mention popovers */}
      <div className='relative'>
        <Textarea
          id='search-input-textarea'
          ref={textareaReference}
          value={value}
          onChange={handleChange}
          onSelect={handleSelect}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className='h-[48px] resize-none overflow-y-auto border-0 p-0 text-base shadow-none focus-visible:ring-0'
          aria-expanded={
            enableMentions && (mention.showOwnerPopover || mention.showEndpointPopover)
          }
          aria-haspopup={enableMentions ? 'listbox' : undefined}
        />

        {/* Mention popovers */}
        {enableMentions && (
          <>
            <OwnerPopover
              ref={popoverReference}
              isOpen={mention.showOwnerPopover}
              owners={mention.filteredOwners}
              highlightedIndex={mention.highlightedIndex}
              onSelect={handleOwnerSelect}
              className='bottom-full left-0 mb-2'
            />
            <EndpointPopover
              ref={popoverReference}
              isOpen={mention.showEndpointPopover}
              endpoints={mention.filteredEndpoints}
              highlightedIndex={mention.highlightedIndex}
              onSelect={handleEndpointSelect}
              className='bottom-full left-0 mb-2'
            />
          </>
        )}
      </div>

      {/* Bottom Toolbar */}
      <div className='mt-3 flex items-center justify-between'>
        {/* Left: Context pill */}
        <ContextPill onClick={handleContextClick} disabled={disabled} />

        {/* Right: Model selector + Submit button */}
        <div className='flex items-center gap-1'>
          {onModelSelect && (
            <ModelSelector
              selectedModel={selectedModel}
              onModelSelect={onModelSelect}
              models={models}
              isLoading={isLoadingModels}
            />
          )}
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
    </div>
  );
}
