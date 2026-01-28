import { memo, useCallback, useMemo, useState } from 'react';

import type { SearchableChatSource } from '@/lib/search-service';
import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Database from 'lucide-react/dist/esm/icons/database';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';
import Send from 'lucide-react/dist/esm/icons/send';
import X from 'lucide-react/dist/esm/icons/x';

import { filterSourcesForAutocomplete } from '@/lib/validation';

// ============================================================================
// Sub-components
// ============================================================================

interface EndpointCardProps {
  source: ChatSource | SearchableChatSource;
  isSelected: boolean;
  onToggle: () => void;
  showRelevance?: boolean;
}

/** Renders a selectable endpoint card */
const EndpointCard = memo(function EndpointCard({
  source,
  isSelected,
  onToggle,
  showRelevance = false
}: Readonly<EndpointCardProps>) {
  const relevanceScore = 'relevance_score' in source ? source.relevance_score : undefined;

  return (
    <button
      type='button'
      onClick={onToggle}
      aria-pressed={isSelected}
      className={`group relative flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-all focus-visible:ring-2 focus-visible:ring-[#272532]/50 focus-visible:outline-none ${
        isSelected
          ? 'border-green-500 bg-green-50 dark:border-green-600 dark:bg-green-950/30'
          : 'border-border bg-card hover:border-green-300 hover:bg-green-50/50 dark:hover:border-green-700 dark:hover:bg-green-950/20'
      }`}
    >
      {/* Icon */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
          isSelected
            ? 'bg-green-500 text-white'
            : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
        }`}
      >
        <Database className='h-4 w-4' />
      </div>

      {/* Content */}
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-2'>
          <span
            className='font-inter text-foreground truncate text-sm font-medium'
            title={source.name}
          >
            {source.name}
          </span>
          {showRelevance && relevanceScore !== undefined && (
            <span className='font-inter shrink-0 rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900 dark:text-green-300'>
              {Math.round(relevanceScore * 100)}% match
            </span>
          )}
        </div>
        {source.full_path && (
          <span className='font-inter text-muted-foreground block truncate text-xs'>
            {source.full_path}
          </span>
        )}
        {source.description && (
          <p className='font-inter text-muted-foreground mt-1 line-clamp-2 text-xs'>
            {source.description}
          </p>
        )}
      </div>

      {/* Checkbox indicator */}
      <div
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
          isSelected
            ? 'border-green-500 bg-green-500 dark:border-green-600 dark:bg-green-600'
            : 'border-input bg-background'
        }`}
        aria-hidden='true'
      >
        {isSelected && <Check className='h-3 w-3 text-white' />}
      </div>
    </button>
  );
});

interface SearchSuggestionProps {
  source: ChatSource;
  isSelected: boolean;
  onSelect: () => void;
}

/** Renders a search suggestion item */
const SearchSuggestion = memo(function SearchSuggestion({
  source,
  isSelected,
  onSelect
}: Readonly<SearchSuggestionProps>) {
  return (
    <button
      type='button'
      onClick={onSelect}
      className='hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left first:rounded-t-lg last:rounded-b-lg'
    >
      <div className='flex h-6 w-6 shrink-0 items-center justify-center rounded bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'>
        <Database className='h-3 w-3' />
      </div>
      <div className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block truncate text-xs font-medium'>
          {source.name}
        </span>
        <span className='font-inter text-muted-foreground truncate text-[10px]'>
          {source.full_path}
        </span>
      </div>
      {isSelected && <Check className='h-3 w-3 shrink-0 text-green-600' />}
    </button>
  );
});

// ============================================================================
// Main Component
// ============================================================================

export interface EndpointConfirmationProps {
  /** The original query from the user */
  query: string;
  /** Suggested endpoints from semantic search */
  suggestedEndpoints: SearchableChatSource[];
  /** Whether endpoint search is in progress */
  isSearching: boolean;
  /** Currently selected source IDs */
  selectedSources: Set<string>;
  /** All available sources for additional search */
  availableSources: ChatSource[];
  /** Toggle a source selection */
  onToggleSource: (id: string) => void;
  /** Confirm and send the query */
  onConfirm: () => void;
  /** Cancel and go back */
  onCancel: () => void;
}

