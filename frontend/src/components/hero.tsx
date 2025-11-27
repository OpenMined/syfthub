import React, { useState } from 'react';

import { Send, Sparkles } from 'lucide-react';

interface HeroProperties {
  onSearch?: (query: string) => void;
  onAuthRequired?: () => void;
}

export function Hero({ onSearch, onAuthRequired: _onAuthRequired }: Readonly<HeroProperties>) {
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
    { label: 'Secure & Private', color: 'bg-[#64bb62]' },
    { label: 'Rare Data & Models', color: 'bg-[#6976ae]' },
    { label: 'Permissioned Access', color: 'bg-[#937098]' }
  ];

  const searchSuggestions = [
    'Look for genomics data',
    'Look for news in finance',
    'Find climate research sources'
  ];

  return (
    <section className='flex min-h-[50vh] items-center justify-center bg-white px-6'>
      <div className='mx-auto w-full max-w-2xl space-y-6'>
        {/* Logo */}
        <div className='flex items-center justify-center gap-2.5'>
          <Sparkles className='h-7 w-7 text-[#6976ae]' />
          <span className='font-rubik text-xl font-medium text-black'>SyftHub</span>
        </div>

        {/* Tagline */}
        <div className='text-center'>
          <p className='font-inter text-lg text-black'>
            Explore trustworthy data sources and discover insights{' '}
            <span className='font-medium text-black'>beyond public reach</span>
          </p>
        </div>

        {/* Feature Badges */}
        <div className='flex flex-wrap items-center justify-center gap-6'>
          {features.map((feature, index) => (
            <div key={index} className='flex items-center gap-2'>
              <div className={`h-2 w-2 rounded-full ${feature.color}`}></div>
              <span className='font-inter text-sm text-black'>{feature.label}</span>
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
              placeholder='Ask anything from collective intelligence'
              className='font-inter w-full rounded-xl border border-[#cfcdd6] bg-white px-6 py-4 text-[#353243] shadow-sm transition-all placeholder:text-[#b4b0bf] focus:border-transparent focus:ring-2 focus:ring-[#272532] focus:outline-none'
            />
            <button
              type='submit'
              aria-label='Search'
              className='absolute top-1/2 right-3 -translate-y-1/2 rounded-lg p-2 transition-colors group-focus-within:text-[#272532] hover:bg-[#f7f6f9]'
            >
              <Send
                className={`h-5 w-5 transition-colors ${
                  searchValue ? 'text-[#272532]' : 'text-[#b4b0bf]'
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
                className='font-inter rounded-full border border-[#e0dfe4] bg-white px-4 py-1.5 text-sm text-black transition-all hover:border-[#272532] hover:bg-[#f7f6f9] focus:ring-2 focus:ring-[#272532] focus:ring-offset-2 focus:outline-none'
              >
                {suggestion}
              </button>
            ))}
          </div>
        </form>
      </div>
    </section>
  );
}
