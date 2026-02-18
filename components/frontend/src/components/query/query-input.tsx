/**
 * QueryInput Component
 *
 * Shared input component for submitting queries.
 * Used by both Hero (centered layout) and ChatView (bottom input bar).
 * Supports @mention autocomplete for data sources when enabled.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Send from 'lucide-react/dist/esm/icons/send';

import { useMention } from '@/hooks/use-mention';

import { MentionedSources } from './mention-hover-card';
import { EndpointPopover, OwnerPopover } from './mention-popover';

// =============================================================================
// Types
// =============================================================================

export interface QueryInputProps {
  /** Callback when user submits a query */
  onSubmit: (query: string) => void;
  /** Whether the input is disabled (e.g., during processing) */
  disabled?: boolean;
  /** Whether a request is currently processing (shows loading indicator) */
  isProcessing?: boolean;
  /** Placeholder text for the input */
  placeholder?: string;
  /** Visual variant of the input */
  variant?: 'hero' | 'chat';
  /** Whether to auto-focus the input on mount (desktop only) */
  autoFocus?: boolean;
  /** Initial value for the input */
  initialValue?: string;
  /** ID for the input element (for accessibility) */
  id?: string;
  /** Accessible label for the input */
  ariaLabel?: string;
  /** Enable @mention autocomplete for data sources */
  enableMentions?: boolean;
  /** Available data sources for mention autocomplete (required when enableMentions is true) */
  sources?: ChatSource[];
  /** Callback when a mention is completed and source should be added to context */
  onMentionComplete?: (source: ChatSource) => void;
  /** Currently selected sources via mentions (for displaying badges) */
  mentionedSources?: ChatSource[];
  /** Callback to remove a mentioned source */
  onMentionRemove?: (source: ChatSource) => void;
}

// =============================================================================
// Component
// =============================================================================

/**
 * Reusable query input component.
 *
 * @example
 * ```tsx
 * // Hero variant (centered, larger)
 * <QueryInput
 *   variant="hero"
 *   onSubmit={handleSearch}
 *   placeholder="What is attribution-based control?"
 *   autoFocus
 * />
 *
 * // Chat variant with mentions enabled
 * <QueryInput
 *   variant="chat"
 *   onSubmit={workflow.submitQuery}
 *   disabled={workflow.phase !== 'idle'}
 *   isProcessing={workflow.phase === 'streaming'}
 *   placeholder="Ask a question — use @ for specific sources"
 *   enableMentions
 *   sources={dataSources}
 *   onMentionComplete={handleMentionComplete}
 * />
 * ```
 */
