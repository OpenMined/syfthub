import React, { useCallback, useMemo, useRef, useState } from 'react';

import { Brain, ChevronDown, Loader2, Search } from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

// Minimal contract — works with both local EndpointInfo and hub NetworkAgentInfo.
export interface SelectableModel {
  slug: string;
  name: string;
  description: string;
  /** Hub owner username. When set, the dropdown shows the fully qualified
   *  "owner/slug" identifier instead of the bare slug. */
  ownerUsername?: string;
}

/** Fully qualified identifier: "owner/slug" when the owner is known,
 *  otherwise the bare slug (e.g. for local endpoints with no hub owner). */
function qualifiedId(model: SelectableModel): string {
  return model.ownerUsername ? `${model.ownerUsername}/${model.slug}` : model.slug;
}

interface ModelSelectorProps<T extends SelectableModel> {
  selectedModel: T | null;
  onModelSelect: (model: T) => void;
  models: T[];
  isLoading?: boolean;
  /** Parent is responsible for coalescing/TTL — this fires on every open. */
  onOpen?: () => void;
  /** When true, the trigger is rendered read-only: no popover, no selection
   *  change. Used by ReviewChatPane to pin the dropdown to the review's
   *  endpoint — the continuation is bound to that agent and letting the user
   *  pick a different model would be silently overridden at submit time. */
  locked?: boolean;
}

export function ModelSelector<T extends SelectableModel>({
  selectedModel,
  onModelSelect,
  models,
  isLoading = false,
  onOpen,
  locked = false,
}: Readonly<ModelSelectorProps<T>>) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputReference = useRef<HTMLInputElement>(null);

  const filteredModels = useMemo(() => {
    if (!searchQuery.trim()) return models;
    const query = searchQuery.toLowerCase();
    return models.filter(
      (model) =>
        model.name.toLowerCase().includes(query) ||
        model.description.toLowerCase().includes(query) ||
        qualifiedId(model).toLowerCase().includes(query)
    );
  }, [models, searchQuery]);

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open);
    if (open) {
      onOpen?.();
      setTimeout(() => {
        searchInputReference.current?.focus();
      }, 0);
    } else {
      setSearchQuery('');
    }
  }, [onOpen]);

  const handleSelect = useCallback(
    (model: T) => {
      onModelSelect(model);
      setIsOpen(false);
      setSearchQuery('');
    },
    [onModelSelect]
  );

  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  }, []);

  // Locked variant: render a non-interactive button that shows the pinned
  // model but never opens the popover. Keeps the same icon + name layout so
  // the composer looks identical to the live pane — just without the chevron
  // affordance and with a fixed cursor.
  if (locked) {
    return (
      <button
        type='button'
        disabled
        title={selectedModel?.name ? `Continuation pinned to ${selectedModel.name}` : 'Continuation locked to this agent'}
        className='text-muted-foreground flex items-center gap-1 rounded-lg px-2.5 py-2 opacity-80 cursor-not-allowed'
        aria-disabled='true'
      >
        <Brain className='h-3.5 w-3.5' aria-hidden='true' />
        <span className='max-w-[120px] truncate text-xs font-normal'>
          {selectedModel ? selectedModel.name : 'Locked'}
        </span>
      </button>
    );
  }

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          type='button'
          disabled={isLoading}
          className={`group flex items-center gap-1 rounded-lg px-2.5 py-2 transition-colors ${
            isOpen
              ? 'bg-accent text-foreground'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
          } ${isLoading ? 'cursor-wait opacity-70' : ''}`}
          aria-expanded={isOpen}
          aria-haspopup='listbox'
        >
          {isLoading ? (
            <Loader2 className='text-muted-foreground h-3.5 w-3.5 animate-spin' aria-hidden='true' />
          ) : (
            <Brain className='text-muted-foreground h-3.5 w-3.5' aria-hidden='true' />
          )}
          <span className='max-w-[120px] truncate text-xs font-normal'>
            {selectedModel ? selectedModel.name : 'Select model'}
          </span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
            aria-hidden='true'
          />
        </button>
      </PopoverTrigger>

      <PopoverContent side='top' align='start' className='w-[340px] overflow-hidden rounded-lg p-0'>
        <div className='border-border border-b px-3 pt-3 pb-2'>
          <h3 className='text-foreground mb-2 text-sm font-semibold'>Select Model</h3>
          <div className='relative'>
            <label htmlFor='model-search' className='sr-only'>
              Search models
            </label>
            <Search
              className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2'
              aria-hidden='true'
            />
            <input
              id='model-search'
              ref={searchInputReference}
              type='search'
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder='Search models…'
              className='border-border bg-card placeholder:text-muted-foreground focus:border-foreground focus:ring-foreground/10 w-full rounded-lg border py-2 pr-3 pl-9 text-sm transition-colors focus:ring-2 focus:outline-none'
              autoComplete='off'
            />
          </div>
        </div>

        <div className='max-h-[300px] overflow-y-auto p-2'>
          {filteredModels.length === 0 ? (
            <div className='text-muted-foreground py-8 text-center text-sm'>
              {searchQuery ? 'No models found' : 'No models available'}
            </div>
          ) : (
            <div className='space-y-1'>
              {filteredModels.map((model) => {
                const isSelected = selectedModel?.slug === model.slug;

                return (
                  <button
                    key={model.slug}
                    type='button'
                    onClick={() => {
                      handleSelect(model);
                    }}
                    className={`group flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors ${
                      isSelected ? 'bg-muted ring-primary/25 ring-1' : 'hover:bg-muted'
                    }`}
                    role='option'
                    aria-selected={isSelected}
                  >
                    <div
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                        isSelected ? 'border-primary bg-primary' : 'border-input bg-card'
                      }`}
                      aria-hidden='true'
                    >
                      {isSelected && (
                        <div className='bg-primary-foreground h-1.5 w-1.5 rounded-full' />
                      )}
                    </div>

                    <div className='min-w-0 flex-1'>
                      <div className='mb-0.5 flex items-center gap-2'>
                        <span className='text-foreground truncate text-sm font-semibold'>
                          {model.name}
                        </span>
                      </div>

                      {model.description ? (
                        <p className='text-muted-foreground mb-0.5 truncate text-xs'>
                          {model.description}
                        </p>
                      ) : null}

                      <span className='text-muted-foreground font-mono text-[11px]'>
                        {qualifiedId(model)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {models.length > 0 ? (
          <div className='border-border bg-card border-t px-3 py-2'>
            <p className='text-muted-foreground text-center text-[10px]'>
              {models.length} model{models.length === 1 ? '' : 's'} available
            </p>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
