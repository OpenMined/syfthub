import React, { useState } from 'react';

import { Send } from 'lucide-react';

import { OpenMinedIcon } from '@/components/ui/openmined-icon';

interface HeroProperties {
  onSearch?: (query: string) => void;
  onAuthRequired?: () => void;
  /** When true, Hero takes full viewport height and centers content (use when no other content below) */
  fullHeight?: boolean;
}

export function Hero({
  onSearch,
  onAuthRequired: _onAuthRequired,
  fullHeight = false
}: Readonly<HeroProperties>) {
  const [searchValue, setSearchValue] = useState('');

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    if (searchValue.trim() && onSearch) {
      onSearch(searchValue);
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setSearchValue(suggestion);
    if (onSearch) {
      onSearch(suggestion);
    }
  };

  const features = [
    { label: 'Secure & Private', color: 'bg-syft-green' },
    { label: 'Rare Data & Models', color: 'bg-syft-secondary' },
    { label: 'Federated, Permissioned Access', color: 'bg-syft-purple' }
  ];

  const searchSuggestions = [
    'Look for genomics data',
    'Look for news in finance',
    'Find climate research sources'
  ];

  return (
    <section
      className={`flex items-center justify-center bg-white px-6 ${
        fullHeight ? 'min-h-[calc(100vh-2rem)]' : 'min-h-[50vh]'
      }`}
    >
      <div className='mx-auto w-full max-w-2xl space-y-8'>
        {/* Logo */}
        <div className='flex items-center justify-center gap-3'>
          <OpenMinedIcon className='h-7 w-7' />
          <span className='font-rubik text-syft-primary text-xl font-normal'>SyftHub</span>
        </div>

        {/* Tagline */}
        <div className='text-center space-y-4 pb-4'>
          <h1 className='font-rubik text-syft-primary text-3xl font-medium'>
            Access the World's <span className='text-transparent bg-gradient-to-r from-syft-secondary via-syft-purple to-syft-green bg-clip-text'>Collective Intelligence</span>
          </h1>
          <p className='font-inter text-syft-primary text-base'>
            Query trusted data sources — public, copyrighted, or private — directly from source.
          </p>
        </div>

        {/* Feature Badges and Search Bar - grouped closer together */}
        <div className='space-y-6'>
          {/* Feature Badges */}
          <div className='flex flex-wrap items-center justify-center gap-8'>
            {features.map((feature, index) => (
              <div key={index} className='flex items-center gap-2'>
                <div className={`h-2 w-2 rounded-full ${feature.color}`}></div>
                <span className='font-inter text-syft-primary text-sm'>{feature.label}</span>
              </div>
            ))}
          </div>

          {/* Search Bar */}
          <form onSubmit={handleSearch} className='space-y-4'>
          <div className='group relative'>
            <input
              autoFocus
              type='text'
              value={searchValue}
              onChange={(event) => {
                setSearchValue(event.target.value);
              }}
              placeholder='What are you looking for?'
              className='font-inter border-syft-border-light text-syft-primary placeholder:text-syft-placeholder focus:ring-syft-primary w-full rounded-xl border bg-white px-6 py-4 shadow-sm transition-all focus:border-transparent focus:ring-2 focus:outline-none'
            />
            <button
              type='submit'
              aria-label='Search'
              className='group-focus-within:text-syft-primary hover:bg-syft-surface absolute top-1/2 right-3 -translate-y-1/2 rounded-lg p-2 transition-colors'
            >
              <Send
                className={`h-5 w-5 transition-colors ${
                  searchValue ? 'text-syft-primary' : 'text-syft-placeholder'
                }`}
              />
            </button>
          </div>

          {/* Search Suggestions Pills */}
          <div className='flex flex-wrap items-center justify-center gap-2.5'>
            {searchSuggestions.map((suggestion, index) => (
              <button
                key={index}
                type='button'
                onClick={() => {
                  handleSuggestionClick(suggestion);
                }}
                className='font-inter border-syft-border text-syft-primary hover:border-syft-primary hover:bg-syft-surface focus:ring-syft-primary rounded-full border bg-white px-4 py-1.5 text-sm transition-all focus:ring-2 focus:ring-offset-2 focus:outline-none'
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