export function QueryInput({
  onSubmit,
  disabled = false,
  isProcessing = false,
  placeholder = 'What is attribution-based control?',
  variant = 'hero',
  autoFocus = false,
  initialValue = '',
  id,
  ariaLabel,
  enableMentions = false,
  sources = [],
  onMentionComplete,
  mentionedSources = [],
  onMentionRemove
}: Readonly<QueryInputProps>) {
  const [value, setValue] = useState(initialValue);
  const [cursorPosition, setCursorPosition] = useState(0);
  const inputReference = useRef<HTMLInputElement>(null);
  const popoverReference = useRef<HTMLDivElement>(null);

  // Initialize mention hook (always called, but only active when enableMentions is true)
  const mention = useMention({
    sources: enableMentions ? sources : [],
    maxResults: 8
  });

  // Auto-focus on desktop only (avoid virtual keyboard on mobile)
  useEffect(() => {
    if (autoFocus) {
      const isDesktop = globalThis.matchMedia('(min-width: 1024px)').matches;
      if (isDesktop && inputReference.current) {
        inputReference.current.focus();
      }
    }
  }, [autoFocus]);

  // Update mention state when value or cursor changes
  useEffect(() => {
    if (enableMentions) {
      mention.updateMentionState(value, cursorPosition);
    }
  }, [enableMentions, value, cursorPosition, mention.updateMentionState]);

  const handleSubmit = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault();
      const trimmedValue = value.trim();
      if (trimmedValue && !disabled) {
        onSubmit(trimmedValue);
        // Clear input after submission for chat variant
        if (variant === 'chat') {
          setValue('');
          setCursorPosition(0);
          mention.reset();
        }
      }
    },
    [value, disabled, onSubmit, variant, mention]
  );

  const handleChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = event.target.value;
    setValue(newValue);
    setCursorPosition(event.target.selectionStart ?? newValue.length);
  }, []);

  const handleSelect = useCallback((event: React.SyntheticEvent<HTMLInputElement>) => {
    const target = event.target as HTMLInputElement;
    setCursorPosition(target.selectionStart ?? 0);
  }, []);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (!enableMentions) return;

      // Let mention hook handle navigation keys
      const result = mention.handleKeyDown(event, value, cursorPosition);

      if (result.handled) {
        // Update value and cursor if mention provided new values
        if (result.newValue !== undefined) {
          setValue(result.newValue);
          // Set cursor position after React updates the input
          const newCursorPos = result.newCursorPos ?? result.newValue.length;
          setCursorPosition(newCursorPos);
          // Also manually set selection since React state update is async
          setTimeout(() => {
            if (inputReference.current) {
              inputReference.current.setSelectionRange(newCursorPos, newCursorPos);
            }
          }, 0);
        }

        // If a mention was completed, notify parent
        if (result.completedSource && onMentionComplete) {
          onMentionComplete(result.completedSource);
        }
      }
    },
    [enableMentions, mention, value, cursorPosition, onMentionComplete]
  );

  const handleOwnerSelect = useCallback(
    (owner: string) => {
      const result = mention.selectOwner(owner, value, cursorPosition);
      setValue(result.newValue);
      setCursorPosition(result.newCursorPos);
      // Set cursor position
      setTimeout(() => {
        if (inputReference.current) {
          inputReference.current.setSelectionRange(result.newCursorPos, result.newCursorPos);
          inputReference.current.focus();
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
      // Notify parent of completed mention
      if (onMentionComplete) {
        onMentionComplete(result.completedSource);
      }
      // Set cursor position
      setTimeout(() => {
        if (inputReference.current) {
          inputReference.current.setSelectionRange(result.newCursorPos, result.newCursorPos);
          inputReference.current.focus();
        }
      }, 0);
    },
    [mention, value, cursorPosition, onMentionComplete]
  );

  // Variant-specific styles
  const isHero = variant === 'hero';

  const inputClassName = isHero
    ? 'font-inter border-input text-foreground placeholder:text-muted-foreground focus:ring-ring bg-background w-full rounded-xl border px-6 py-4 shadow-sm transition-colors transition-shadow focus:border-transparent focus:ring-2 focus:outline-none [&::-webkit-search-cancel-button]:hidden [&::-webkit-search-decoration]:hidden'
    : 'font-inter border-border bg-background placeholder:text-muted-foreground focus:border-foreground focus:ring-foreground/10 w-full rounded-xl border py-3.5 pr-12 pl-4 shadow-sm transition-colors transition-shadow focus:ring-2 focus:outline-none';

  const buttonClassName = isHero
    ? 'group-focus-within:text-ring hover:bg-muted absolute top-1/2 right-3 -translate-y-1/2 rounded-lg p-2 transition-colors'
    : 'bg-primary hover:bg-primary/90 absolute top-1/2 right-2 -translate-y-1/2 rounded-lg p-2 text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  const heroIconColorClass = value ? 'text-ring' : 'text-muted-foreground';
  const iconClassName = isHero ? `h-5 w-5 transition-colors ${heroIconColorClass}` : 'h-4 w-4';

  const inputId = id ?? `query-input-${variant}`;
  const label =
    ariaLabel ??
    (isHero ? 'Search for data sources, models, or topics' : 'Ask a follow-up question');

  const renderButtonIcon = () => {
    if (isProcessing) {
      return <Loader2 className={`${iconClassName} animate-spin`} aria-hidden='true' />;
    }
    if (isHero) {
      return <Send className={iconClassName} aria-hidden='true' />;
    }
    return (
      <svg
        width='16'
        height='16'
        viewBox='0 0 24 24'
        fill='none'
        stroke='currentColor'
        strokeWidth='2'
        strokeLinecap='round'
        strokeLinejoin='round'
        aria-hidden='true'
      >
        <path d='M5 12h14M12 5l7 7-7 7' />
      </svg>
    );
  };

  return (
    <form onSubmit={handleSubmit} role={isHero ? 'search' : undefined}>
      {/* Mentioned sources badges (above input) */}
      {enableMentions && mentionedSources.length > 0 && (
        <MentionedSources sources={mentionedSources} onRemove={onMentionRemove} className='mb-2' />
      )}

      <div className={isHero ? 'group relative' : 'relative'}>
        <label htmlFor={inputId} className='sr-only'>
          {label}
        </label>
        <input
          id={inputId}
          ref={inputReference}
          type={isHero ? 'search' : 'text'}
          name='query'
          value={value}
          onChange={handleChange}
          onSelect={handleSelect}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={inputClassName}
          autoComplete='off'
          disabled={disabled}
          aria-expanded={
            enableMentions && (mention.showOwnerPopover || mention.showEndpointPopover)
          }
          aria-haspopup={enableMentions ? 'listbox' : undefined}
        />
        <button
          type='submit'
          disabled={!value.trim() || disabled}
          aria-label={isProcessing ? 'Processing…' : 'Send'}
          className={buttonClassName}
        >
          {renderButtonIcon()}
        </button>

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
    </form>
  );
}

// =============================================================================
// Search Suggestions (for Hero variant)
// =============================================================================

export interface SearchSuggestionsProps {
  suggestions: readonly string[];
  onSelect: (suggestion: string) => void;
}

/**
 * Search suggestion pills shown below the Hero input.
 */
export function SearchSuggestions({ suggestions, onSelect }: Readonly<SearchSuggestionsProps>) {
  return (
    <div className='flex flex-wrap items-center gap-2'>
      {suggestions.map((suggestion, index) => (
        <button
          key={index}
          type='button'
          onClick={() => {
            onSelect(suggestion);
          }}
          className='font-inter border-border/40 text-muted-foreground hover:border-border hover:text-foreground focus:ring-ring rounded-full border px-3 py-2 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none'
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
