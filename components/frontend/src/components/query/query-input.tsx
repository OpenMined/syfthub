/**
 * QueryInput Component
 *
 * Shared input component for submitting queries.
 * Used by both Hero (centered layout) and ChatView (bottom input bar).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Send from 'lucide-react/dist/esm/icons/send';

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
 * // Chat variant (bottom bar, compact)
 * <QueryInput
 *   variant="chat"
 *   onSubmit={workflow.submitQuery}
 *   disabled={workflow.phase !== 'idle'}
 *   isProcessing={workflow.phase === 'streaming'}
 *   placeholder="Ask a follow-up question…"
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
  ariaLabel
}: Readonly<QueryInputProps>) {
  const [value, setValue] = useState(initialValue);
  const inputReference = useRef<HTMLInputElement>(null);

  // Auto-focus on desktop only (avoid virtual keyboard on mobile)
  useEffect(() => {
    if (autoFocus) {
      const isDesktop = globalThis.matchMedia('(min-width: 1024px)').matches;
      if (isDesktop && inputReference.current) {
        inputReference.current.focus();
      }
    }
  }, [autoFocus]);

  const handleSubmit = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault();
      const trimmedValue = value.trim();
      if (trimmedValue && !disabled) {
        onSubmit(trimmedValue);
        // Clear input after submission for chat variant
        if (variant === 'chat') {
          setValue('');
        }
      }
    },
    [value, disabled, onSubmit, variant]
  );

  const handleChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setValue(event.target.value);
  }, []);

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
          placeholder={placeholder}
          className={inputClassName}
          autoComplete='off'
          disabled={disabled}
        />
        <button
          type='submit'
          disabled={!value.trim() || disabled}
          aria-label={isProcessing ? 'Processing…' : 'Send'}
          className={buttonClassName}
        >
          {renderButtonIcon()}
        </button>
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
    <div className='flex flex-wrap items-center justify-center gap-2'>
      {suggestions.map((suggestion, index) => (
        <button
          key={index}
          type='button'
          onClick={() => {
            onSelect(suggestion);
          }}
          className='font-inter border-border/40 text-muted-foreground hover:border-border hover:text-foreground focus:ring-ring rounded-full border px-3 py-1.5 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none'
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
