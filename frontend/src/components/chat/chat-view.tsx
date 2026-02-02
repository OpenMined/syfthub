/**
 * ChatView Component
 *
 * Main chat interface for querying data sources.
 * Uses shared hooks for model management, data sources, and workflow execution.
 * Orchestrates sub-components: AdvancedPanel, ModelSelector, EndpointConfirmation, etc.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { WorkflowResult } from '@/hooks/use-chat-workflow';
import type { ChatSource } from '@/lib/types';
import type { SourcesData } from './sources-section';

import Settings2 from 'lucide-react/dist/esm/icons/settings-2';

import { ChatEmptyState } from '@/components/onboarding';
import { QueryInput } from '@/components/query/query-input';
import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import { useDataSources } from '@/hooks/use-data-sources';
import { useModels } from '@/hooks/use-models';
import { useOnboardingStore } from '@/stores/onboarding-store';

import { AdvancedPanel } from './advanced-panel';
import { EndpointConfirmation } from './endpoint-confirmation';
import { MarkdownMessage } from './markdown-message';
import { ModelSelector } from './model-selector';
import { SourcesSection } from './sources-section';
import { StatusIndicator } from './status-indicator';

// =============================================================================
// Types
// =============================================================================

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  type?: 'text';
  isThinking?: boolean;
  aggregatorSources?: SourcesData;
}

export interface ChatViewProperties {
  /** Initial query from navigation (e.g., from home page search) */
  initialQuery: string;
  /** Optional pre-selected model from navigation */
  initialModel?: ChatSource | null;
  /** Optional initial result if workflow was completed before navigation */
  initialResult?: WorkflowResult | null;
}

// =============================================================================
// Component
// =============================================================================

