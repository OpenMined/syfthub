import React, { useCallback, useMemo, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Brain from 'lucide-react/dist/esm/icons/brain';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { estimatePerRequestCost, formatPerRequestCost } from '@/lib/cost-utils';

/**
 * Get a unique identifier for a model that distinguishes models with the same name
 * but different owners. Uses full_path (owner/slug) when available, otherwise
 * constructs it from owner_username and slug.
 */
function getModelUniqueId(model: ChatSource): string {
  return model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;
}

interface ModelSelectorProps {
  selectedModel: ChatSource | null;
  onModelSelect: (model: ChatSource) => void;
  models: ChatSource[];
  isLoading?: boolean;
}

export function ModelSelector({
  selectedModel,
  onModelSelect,
  models,
  isLoading = false
}: Readonly<ModelSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputReference = useRef<HTMLInputElement>(null);

  // Filter models based on search query
  const filteredModels = useMemo(() => {
    if (!searchQuery.trim()) return models;

    const query = searchQuery.toLowerCase();
    return models.filter(
      (model) =>
        model.name.toLowerCase().includes(query) ||
        model.description.toLowerCase().includes(query) ||
        model.slug.toLowerCase().includes(query)
    );
  }, [models, searchQuery]);

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open);
    if (open) {
      setTimeout(() => {
        searchInputReference.current?.focus();
      }, 0);
    } else {
      setSearchQuery('');
    }
  }, []);

  const handleSelect = useCallback(
    (model: ChatSource) => {
      onModelSelect(model);
      setIsOpen(false);
      setSearchQuery('');
    },
    [onModelSelect]
  );

  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  }, []);

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
            <Loader2
              className='text-muted-foreground h-3.5 w-3.5 animate-spin'
              aria-hidden='true'
            />
          ) : (
            <Brain className='text-muted-foreground h-3.5 w-3.5' aria-hidden='true' />
          )}
          <span className='font-inter max-w-[120px] truncate text-xs font-normal'>
            {selectedModel ? selectedModel.name : 'Select model'}
          </span>
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
            aria-hidden='true'
          />
        </button>
      </PopoverTrigger>

      <PopoverContent side='top' align='start' className='w-[340px] overflow-hidden rounded-xl p-0'>
        {/* Header */}
        <div className='border-border border-b px-3 pt-3 pb-2'>
          <h3 className='font-inter text-foreground mb-2 text-sm font-semibold'>Select Model</h3>
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
              className='font-inter border-border bg-card placeholder:text-muted-foreground focus:border-foreground focus:ring-foreground/10 w-full rounded-lg border py-2 pr-3 pl-9 text-sm transition-colors transition-shadow focus:ring-2 focus:outline-none'
              autoComplete='off'
            />
          </div>
        </div>

        {/* Model List */}
        <div className='max-h-[300px] overflow-y-auto p-2'>
          {filteredModels.length === 0 ? (
            <div className='font-inter text-muted-foreground py-8 text-center text-sm'>
              {searchQuery ? 'No models found' : 'No models available'}
            </div>
          ) : (
            <div className='space-y-1'>
              {filteredModels.map((model) => {
                const modelUniqueId = getModelUniqueId(model);
                const isSelected =
                  selectedModel !== null && getModelUniqueId(selectedModel) === modelUniqueId;
                const perRequestCost = estimatePerRequestCost(model);
                const formattedCost = formatPerRequestCost(perRequestCost);

                return (
                  <button
                    key={modelUniqueId}
                    type='button'
                    onClick={() => {
                      handleSelect(model);
                    }}
                    className={`group flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors ${
                      isSelected ? 'bg-muted ring-secondary/20 ring-1' : 'hover:bg-muted'
                    }`}
                    role='option'
                    aria-selected={isSelected}
                  >
                    {/* Selection Indicator */}
                    <div
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                        isSelected ? 'border-secondary bg-secondary' : 'border-input bg-card'
                      }`}
                      aria-hidden='true'
                    >
                      {isSelected && <div className='h-1.5 w-1.5 rounded-full bg-white' />}
                    </div>

                    {/* Model Info */}
                    <div className='min-w-0 flex-1'>
                      {/* Name + Price row */}
                      <div className='mb-0.5 flex items-center gap-2'>
                        <span className='font-inter text-foreground truncate text-sm font-semibold'>
                          {model.name}
                        </span>
                        {formattedCost ? (
                          <span className='font-inter text-muted-foreground shrink-0 text-xs'>
                            {formattedCost}
                          </span>
                        ) : null}
                      </div>

                      {/* Description */}
                      {model.description ? (
                        <p className='font-inter text-muted-foreground mb-0.5 truncate text-xs'>
                          {model.description}
                        </p>
                      ) : null}

                      {/* Provider path */}
                      <span className='font-inter text-secondary text-[11px]'>{modelUniqueId}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer hint */}
        {models.length > 0 ? (
          <div className='border-border bg-card border-t px-3 py-2'>
            <p className='font-inter text-muted-foreground text-center text-[10px]'>
              {models.length} model{models.length === 1 ? '' : 's'} available
            </p>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
