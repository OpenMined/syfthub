import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import Brain from 'lucide-react/dist/esm/icons/brain';
import Check from 'lucide-react/dist/esm/icons/check';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';
import Star from 'lucide-react/dist/esm/icons/star';
import { useNavigate } from 'react-router-dom';

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
  const navigate = useNavigate();
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

  const handleNavigateToEndpoint = useCallback(
    (event: React.MouseEvent, model: ChatSource) => {
      event.stopPropagation(); // Prevent selecting the model
      setIsOpen(false);
      setSearchQuery('');
      const path = model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;
      // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
      navigate(`/${path}`);
    },
    [navigate]
  );

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

      {/* Dropdown Panel - Opens downward from top left position */}
      <AnimatePresence>
        {isOpen ? (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className='border-border bg-card absolute top-full left-0 z-50 mt-2 w-[320px] overflow-hidden rounded-xl border shadow-lg'
          >
            {/* Search Input */}
            <div className='border-border border-b p-3'>
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
            <div className='max-h-[280px] overflow-y-auto p-2'>
              {filteredModels.length === 0 ? (
                <div className='font-inter text-muted-foreground py-8 text-center text-sm'>
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
                          isSelected ? 'bg-muted ring-secondary/20 ring-1' : 'hover:bg-muted'
                        }`}
                        role='option'
                        aria-selected={isSelected}
                      >
                        {/* Model Icon */}
                        <div
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                            isSelected ? 'bg-secondary text-white' : 'bg-accent text-secondary'
                          }`}
                          aria-hidden='true'
                        >
                          <Brain className='h-4 w-4' />
                        </div>

                        {/* Model Info */}
                        <div className='min-w-0 flex-1'>
                          <div className='mb-0.5 flex items-center gap-2'>
                            <span className='font-inter text-foreground truncate text-sm font-medium'>
                              {model.name}
                            </span>
                            {model.stars_count > 0 ? (
                              <div className='text-muted-foreground flex items-center gap-0.5'>
                                <Star className='h-3 w-3' aria-hidden='true' />
                                <span className='font-inter text-xs'>{model.stars_count}</span>
                              </div>
                            ) : null}
                          </div>
                          {/* Clickable path to endpoint page */}
                          <button
                            type='button'
                            onClick={(event) => {
                              handleNavigateToEndpoint(event, model);
                            }}
                            className='font-inter group/link text-secondary hover:text-foreground flex items-center gap-1 text-xs transition-colors hover:underline'
                          >
                            <span className='truncate'>
                              {model.full_path ??
                                `${model.owner_username ?? 'unknown'}/${model.slug}`}
                            </span>
                            <ExternalLink
                              className='h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover/link:opacity-100'
                              aria-hidden='true'
                            />
                          </button>
                          {model.version ? (
                            <span className='font-inter bg-accent text-muted-foreground mt-1 inline-block rounded px-1.5 py-0.5 text-[10px]'>
                              v{model.version}
                            </span>
                          ) : null}
                        </div>

                        {/* Selected Indicator */}
                        <div
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors ${
                            isSelected
                              ? 'bg-foreground text-background'
                              : 'border-input bg-card border'
                          }`}
                          aria-hidden='true'
                        >
                          {isSelected && <Check className='h-3 w-3' />}
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