export function ChatView({
  initialQuery,
  initialModel,
  initialResult
}: Readonly<ChatViewProperties>) {
  // Use shared hooks
  const {
    models,
    selectedModel,
    setSelectedModel,
    isLoading: isLoadingModels
  } = useModels({
    initialModel
  });
  const { sources, sourcesById } = useDataSources();
  const markFirstQueryComplete = useOnboardingStore((s) => s.markFirstQueryComplete);

  // Local state for messages and UI
  const [messages, setMessages] = useState<Message[]>(() => {
    // Initialize with initial query as first message if provided
    if (initialResult) {
      // If we have an initial result from Hero, add both user and assistant messages
      return [
        { id: '1', role: 'user' as const, content: initialResult.query, type: 'text' as const },
        {
          id: '2',
          role: 'assistant' as const,
          content: initialResult.content,
          type: 'text' as const,
          aggregatorSources: initialResult.sources
        }
      ];
    }
    if (initialQuery) {
      return [{ id: '1', role: 'user' as const, content: initialQuery, type: 'text' as const }];
    }
    return [];
  });

  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [isFactualMode, setIsFactualMode] = useState(true);
  const messagesEndReference = useRef<HTMLDivElement>(null);

  // Use workflow hook
  const workflow = useChatWorkflow({
    model: selectedModel,
    dataSources: sources,
    dataSourcesById: sourcesById,
    onComplete: (result) => {
      markFirstQueryComplete();
      // Add user message and assistant response to messages
      setMessages((previous) => {
        // Check if user message already exists (avoid duplicates)
        const hasUserMessage = previous.some(
          (m) => m.role === 'user' && m.content === result.query
        );

        const newMessages = hasUserMessage
          ? previous
          : [
              ...previous,
              {
                id: Date.now().toString(),
                role: 'user' as const,
                content: result.query,
                type: 'text' as const
              }
            ];

        return [
          ...newMessages,
          {
            id: (Date.now() + 1).toString(),
            role: 'assistant' as const,
            content: result.content,
            type: 'text' as const,
            aggregatorSources: result.sources
          }
        ];
      });
    }
  });

  // Auto-trigger workflow for initial query (when navigated from home page)
  useEffect(() => {
    // Only trigger if:
    // 1. We have an initial query
    // 2. No initial result (not already processed)
    // 3. Workflow is idle
    // 4. Model is selected
    // 5. Sources have loaded
    if (
      initialQuery &&
      !initialResult &&
      workflow.phase === 'idle' &&
      selectedModel &&
      sources.length > 0
    ) {
      void workflow.submitQuery(initialQuery);
    }
    // Only run once when dependencies are ready, not on every change
  }, [initialQuery, initialResult, selectedModel, sources.length]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndReference.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, workflow.streamedContent]);

  // Handlers
  const handleOpenPanel = useCallback(() => {
    setIsPanelOpen(true);
  }, []);
  const handleClosePanel = useCallback(() => {
    setIsPanelOpen(false);
  }, []);
  const handleModeChange = useCallback((isFactual: boolean) => {
    setIsFactualMode(isFactual);
  }, []);

  // Handle query submission
  const handleSubmit = useCallback(
    (query: string) => {
      void workflow.submitQuery(query);
    },
    [workflow]
  );

  // Determine if workflow is in a blocking state
  const isWorkflowActive =
    workflow.phase !== 'idle' && workflow.phase !== 'complete' && workflow.phase !== 'error';

  return (
    <div className='bg-card min-h-screen pb-32'>
      {/* Advanced Panel */}
      <AdvancedPanel
        isOpen={isPanelOpen}
        onClose={handleClosePanel}
        availableSources={sources}
        selectedSourceIds={workflow.selectedSources}
        onToggleSource={workflow.toggleSource}
        isFactualMode={isFactualMode}
        onModeChange={handleModeChange}
        selectedModel={selectedModel}
        availableModels={models}
        onModelSelect={setSelectedModel}
        isLoadingModels={isLoadingModels}
      />

      {/* Model Selector - Fixed top left */}
      <div className='fixed top-4 left-24 z-40'>
        <ModelSelector
          selectedModel={selectedModel}
          onModelSelect={setSelectedModel}
          models={models}
          isLoading={isLoadingModels}
        />
      </div>

      {/* Messages Area */}
      <div className='mx-auto max-w-4xl px-6 py-8 pt-16'>
        {messages.length === 0 && !initialQuery && workflow.phase === 'idle' ? (
          <ChatEmptyState onSuggestionClick={handleSubmit} />
        ) : (
          <div className='space-y-8'>
            {/* Existing messages */}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'} max-w-full`}
                >
                  {message.content && (
                    <div
                      className={`font-inter max-w-2xl rounded-2xl px-5 py-3 shadow-sm ${
                        message.role === 'user'
                          ? 'bg-primary text-primary-foreground rounded-br-none text-[15px] leading-relaxed'
                          : 'border-border bg-muted text-foreground rounded-bl-none border'
                      }`}
                    >
                      {message.role === 'assistant' ? (
                        <MarkdownMessage content={message.content} />
                      ) : (
                        message.content
                      )}
                    </div>
                  )}
                  {message.role === 'assistant' &&
                    message.aggregatorSources &&
                    Object.keys(message.aggregatorSources).length > 0 && (
                      <div className='mt-2 w-full max-w-2xl'>
                        <SourcesSection sources={message.aggregatorSources} />
                      </div>
                    )}
                </div>
              </div>
            ))}

            {/* Workflow UI - Endpoint Confirmation */}
            {(workflow.phase === 'searching' || workflow.phase === 'selecting') &&
              workflow.query && (
                <div className='flex justify-start'>
                  <EndpointConfirmation
                    query={workflow.query}
                    suggestedEndpoints={workflow.suggestedEndpoints}
                    isSearching={workflow.phase === 'searching'}
                    selectedSources={workflow.selectedSources}
                    availableSources={sources}
                    onToggleSource={workflow.toggleSource}
                    onConfirm={workflow.confirmSelection}
                    onCancel={workflow.cancelSelection}
                  />
                </div>
              )}

            {/* Workflow UI - Processing Status */}
            {(workflow.phase === 'preparing' || workflow.phase === 'streaming') && (
              <div className='flex justify-start'>
                <div className='flex max-w-full flex-col items-start'>
                  {workflow.processingStatus && (
                    <StatusIndicator status={workflow.processingStatus} />
                  )}
                  {workflow.streamedContent && (
                    <div className='font-inter border-border bg-muted text-foreground mt-2 max-w-2xl rounded-2xl rounded-bl-none border px-5 py-3 shadow-sm'>
                      <MarkdownMessage content={workflow.streamedContent} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Error display */}
            {workflow.phase === 'error' && workflow.error && (
              <div className='flex justify-start'>
                <div className='font-inter max-w-2xl rounded-2xl rounded-bl-none border border-red-200 bg-red-50 px-5 py-3 text-red-700 shadow-sm dark:border-red-800 dark:bg-red-950 dark:text-red-300'>
                  {workflow.error}
                </div>
              </div>
            )}

            <div ref={messagesEndReference} />
          </div>
        )}
      </div>

      {/* Input Area - Fixed bottom */}
      <div className='border-border bg-card fixed bottom-0 left-0 z-40 w-full border-t p-4 pl-24'>
        <div className='mx-auto max-w-3xl'>
          <div className='flex gap-3'>
            <button
              type='button'
              onClick={handleOpenPanel}
              className='group border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground flex items-center justify-center rounded-xl border p-3.5 transition-colors'
              aria-label='Open advanced configuration'
            >
              <Settings2
                className='h-5 w-5 transition-transform duration-500 group-hover:rotate-45'
                aria-hidden='true'
              />
            </button>

            <div className='flex-1'>
              <QueryInput
                variant='chat'
                onSubmit={handleSubmit}
                disabled={isWorkflowActive}
                isProcessing={workflow.phase === 'streaming'}
                placeholder='Ask a follow-up question…'
                id='chat-followup-input'
                ariaLabel='Ask a follow-up question'
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
