import { useCallback, useMemo, useRef, useState } from 'react';

import { AtSign, Check, Search } from 'lucide-react';

import type { EndpointInfo } from '@/stores/appStore';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

interface SourceSelectorProps {
  /** Available (non-model) endpoints to pick from */
  endpoints: EndpointInfo[];
  /** Currently selected data sources */
  selectedSources: EndpointInfo[];
  /** Toggle a source in/out of the selection */
  onToggle: (source: EndpointInfo) => void;
  /** Disable the trigger button (e.g. no aggregator configured) */
  disabled?: boolean;
}

// =============================================================================
// Component
// =============================================================================

/**
 * Pill-shaped popover trigger that opens a searchable list of data-source
 * endpoints. Toggles individual sources via `onToggle`. Shows the selected
 * count in the label when at least one source is active.
 */
export function SourceSelector({
  endpoints,
  selectedSources,
  onToggle,
  disabled = false,
}: Readonly<SourceSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  const selectedIds = useMemo(
    () => new Set(selectedSources.map((s) => s.slug)),
    [selectedSources],
  );

  const filteredEndpoints = useMemo(() => {
    if (!searchQuery.trim()) return endpoints;
    const q = searchQuery.toLowerCase();
    return endpoints.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.slug.toLowerCase().includes(q) ||
        e.description.toLowerCase().includes(q),
    );
  }, [endpoints, searchQuery]);

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open);
    if (open) {
      setTimeout(() => {
        searchRef.current?.focus();
      }, 0);
    } else {
      setSearchQuery('');
    }
  }, []);

  const selectedCount = selectedSources.length;

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          type='button'
          disabled={disabled}
          className={cn(
            'border-border text-muted-foreground hover:text-foreground hover:border-foreground/20 inline-flex items-center gap-1 rounded-full border px-2.5 py-1.5 text-xs font-normal transition-colors',
            disabled && 'pointer-events-none opacity-50',
            isOpen && 'border-foreground/20 text-foreground bg-accent',
            selectedCount > 0 && 'border-secondary/40 text-foreground',
          )}
          aria-expanded={isOpen}
          aria-haspopup='listbox'
        >
          <AtSign className='h-3.5 w-3.5' aria-hidden='true' />
          {selectedCount > 0 ? `Context (${selectedCount})` : 'Add context'}
        </button>
      </PopoverTrigger>

      <PopoverContent side='top' align='start' className='w-[300px] overflow-hidden rounded-xl p-0'>
        {/* Header */}
        <div className='border-border border-b px-3 pt-3 pb-2'>
          <h3 className='text-foreground mb-2 text-sm font-semibold'>Add Context</h3>
          <div className='relative'>
            <label htmlFor='source-search' className='sr-only'>
              Search data sources
            </label>
            <Search
              className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2'
              aria-hidden='true'
            />
            <input
              id='source-search'
              ref={searchRef}
              type='search'
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder='Search sources…'
              className='border-border bg-card placeholder:text-muted-foreground focus:border-foreground focus:ring-foreground/10 w-full rounded-lg border py-2 pr-3 pl-9 text-sm transition-colors focus:ring-2 focus:outline-none'
              autoComplete='off'
            />
          </div>
        </div>

        {/* Source list */}
        <div className='max-h-[280px] overflow-y-auto p-2'>
          {filteredEndpoints.length === 0 ? (
            <p className='text-muted-foreground py-6 text-center text-sm'>
              {searchQuery ? 'No sources found' : 'No data sources available'}
            </p>
          ) : (
            <div className='space-y-1'>
              {filteredEndpoints.map((endpoint) => {
                const isSelected = selectedIds.has(endpoint.slug);
                return (
                  <button
                    key={endpoint.slug}
                    type='button'
                    onClick={() => {
                      onToggle(endpoint);
                    }}
                    className={cn(
                      'flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors',
                      isSelected ? 'bg-muted ring-secondary/20 ring-1' : 'hover:bg-muted',
                    )}
                    role='option'
                    aria-selected={isSelected}
                  >
                    {/* Checkbox indicator */}
                    <div
                      className={cn(
                        'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors',
                        isSelected ? 'border-secondary bg-secondary' : 'border-input bg-card',
                      )}
                      aria-hidden='true'
                    >
                      {isSelected && <Check className='h-3 w-3 text-white' />}
                    </div>

                    {/* Endpoint info */}
                    <div className='min-w-0 flex-1'>
                      <p className='text-foreground truncate text-sm font-medium'>
                        {endpoint.name}
                      </p>
                      {endpoint.description ? (
                        <p className='text-muted-foreground truncate text-xs'>
                          {endpoint.description}
                        </p>
                      ) : null}
                      <span className='text-secondary text-[11px]'>{endpoint.slug}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        {endpoints.length > 0 ? (
          <div className='border-border border-t px-3 py-2'>
            <p className='text-muted-foreground text-center text-[10px]'>
              {selectedCount > 0
                ? `${selectedCount} source${selectedCount === 1 ? '' : 's'} selected`
                : `${endpoints.length} source${endpoints.length === 1 ? '' : 's'} available`}
            </p>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
