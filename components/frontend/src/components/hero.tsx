/**
 * Hero Component
 *
 * Landing page hero section with search input and model selection.
 * Uses hero-04 layout pattern with two-column grid.
 */
import { useCallback, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import ArrowUpRight from 'lucide-react/dist/esm/icons/arrow-up-right';
import { Link, useNavigate } from 'react-router-dom';

import { AddSourcesModal } from '@/components/chat/add-sources-modal';
import { SearchInput } from '@/components/chat/search-input';
import { SearchSuggestions } from '@/components/query/query-input';
import { Badge } from '@/components/ui/badge';
import { WorkflowOverlay } from '@/components/workflow';
import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import { useDataSources } from '@/hooks/use-data-sources';
import { useModels } from '@/hooks/use-models';
import { useContextSelectionStore } from '@/stores/context-selection-store';

// =============================================================================
// Constants
// =============================================================================

const SEARCH_SUGGESTIONS = [
  'Ask WGA about parental leave',
  'Ask OpenMined about attribution'
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
  fullHeight: _fullHeight = false,
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
  const { sources, sourcesById } = useDataSources();
  const contextStore = useContextSelectionStore();

  // Source modal state
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);

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

  // Handle @mention completion — add source to context (tracked for sync)
  const handleMentionComplete = useCallback(
    (source: ChatSource) => {
      if (!contextStore.isSelected(source.id)) {
        contextStore.addMentionSource(source);
      }
    },
    [contextStore]
  );

  // Handle @mention sync — remove sources whose mentions were deleted from text
  const handleMentionSync = useCallback(
    (mentionedIds: Set<string>) => {
      contextStore.syncMentionSources(mentionedIds);
    },
    [contextStore]
  );

  // Handle removing a context source
  const handleRemoveSource = useCallback(
    (id: string) => {
      contextStore.removeSource(id);
    },
    [contextStore]
  );

  // Handle source modal confirm
  const handleSourceModalConfirm = useCallback(
    (selectedIds: Set<string>) => {
      contextStore.clearSources();
      for (const id of selectedIds) {
        const source = sourcesById.get(id) ?? sources.find((s) => s.id === id);
        if (source) {
          contextStore.addSource(source);
        }
      }
      setIsSourceModalOpen(false);
    },
    [contextStore, sourcesById, sources]
  );

  // Determine if workflow is active (not idle)
  const isWorkflowActive = workflow.phase !== 'idle';

  return (
    <>
      {/* Hero Section - hero-04 layout pattern */}
      <div className='flex min-h-screen items-center justify-center overflow-hidden'>
        <div className='mx-auto grid w-full max-w-7xl gap-16 px-6 py-12 lg:grid-cols-2 lg:py-0'>
          {/* Left column - Main content */}
          <div className='my-auto'>
            {/* Announcement Badge */}
            <Badge asChild className='border-border rounded-full py-1' variant='secondary'>
              <Link to='/about'>
                See how it works <ArrowUpRight className='ml-1 size-4' />
              </Link>
            </Badge>

            {/* Headline */}
            <h1 className='font-rubik mt-6 max-w-[20ch] text-4xl leading-[1.2] font-semibold tracking-[-0.035em] md:text-5xl lg:text-5xl xl:text-6xl'>
              Ask{' '}
              <span className='from-chart-1 via-chart-2 to-chart-3 bg-gradient-to-r bg-clip-text text-transparent'>
                anyone, anything
              </span>{' '}
              &mdash; at source
            </h1>

            {/* Subtitle */}
            <p className='text-foreground/80 font-inter mt-6 max-w-[60ch] text-lg'>
              Query AI models and data sources directly with attribution, compensation, and privacy
              built in. Connect to the collective intelligence network.
            </p>

            {/* Action Buttons */}
            {actionButtons && <div className='mt-8 flex items-center gap-4'>{actionButtons}</div>}

            {/* Search Input */}
            <div className='mt-8 max-w-xl space-y-4'>
              <SearchInput
                onSubmit={handleSubmit}
                disabled={isWorkflowActive}
                isProcessing={workflow.phase === 'streaming'}
                placeholder='Ask anything...'
                onContextClick={() => {
                  setIsSourceModalOpen(true);
                }}
                selectedContexts={contextStore
                  .getSourcesArray()
                  .map((s) => ({ id: s.id, label: s.name }))}
                onRemoveContext={handleRemoveSource}
                selectedModel={selectedModel}
                onModelSelect={setSelectedModel}
                models={models}
                isLoadingModels={isLoadingModels}
                enableMentions
                sources={sources}
                onMentionComplete={handleMentionComplete}
                onMentionSync={handleMentionSync}
              />

              {/* Search Suggestions Pills */}
              <SearchSuggestions
                suggestions={SEARCH_SUGGESTIONS}
                onSelect={handleSuggestionClick}
              />
            </div>
          </div>

          {/* Right column - Global Directory Block */}
          {sidePanel && (
            <div className='bg-accent/30 border-border/40 my-auto hidden max-h-[calc(100vh-8rem)] w-full max-w-xl overflow-hidden rounded-2xl border backdrop-blur-sm lg:block'>
              <div className='h-full overflow-y-auto p-4'>{sidePanel}</div>
            </div>
          )}
        </div>
      </div>

      {/* Workflow Overlay - shown when workflow is active */}
      <WorkflowOverlay workflow={workflow} />

      {/* Add Sources Modal */}
      <AddSourcesModal
        isOpen={isSourceModalOpen}
        onClose={() => {
          setIsSourceModalOpen(false);
        }}
        availableSources={sources}
        selectedSourceIds={new Set(contextStore.getSourcesArray().map((s) => s.id))}
        onConfirm={handleSourceModalConfirm}
      />
    </>
  );
}
