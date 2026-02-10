/**
 * Hero Component
 *
 * Landing page hero section with search input and model selection.
 * Uses shared hooks for model management and workflow execution.
 */
import { useCallback } from 'react';

import type { ChatSource } from '@/lib/types';

import { useNavigate } from 'react-router-dom';

import { ModelSelector } from '@/components/chat/model-selector';
import { QueryInput, SearchSuggestions } from '@/components/query/query-input';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { WorkflowOverlay } from '@/components/workflow';
import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import { useDataSources } from '@/hooks/use-data-sources';
import { useModels } from '@/hooks/use-models';

// =============================================================================
// Constants
// =============================================================================

const FEATURES = [
  { label: 'Secure & Private', color: 'bg-chart-1', icon: '🔒' },
  { label: 'Rare Data & Models', color: 'bg-chart-2', icon: '💎' },
  { label: 'Federated Access', color: 'bg-chart-3', icon: '🌐' }
] as const;

const SEARCH_SUGGESTIONS = [
  'Find genomics datasets',
  'Query financial data sources',
  'Explore climate research',
  'Access medical imaging data'
] as const;

// =============================================================================
// Types
// =============================================================================

export interface HeroProperties {
  /** Called when user completes a search (navigates to chat with results) */
  onSearch?: (query: string, selectedModel: ChatSource | null) => void;
  /** Called when authentication is required */
  onAuthRequired?: () => void;
  /** When true, Hero takes full viewport height and centers content */
  fullHeight?: boolean;
  /** Optional pre-selected model (e.g., from URL params) */
  initialModel?: ChatSource | null;
}

// =============================================================================
// Component
// =============================================================================

export function Hero({
  onSearch,
  onAuthRequired: _onAuthRequired,
  fullHeight = false,
  initialModel
}: Readonly<HeroProperties>) {
  const navigate = useNavigate();

  // Use shared hooks for model and data source management
  const {
    models,
    selectedModel,
    setSelectedModel,
    isLoading: isLoadingModels
  } = useModels({
    initialModel
  });
  const { sources } = useDataSources();

  // Use workflow hook for query execution
  const workflow = useChatWorkflow({
    model: selectedModel,
    dataSources: sources,
    onComplete: (result) => {
      // Navigate to chat with the completed result
      // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
      navigate('/chat', {
        state: {
          query: result.query,
          model: selectedModel,
          initialResult: result
        }
      });
    },
    onError: (error) => {
      console.error('Workflow error:', error);
    }
  });

  // Handle query submission - either use workflow or direct navigation
  const handleSubmit = useCallback(
    (query: string) => {
      if (onSearch) {
        // If onSearch is provided, let parent handle navigation
        onSearch(query, selectedModel);
      } else {
        // Use workflow for full execution flow
        void workflow.submitQuery(query);
      }
    },
    [onSearch, selectedModel, workflow]
  );

  // Handle suggestion click
  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      handleSubmit(suggestion);
    },
    [handleSubmit]
  );

  // Determine if workflow is active (not idle)
  const isWorkflowActive = workflow.phase !== 'idle';

  return (
    <>
      {/* Model Selector - Fixed top left, matching chat-view layout */}
      <div className='fixed top-4 left-24 z-40'>
        <ModelSelector
          selectedModel={selectedModel}
          onModelSelect={setSelectedModel}
          models={models}
          isLoading={isLoadingModels}
        />
      </div>

      {/* Hero Section */}
      <section
        className={`relative bg-background flex items-center justify-center px-6 ${
          fullHeight ? 'min-h-[calc(100vh-2rem)]' : 'min-h-[60vh]'
        }`}
      >
        <div className='mx-auto w-full max-w-3xl space-y-12'>
          {/* Logo */}
          <div className='flex items-center justify-center gap-4'>
            <OpenMinedIcon className='h-8 w-8' />
            <span className='font-rubik text-foreground text-2xl font-medium tracking-tight'>SyftHub</span>
          </div>

          {/* Tagline */}
          <div className='space-y-6 pb-4 text-center'>
            <h1 className='font-rubik text-foreground text-4xl font-medium leading-tight'>
              Access the World's{' '}
              <span className='from-chart-1 via-chart-2 to-chart-3 bg-gradient-to-r bg-clip-text text-transparent'>
                Collective Intelligence
              </span>
            </h1>
            <div className='space-y-3'>
              <p className='font-inter text-foreground/90 text-lg font-medium'>
                Query trusted data sources — public, copyrighted, or private — directly from source.
              </p>
              <p className='font-inter text-muted-foreground text-sm'>
                Built for researchers, developers, and organizations seeking reliable data access
              </p>
            </div>
          </div>

          {/* Feature Badges and Search Bar */}
          <div className='space-y-6'>
            {/* Feature Badges */}
            <div className='flex flex-wrap items-center justify-center gap-6'>
              {FEATURES.map((feature, index) => (
                <div key={index} className='flex items-center gap-3 rounded-full border bg-card/50 px-4 py-2 backdrop-blur-sm'>
                  <span className='text-base'>{feature.icon}</span>
                  <span className='font-inter text-foreground/80 text-sm font-medium'>{feature.label}</span>
                </div>
              ))}
            </div>

            {/* Search Bar */}
            <div className='space-y-4'>
              <QueryInput
                variant='hero'
                onSubmit={handleSubmit}
                disabled={isWorkflowActive}
                isProcessing={workflow.phase === 'streaming'}
                placeholder='What are you looking for…'
                autoFocus
                id='hero-search'
                ariaLabel='Search for data sources, models, or topics'
              />

              {/* Search Suggestions Pills */}
              <SearchSuggestions
                suggestions={SEARCH_SUGGESTIONS}
                onSelect={handleSuggestionClick}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Workflow Overlay - shown when workflow is active */}
      <WorkflowOverlay workflow={workflow} availableSources={sources} />
    </>
  );
}
