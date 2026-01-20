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
        className={`group flex items-center gap-2 rounded-xl border px-3 py-2.5 transition-all ${
          isOpen
            ? 'border-[#272532] bg-[#f7f6f9] text-[#272532]'
            : 'border-[#ecebef] bg-[#fcfcfd] text-[#5e5a72] hover:border-[#cfcdd6] hover:bg-[#f1f0f4] hover:text-[#272532]'
        } ${isLoading ? 'cursor-wait opacity-70' : ''}`}
        aria-expanded={isOpen}
        aria-haspopup='listbox'
      >
        {isLoading ? (
          <Loader2 className='h-4 w-4 animate-spin text-[#6976ae]' />
        ) : (
          <Brain className='h-4 w-4 text-[#6976ae]' />
        )}
        <span className='font-inter max-w-[120px] truncate text-sm font-medium'>
          {selectedModel ? selectedModel.name : 'Select model'}
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown Panel - Opens downward from top left position */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className='absolute top-full left-0 z-50 mt-2 w-[320px] overflow-hidden rounded-xl border border-[#ecebef] bg-white shadow-lg'
          >
            {/* Search Input */}
            <div className='border-b border-[#ecebef] p-3'>
              <div className='relative'>
                <Search className='absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-[#b4b0bf]' />
                <input
                  ref={searchInputReference}
                  type='text'
                  value={searchQuery}
                  onChange={handleSearchChange}
                  placeholder='Search models...'
                  className='font-inter w-full rounded-lg border border-[#ecebef] bg-[#fcfcfd] py-2 pr-3 pl-9 text-sm transition-all placeholder:text-[#b4b0bf] focus:border-[#272532] focus:ring-2 focus:ring-[#272532]/10 focus:outline-none'
                />
              </div>
            </div>

            {/* Model List */}
            <div className='max-h-[280px] overflow-y-auto p-2'>
              {filteredModels.length === 0 ? (
                <div className='font-inter py-8 text-center text-sm text-[#b4b0bf]'>
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
                        className={`group flex w-full items-start gap-3 rounded-lg p-3 text-left transition-all ${
                          isSelected
                            ? 'bg-[#f7f6f9] ring-1 ring-[#6976ae]/20'
                            : 'hover:bg-[#f7f6f9]'
                        }`}
                        role='option'
                        aria-selected={isSelected}
                      >
                        {/* Model Icon */}
                        <div
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                            isSelected ? 'bg-[#6976ae] text-white' : 'bg-[#f1f0f4] text-[#6976ae]'
                          }`}
                        >
                          <Brain className='h-4 w-4' />
                        </div>

                        {/* Model Info */}
                        <div className='min-w-0 flex-1'>
                          <div className='mb-0.5 flex items-center gap-2'>
                            <span className='font-inter truncate text-sm font-medium text-[#272532]'>
                              {model.name}
                            </span>
                            {model.stars_count > 0 && (
                              <div className='flex items-center gap-0.5 text-[#b4b0bf]'>
                                <Star className='h-3 w-3' />
                                <span className='font-inter text-xs'>{model.stars_count}</span>
                              </div>
                            )}
                          </div>
                          {/* Clickable path to endpoint page */}
                          <button
                            type='button'
                            onClick={(event) => {
                              handleNavigateToEndpoint(event, model);
                            }}
                            className='font-inter group/link flex items-center gap-1 text-xs text-[#6976ae] transition-colors hover:text-[#272532] hover:underline'
                          >
                            <span className='truncate'>
                              {model.full_path ??
                                `${model.owner_username ?? 'unknown'}/${model.slug}`}
                            </span>
                            <ExternalLink className='h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover/link:opacity-100' />
                          </button>
                          {model.version && (
                            <span className='font-inter mt-1 inline-block rounded bg-[#f1f0f4] px-1.5 py-0.5 text-[10px] text-[#5e5a72]'>
                              v{model.version}
                            </span>
                          )}
                        </div>

                        {/* Selected Indicator */}
                        <div
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-all ${
                            isSelected
                              ? 'bg-[#272532] text-white'
                              : 'border border-[#cfcdd6] bg-white'
                          }`}
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
            {models.length > 0 && (
              <div className='border-t border-[#ecebef] bg-[#fcfcfd] px-3 py-2'>
                <p className='font-inter text-center text-[10px] text-[#b4b0bf]'>
                  {models.length} model{models.length === 1 ? '' : 's'} available
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