export const EndpointConfirmation = memo(function EndpointConfirmation({
  query,
  suggestedEndpoints,
  isSearching,
  selectedSources,
  availableSources,
  onToggleSource,
  onConfirm,
  onCancel
}: Readonly<EndpointConfirmationProps>) {
  // Local state for search input
  const [searchInput, setSearchInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Filter available sources based on search input (client-side)
  const searchSuggestions = useMemo(() => {
    if (!searchInput.trim()) return [];
    // Exclude already suggested endpoints from search results
    const suggestedIds = new Set(suggestedEndpoints.map((s) => s.id));
    const filtered = availableSources.filter((s) => !suggestedIds.has(s.id));
    return filterSourcesForAutocomplete(filtered, searchInput, 8);
  }, [availableSources, suggestedEndpoints, searchInput]);

  // Count selected sources
  const selectedCount = selectedSources.size;

  // Handle input change
  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchInput(event.target.value);
    setShowSuggestions(event.target.value.trim().length > 0);
  }, []);

  // Handle input blur
  const handleSearchBlur = useCallback(() => {
    // Delay hiding suggestions to allow click events
    setTimeout(() => {
      setShowSuggestions(false);
    }, 200);
  }, []);

  // Handle selecting a suggestion
  const handleSelectSuggestion = useCallback(
    (source: ChatSource) => {
      onToggleSource(source.id);
      setSearchInput('');
      setShowSuggestions(false);
    },
    [onToggleSource]
  );

  // Handle keyboard events on search input
  const handleSearchKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setShowSuggestions(false);
      setSearchInput('');
    }
  }, []);

  return (
    <div className='my-4 w-full max-w-3xl'>
      <div className='border-border bg-card rounded-xl border shadow-sm'>
        {/* Header */}
        <div className='border-border flex items-center justify-between border-b p-4'>
          <div className='flex items-center gap-3'>
            <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'>
              <Database className='h-5 w-5' />
            </div>
            <div>
              <h3 className='font-inter text-foreground text-sm font-medium'>
                Select Data Sources
              </h3>
              <p className='font-inter text-muted-foreground text-xs'>
                Choose which data sources to query for your question
              </p>
            </div>
          </div>
          <button
            type='button'
            onClick={onCancel}
            className='text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors'
            aria-label='Cancel'
          >
            <X className='h-5 w-5' />
          </button>
        </div>

        {/* Query display */}
        <div className='border-border border-b bg-slate-50 px-4 py-3 dark:bg-slate-900/50'>
          <p className='font-inter text-muted-foreground mb-1 text-xs font-medium'>
            Your question:
          </p>
          <p className='font-inter text-foreground text-sm leading-relaxed'>{query}</p>
        </div>

        {/* Content */}
        <div className='p-4'>
          {/* Loading state */}
          {isSearching && (
            <div className='flex flex-col items-center justify-center py-8'>
              <Loader2 className='text-muted-foreground mb-3 h-8 w-8 animate-spin' />
              <p className='font-inter text-muted-foreground text-sm'>
                Finding relevant data sources...
              </p>
            </div>
          )}

          {/* Suggested endpoints */}
          {!isSearching && (
            <>
              {suggestedEndpoints.length > 0 ? (
                <div className='mb-4'>
                  <p className='font-inter text-muted-foreground mb-3 text-xs font-medium'>
                    Suggested data sources ({suggestedEndpoints.length} found):
                  </p>
                  <div className='space-y-2'>
                    {suggestedEndpoints.map((source) => (
                      <EndpointCard
                        key={source.id}
                        source={source}
                        isSelected={selectedSources.has(source.id)}
                        onToggle={() => {
                          onToggleSource(source.id);
                        }}
                        showRelevance
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <div className='mb-4 rounded-lg border border-dashed border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950/30'>
                  <p className='font-inter text-sm text-amber-800 dark:text-amber-200'>
                    No highly relevant data sources found for your query.
                  </p>
                  <p className='font-inter mt-1 text-xs text-amber-600 dark:text-amber-400'>
                    You can search for specific endpoints below, or proceed without data sources to
                    use the model directly.
                  </p>
                </div>
              )}

              {/* Search for more endpoints */}
              <div className='relative'>
                <p className='font-inter text-muted-foreground mb-2 text-xs font-medium'>
                  Search for additional data sources:
                </p>
                <div className='relative'>
                  <Search className='text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2' />
                  <input
                    type='text'
                    value={searchInput}
                    onChange={handleSearchChange}
                    onFocus={() => {
                      setShowSuggestions(searchInput.trim().length > 0);
                    }}
                    onBlur={handleSearchBlur}
                    onKeyDown={handleSearchKeyDown}
                    placeholder='Type to search endpoints...'
                    className='font-inter border-border bg-background placeholder:text-muted-foreground w-full rounded-lg border py-2 pr-4 pl-10 text-sm transition-colors focus:border-green-500 focus:ring-2 focus:ring-green-500/20 focus:outline-none'
                    autoComplete='off'
                  />
                </div>

                {/* Search suggestions dropdown */}
                {showSuggestions && searchSuggestions.length > 0 && (
                  <div className='border-border bg-card absolute top-full left-0 z-10 mt-1 w-full rounded-lg border shadow-lg'>
                    {searchSuggestions.map((source) => (
                      <SearchSuggestion
                        key={source.id}
                        source={source}
                        isSelected={selectedSources.has(source.id)}
                        onSelect={() => {
                          handleSelectSuggestion(source);
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* No results message */}
                {showSuggestions && searchInput.trim() && searchSuggestions.length === 0 && (
                  <div className='border-border bg-card absolute top-full left-0 z-10 mt-1 w-full rounded-lg border p-3 shadow-lg'>
                    <p className='font-inter text-muted-foreground text-center text-xs'>
                      No matching endpoints found
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className='border-border flex items-center justify-between border-t bg-slate-50 px-4 py-3 dark:bg-slate-900/50'>
          <p className='font-inter text-muted-foreground text-xs'>
            {selectedCount === 0
              ? 'No data sources selected (model-only mode)'
              : `${String(selectedCount)} data source${selectedCount === 1 ? '' : 's'} selected`}
          </p>
          <div className='flex items-center gap-2'>
            <button
              type='button'
              onClick={onCancel}
              className='font-inter text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg px-4 py-2 text-sm transition-colors'
            >
              Cancel
            </button>
            <button
              type='button'
              onClick={onConfirm}
              disabled={isSearching}
              className='font-inter bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50'
            >
              <Send className='h-4 w-4' />
              {selectedCount === 0
                ? 'Send (Model Only)'
                : `Send with ${String(selectedCount)} Source${selectedCount === 1 ? '' : 's'}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
