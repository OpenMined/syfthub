import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import Brain from 'lucide-react/dist/esm/icons/brain';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';

import { estimatePerRequestCost, formatPerRequestCost } from '@/lib/cost-utils';

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
  const containerReference = useRef<HTMLDivElement>(null);
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

  // Handle click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerReference.current &&
        !containerReference.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setSearchQuery('');
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  // Handle escape key to close dropdown
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
        setSearchQuery('');
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.removeEventListener('keydown', handleEscape);
      };
    }
  }, [isOpen]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputReference.current) {
      // Small delay to ensure the element is mounted
      const timer = setTimeout(() => {
        searchInputReference.current?.focus();
      }, 50);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isOpen]);

  const handleToggle = useCallback(() => {
    setIsOpen((previous) => !previous);
    if (isOpen) {
      setSearchQuery('');
    }
  }, [isOpen]);

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
    <div ref={containerReference} className='relative'>
      {/* Trigger Button */}
      <button
        type='button'
        onClick={handleToggle}
        disabled={isLoading}
        className={`group flex items-center gap-2 rounded-xl border px-3 py-2.5 transition-colors ${
          isOpen
            ? 'border-foreground bg-muted text-foreground'
            : 'border-border bg-card text-muted-foreground hover:border-input hover:bg-accent hover:text-foreground'
        } ${isLoading ? 'cursor-wait opacity-70' : ''}`}
        aria-expanded={isOpen}
        aria-haspopup='listbox'
      >
        {isLoading ? (
          <Loader2 className='text-secondary h-4 w-4 animate-spin' aria-hidden='true' />
        ) : (
          <Brain className='text-secondary h-4 w-4' aria-hidden='true' />
        )}
        <span className='font-inter max-w-[120px] truncate text-sm font-medium'>
          {selectedModel ? selectedModel.name : 'Select model'}
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          aria-hidden='true'
        />
      </button>

      {/* Dropdown Panel */}
      <AnimatePresence>
        {isOpen ? (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className='border-border bg-card absolute top-full left-0 z-50 mt-2 w-[340px] overflow-hidden rounded-xl border shadow-lg'
          >
            {/* Header */}
            <div className='border-border border-b px-3 pt-3 pb-2'>
              <h3 className='font-inter text-foreground mb-2 text-sm font-semibold'>
                Select Model
              </h3>
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
                    const isSelected = selectedModel?.slug === model.slug;
                    const perRequestCost = estimatePerRequestCost(model);
                    const formattedCost = formatPerRequestCost(perRequestCost);
                    const modelPath =
                      model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;

                    return (
                      <button
                        key={model.slug}
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
                          <span className='font-inter text-secondary text-[11px]'>{modelPath}</span>
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
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
