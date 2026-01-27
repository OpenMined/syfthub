import React, { useCallback, useEffect, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Send from 'lucide-react/dist/esm/icons/send';

import { ModelSelector } from '@/components/chat/model-selector';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';

// Static data hoisted outside component to prevent recreation on each render
const FEATURES = [
  { label: 'Secure & Private', color: 'bg-chart-1' },
  { label: 'Rare Data & Models', color: 'bg-secondary' },
  { label: 'Federated, Permissioned Access', color: 'bg-chart-3' }
] as const;

const SEARCH_SUGGESTIONS = [
  'Look for genomics data',
  'Look for news in finance',
  'Find climate research sources'
] as const;

interface HeroProperties {
  onSearch?: (query: string) => void;
  onAuthRequired?: () => void;
  /** When true, Hero takes full viewport height and centers content (use when no other content below) */
  fullHeight?: boolean;
  /** Currently selected model for chat */
  selectedModel?: ChatSource | null;
  /** Callback when user selects a model */
  onModelSelect?: (model: ChatSource) => void;
  /** Available models for the model selector dropdown */
  availableModels?: ChatSource[];
  /** Whether models are being loaded */
  isLoadingModels?: boolean;
}

export function Hero({
  onSearch,
  onAuthRequired: _onAuthRequired,
  fullHeight = false,
  selectedModel = null,
  onModelSelect,
  availableModels = [],
  isLoadingModels = false
}: Readonly<HeroProperties>) {
  const [searchValue, setSearchValue] = useState('');
  const inputReference = useRef<HTMLInputElement>(null);

  // Auto-focus on desktop only (avoid virtual keyboard on mobile)
  useEffect(() => {
    const isDesktop = globalThis.matchMedia('(min-width: 1024px)').matches;
    if (isDesktop && inputReference.current) {
      inputReference.current.focus();
    }
  }, []);

  // Memoized handlers for stable references - prevents re-renders of child components
  const handleSearch = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault();
      if (searchValue.trim() && onSearch) {
        onSearch(searchValue);
      }
    },
    [searchValue, onSearch]
  );

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      setSearchValue(suggestion);
      if (onSearch) {
        onSearch(suggestion);
      }
    },
    [onSearch]
  );

  // Memoized input handler using functional setState for stable reference
  const handleInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchValue(event.target.value);
  }, []);

  return (
    <section
      className={`bg-background flex items-center justify-center px-6 ${
        fullHeight ? 'min-h-[calc(100vh-2rem)]' : 'min-h-[50vh]'
      }`}
    >
      <div className='mx-auto w-full max-w-2xl space-y-8'>
        {/* Logo */}
        <div className='flex items-center justify-center gap-3'>
          <OpenMinedIcon className='h-7 w-7' />
          <span className='font-rubik text-foreground text-xl font-normal'>SyftHub</span>
        </div>

        {/* Tagline */}
        <div className='space-y-4 pb-4 text-center'>
          <h1 className='font-rubik text-foreground text-3xl font-medium'>
            Access the World's{' '}
            <span className='from-secondary via-chart-3 to-chart-1 bg-gradient-to-r bg-clip-text text-transparent'>
              Collective Intelligence
            </span>
          </h1>
          <p className='font-inter text-foreground text-base'>
            Query trusted data sources — public, copyrighted, or private — directly from source.
          </p>
        </div>

        {/* Feature Badges and Search Bar - grouped closer together */}
        <div className='space-y-6'>
          {/* Feature Badges */}
          <div className='flex flex-wrap items-center justify-center gap-8'>
            {FEATURES.map((feature, index) => (
              <div key={index} className='flex items-center gap-2'>
                <div className={`h-2 w-2 rounded-full ${feature.color}`}></div>
                <span className='font-inter text-foreground text-sm'>{feature.label}</span>
              </div>
            ))}
          </div>

          {/* Model Selector */}
          {onModelSelect ? (
            <div className='flex items-center justify-center'>
              <ModelSelector
                selectedModel={selectedModel}
                onModelSelect={onModelSelect}
                models={availableModels}
                isLoading={isLoadingModels}
              />
            </div>
          ) : null}

          {/* Search Bar */}
          <form onSubmit={handleSearch} className='space-y-4' role='search'>
            <div className='group relative'>
              <label htmlFor='hero-search' className='sr-only'>
                Search for data sources, models, or topics
              </label>
              <input
                id='hero-search'
                ref={inputReference}
                type='search'
                name='search'
                value={searchValue}
                onChange={handleInputChange}
                placeholder='What are you looking for…'
                className='font-inter border-input text-foreground placeholder:text-muted-foreground focus:ring-ring bg-background w-full rounded-xl border px-6 py-4 shadow-sm transition-colors transition-shadow focus:border-transparent focus:ring-2 focus:outline-none'
                autoComplete='off'
              />
              <button
                type='submit'
                aria-label='Search'
                className='group-focus-within:text-foreground hover:bg-muted absolute top-1/2 right-3 -translate-y-1/2 rounded-lg p-2 transition-colors'
              >
                <Send
                  className={`h-5 w-5 transition-colors ${
                    searchValue ? 'text-foreground' : 'text-muted-foreground'
                  }`}
                  aria-hidden='true'
                />
              </button>
            </div>

            {/* Search Suggestions Pills */}
            <div className='flex flex-wrap items-center justify-center gap-2.5'>
              {SEARCH_SUGGESTIONS.map((suggestion, index) => (
                <button
                  key={index}
                  type='button'
                  onClick={() => {
                    handleSuggestionClick(suggestion);
                  }}
                  className='font-inter border-border text-foreground hover:border-primary hover:bg-muted focus:ring-ring bg-background rounded-full border px-4 py-1.5 text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none'
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>
    </section>
  );
}
