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
  { label: 'Secure & Private', color: 'bg-chart-1' },
  { label: 'Rare Data & Models', color: 'bg-secondary' },
  { label: 'Federated, Permissioned Access', color: 'bg-chart-3' }
] as const;

const SEARCH_SUGGESTIONS = [
  'What is attribution-based control?',
  'What is paid parental leave?',
  "What's AI data scarcity problem?"
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

          {/* Feature Badges and Search Bar */}
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

            {/* Search Bar */}
            <div className='space-y-4'>
              <QueryInput
                variant='hero'
                onSubmit={handleSubmit}
                disabled={isWorkflowActive}
                isProcessing={workflow.phase === 'streaming'}
                placeholder='What is attribution-based control?'
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
