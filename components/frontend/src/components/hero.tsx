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

const SEARCH_SUGGESTIONS = [
  'Ask the WGA about parental leave for screenwriters',
  'Ask OpenMined about attribution-based control'
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
  /** Optional panel rendered to the right of the search area */
  sidePanel?: React.ReactNode;
  /** Action buttons rendered below the search suggestions */
  actionButtons?: React.ReactNode;
}

// =============================================================================
// Component
// =============================================================================

export function Hero({
  onSearch,
  onAuthRequired: _onAuthRequired,
  fullHeight = false,
  initialModel,
  sidePanel,
  actionButtons
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
        className={`bg-background relative px-6 ${
          fullHeight ? 'flex min-h-[calc(100vh-2rem)] items-center justify-center' : 'py-16'
        }`}
      >
        {/* Two-column grid: left (search) / right (directory) */}
        <div
          className={`mx-auto w-full ${
            sidePanel ? 'grid max-w-6xl items-start gap-16 lg:grid-cols-[1fr_0.8fr]' : 'max-w-3xl'
          }`}
        >
          {/* Left column */}
          <div className='space-y-8'>
            {/* Logo */}
            <div
              className={`flex items-center gap-4 ${sidePanel ? 'justify-start' : 'justify-center'}`}
            >
              <OpenMinedIcon className='h-8 w-8' />
              <span className='font-rubik text-foreground text-2xl font-normal tracking-tight'>
                SyftHub
              </span>
            </div>

            {/* Tagline */}
            <div className={`space-y-3 ${sidePanel ? 'text-left' : 'text-center'}`}>
              <h1 className='font-rubik text-foreground text-4xl leading-tight font-medium'>
                Ask{' '}
                <span className='from-chart-1 via-chart-2 to-chart-3 bg-gradient-to-r bg-clip-text text-transparent'>
                  anyone, anything
                </span>{' '}
                &mdash; at source
              </h1>
              <p className='font-inter text-muted-foreground text-base'>
                A directory for querying trusted data sources with attribution and privacy built in.
              </p>
            </div>

            {/* Search Bar */}
            <div className='space-y-4'>
              <QueryInput
                variant='hero'
                onSubmit={handleSubmit}
                disabled={isWorkflowActive}
                isProcessing={workflow.phase === 'streaming'}
                placeholder='Ask a question about any connected source...'
                autoFocus
                id='hero-search'
                ariaLabel='Query connected data sources'
              />

              {/* Search Suggestions Pills */}
              <SearchSuggestions
                suggestions={SEARCH_SUGGESTIONS}
                onSelect={handleSuggestionClick}
              />
            </div>
          </div>

          {/* Right column: Global Directory — pt offsets past the logo row */}
          {sidePanel && <div className='hidden pt-14 lg:block'>{sidePanel}</div>}
        </div>

        {/* Action Buttons — centered underneath everything, with divider lines */}
        {actionButtons && (
          <div className='mx-auto mt-10 flex max-w-xl items-center gap-6'>
            <div className='border-border/40 h-px flex-1 border-t' />
            {actionButtons}
            <div className='border-border/40 h-px flex-1 border-t' />
          </div>
        )}
      </section>

      {/* Workflow Overlay - shown when workflow is active */}
      <WorkflowOverlay workflow={workflow} />
    </>
  );
}
