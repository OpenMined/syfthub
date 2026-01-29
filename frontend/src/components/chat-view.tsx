/**
 * ChatView Component
 *
 * Main chat interface for querying data sources.
 * Uses shared hooks for model management, data sources, and workflow execution.
 */
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { WorkflowResult } from '@/hooks/use-chat-workflow';
import type { ChatSource } from '@/lib/types';
import type { SourcesData } from './chat/sources-section';

import { AnimatePresence, motion } from 'framer-motion';
import ArrowDown from 'lucide-react/dist/esm/icons/arrow-down';
import Brain from 'lucide-react/dist/esm/icons/brain';
import Check from 'lucide-react/dist/esm/icons/check';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Info from 'lucide-react/dist/esm/icons/info';
import Settings2 from 'lucide-react/dist/esm/icons/settings-2';
import X from 'lucide-react/dist/esm/icons/x';

import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import { useDataSources } from '@/hooks/use-data-sources';
import { useModels } from '@/hooks/use-models';
import { formatCostPerUnit, getCostsFromSource } from '@/lib/cost-utils';
import { filterSourcesForAutocomplete } from '@/lib/validation';

import { CostEstimationPanel } from './chat/cost-estimation-panel';
import { EndpointConfirmation } from './chat/endpoint-confirmation';
import { MarkdownMessage } from './chat/markdown-message';
import { ModelSelector } from './chat/model-selector';
import { SourcesSection } from './chat/sources-section';
import { StatusIndicator } from './chat/status-indicator';
import { QueryInput } from './query/query-input';
import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

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
// AdvancedPanel Sub-components
// =============================================================================

interface CostBadgesProps {
  inputPerToken: number;
  outputPerToken: number;
  colorScheme: 'green' | 'purple';
}

function CostBadges({ inputPerToken, outputPerToken, colorScheme }: Readonly<CostBadgesProps>) {
  const hasInputCost = inputPerToken > 0;
  const hasOutputCost = outputPerToken > 0;

  const colorClasses =
    colorScheme === 'green'
      ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300'
      : 'border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300';

  if (!hasInputCost && !hasOutputCost) {
    return (
      <Badge
        variant='secondary'
        className='font-inter border-border bg-muted text-muted-foreground h-5 px-2 text-[10px] font-normal'
      >
        No pricing
      </Badge>
    );
  }

  return (
    <>
      {hasInputCost && (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          In: {formatCostPerUnit(inputPerToken, 'request')}
        </Badge>
      )}
      {hasOutputCost && (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          Out: {formatCostPerUnit(outputPerToken, 'request')}
        </Badge>
      )}
    </>
  );
}

interface SourceCardProps {
  source: ChatSource;
  onRemove: () => void;
}

function SourceCard({ source, onRemove }: Readonly<SourceCardProps>) {
  const costs = getCostsFromSource(source);

  return (
    <div className='group bg-card relative rounded-lg border border-green-100 p-3 shadow-sm dark:border-green-800'>
      <button
        onClick={onRemove}
        className='absolute top-2 right-2 rounded p-1 text-red-500 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-950'
        aria-label={`Remove ${source.name}`}
      >
        <X className='h-3 w-3' aria-hidden='true' />
      </button>
      <div className='mb-3 flex items-center gap-3'>
        <div className='font-inter flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-green-100 text-xs font-bold text-green-700 dark:bg-green-900 dark:text-green-300'>
          {source.name.slice(0, 2).toUpperCase() || '??'}
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='font-inter text-foreground block truncate text-sm font-medium'
            title={source.name}
          >
            {source.name}
          </span>
          {source.full_path && (
            <span className='font-inter text-muted-foreground truncate text-xs'>
              {source.full_path}
            </span>
          )}
        </div>
      </div>
      <div className='flex flex-wrap gap-2'>
        <CostBadges
          inputPerToken={costs.inputPerToken}
          outputPerToken={costs.outputPerToken}
          colorScheme='green'
        />
      </div>
    </div>
  );
}

interface SuggestionItemProps {
  source: ChatSource;
  isSelected: boolean;
  onSelect: () => void;
}

function SuggestionItem({ source, isSelected, onSelect }: Readonly<SuggestionItemProps>) {
  return (
    <button
      type='button'
      onClick={onSelect}
      className='hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left first:rounded-t-lg last:rounded-b-lg'
    >
      <div className='font-inter flex h-6 w-6 shrink-0 items-center justify-center rounded bg-green-100 text-[10px] font-bold text-green-700'>
        {source.name.slice(0, 2).toUpperCase()}
      </div>
      <div className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block truncate text-xs font-medium'>
          {source.name}
        </span>
        <span className='font-inter text-muted-foreground truncate text-[10px]'>
          {source.full_path}
        </span>
      </div>
      {isSelected && <Check className='h-3 w-3 text-green-600' />}
    </button>
  );
}

interface ModelDisplayProps {
  model: ChatSource | null;
  modelCosts: { inputPerToken: number; outputPerToken: number } | null;
  isFactualMode: boolean;
}

function ModelDisplay({ model, modelCosts, isFactualMode }: Readonly<ModelDisplayProps>) {
  if (!model) {
    return (
      <div className='font-inter bg-card/50 rounded-lg border border-dashed border-purple-200 py-6 text-center text-sm text-purple-700/50 dark:border-purple-800 dark:text-purple-400/50'>
        <p>No model selected</p>
        <p className='mt-1 text-xs'>Select a model from the dropdown above</p>
      </div>
    );
  }

  return (
    <>
      <div className='flex items-center gap-3'>
        <div className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300'>
          <Brain className='h-4 w-4' />
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='font-inter text-foreground block truncate text-sm font-medium'
            title={model.name}
          >
            {model.name}
          </span>
          <span className='font-inter text-muted-foreground text-xs'>
            {model.version ? `v${model.version}` : 'latest'}
          </span>
        </div>
      </div>
      <div className='flex flex-wrap gap-2'>
        <CostBadges
          inputPerToken={modelCosts?.inputPerToken ?? 0}
          outputPerToken={modelCosts?.outputPerToken ?? 0}
          colorScheme='purple'
        />
      </div>
      <div
        id='mode-description'
        className='font-inter text-muted-foreground mt-2 flex items-start gap-2 border-t border-purple-50 pt-2 text-xs dark:border-purple-900'
      >
        <Info className='mt-0.5 h-3 w-3 shrink-0' aria-hidden='true' />
        {isFactualMode
          ? 'Strict mode: Results will be grounded in retrieved data only.'
          : 'Nuanced mode: Model can infer and synthesize broader context.'}
      </div>
    </>
  );
}

// =============================================================================
// AdvancedPanel Component
// =============================================================================

interface AdvancedPanelProps {
  isOpen: boolean;
  onClose: () => void;
  availableSources: ChatSource[];
  selectedSourceIds: Set<string>;
  onToggleSource: (id: string) => void;
  isFactualMode: boolean;
  onModeChange: (isFactual: boolean) => void;
  selectedModel: ChatSource | null;
  availableModels: ChatSource[];
  onModelSelect: (model: ChatSource) => void;
  isLoadingModels: boolean;
}

const AdvancedPanel = memo(function AdvancedPanel({
  isOpen,
  onClose,
  availableSources,
  selectedSourceIds,
  onToggleSource,
  isFactualMode,
  onModeChange,
  selectedModel,
  availableModels,
  onModelSelect,
  isLoadingModels
}: Readonly<AdvancedPanelProps>) {
  const activeSources = useMemo(
    () => availableSources.filter((s) => selectedSourceIds.has(s.id)),
    [availableSources, selectedSourceIds]
  );

  const [customSourceInput, setCustomSourceInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const panelReference = useRef<HTMLDivElement>(null);

  const modelCosts = useMemo(
    () => (selectedModel ? getCostsFromSource(selectedModel) : null),
    [selectedModel]
  );

  const suggestions = useMemo(() => {
    if (!customSourceInput.trim()) return [];
    return filterSourcesForAutocomplete(availableSources, customSourceInput, 5);
  }, [availableSources, customSourceInput]);

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen && panelReference.current) {
      const timer = setTimeout(() => panelReference.current?.focus(), 100);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isOpen]);

  const handleSelectSuggestion = useCallback(
    (source: ChatSource) => {
      if (availableSources.some((s) => s.id === source.id)) {
        onToggleSource(source.id);
      }
      setCustomSourceInput('');
      setShowSuggestions(false);
    },
    [availableSources, onToggleSource]
  );

  const handleInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setCustomSourceInput(event.target.value);
    setShowSuggestions(event.target.value.trim().length > 0);
  }, []);

  const handleInputBlur = useCallback(() => {
    setTimeout(() => {
      setShowSuggestions(false);
    }, 200);
  }, []);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className='fixed inset-0 z-50 bg-black/20 backdrop-blur-sm'
            aria-hidden='true'
          />
          <motion.div
            ref={panelReference}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className='border-border bg-card fixed top-0 right-0 z-50 flex h-full w-[400px] flex-col border-l shadow-2xl'
            role='dialog'
            aria-modal='true'
            aria-labelledby='panel-title'
            tabIndex={-1}
          >
            {/* Header */}
            <div className='border-border bg-background flex items-center justify-between border-b p-6'>
              <div className='flex items-center gap-3'>
                <div className='bg-primary flex h-10 w-10 items-center justify-center rounded-lg'>
                  <Settings2 className='h-5 w-5 text-white' />
                </div>
                <div>
                  <h2 id='panel-title' className='font-rubik text-foreground text-lg font-medium'>
                    Execution Layout
                  </h2>
                  <p className='font-inter text-muted-foreground text-xs'>Pipeline configuration</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className='hover:bg-accent rounded-full p-2 transition-colors'
                aria-label='Close panel'
              >
                <X className='text-muted-foreground h-5 w-5' aria-hidden='true' />
              </button>
            </div>

            <div className='flex-1 space-y-4 overflow-y-auto p-6'>
              {/* Data Sources Section */}
              <div className='rounded-xl border border-green-200 bg-green-50/30 p-4 dark:border-green-800 dark:bg-green-950/30'>
                <div className='mb-4 flex items-center justify-between'>
                  <div className='font-inter flex items-center gap-2 font-medium text-green-800 dark:text-green-300'>
                    <Database className='h-4 w-4' />
                    <h3>Data Sources</h3>
                    <span className='text-xs font-normal text-green-600/60'>
                      ({activeSources.length} selected)
                    </span>
                  </div>
                  <div className='flex items-center gap-2'>
                    <Label
                      htmlFor='mode-toggle'
                      className='font-inter cursor-pointer text-[10px] font-medium text-green-800 dark:text-green-300'
                    >
                      {isFactualMode ? 'Factual' : 'Nuanced'}
                    </Label>
                    <Switch
                      id='mode-toggle'
                      checked={!isFactualMode}
                      onCheckedChange={(checked) => {
                        onModeChange(!checked);
                      }}
                      className='h-4 w-8 data-[state=checked]:bg-purple-600 data-[state=unchecked]:bg-green-600 dark:data-[state=checked]:bg-purple-500 dark:data-[state=unchecked]:bg-green-500'
                      aria-describedby='mode-description'
                    />
                  </div>
                </div>

                <div className='space-y-3'>
                  {activeSources.length === 0 ? (
                    <div className='font-inter bg-card/50 rounded-lg border border-dashed border-green-200 py-8 text-center text-sm text-green-700/50 dark:border-green-800 dark:text-green-400/50'>
                      <p>No sources selected</p>
                      <p className='mt-1 text-xs'>Select sources from the chat or add below</p>
                    </div>
                  ) : (
                    activeSources.map((source) => (
                      <SourceCard
                        key={source.id}
                        source={source}
                        onRemove={() => {
                          onToggleSource(source.id);
                        }}
                      />
                    ))
                  )}

                  {/* Source search input */}
                  <div className='relative mt-2'>
                    <label htmlFor='custom-source-input' className='sr-only'>
                      Add source (owner/endpoint-name)
                    </label>
                    <input
                      id='custom-source-input'
                      type='text'
                      value={customSourceInput}
                      onChange={handleInputChange}
                      onFocus={() => {
                        setShowSuggestions(customSourceInput.trim().length > 0);
                      }}
                      onBlur={handleInputBlur}
                      placeholder='Add source (owner/endpoint-name)…'
                      className='font-inter bg-card w-full rounded-lg border border-green-200 py-2 pr-8 pl-3 text-xs transition-colors placeholder:text-green-700/40 focus:border-green-500 focus:ring-1 focus:ring-green-500/20 focus:outline-none dark:border-green-800 dark:placeholder:text-green-400/40'
                      autoComplete='off'
                    />
                    <div className='font-inter text-muted-foreground pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-[10px]'>
                      ↵
                    </div>

                    {showSuggestions && suggestions.length > 0 && (
                      <div className='border-border bg-card absolute top-full left-0 z-10 mt-1 w-full rounded-lg border shadow-lg'>
                        {suggestions.map((source) => (
                          <SuggestionItem
                            key={source.id}
                            source={source}
                            isSelected={selectedSourceIds.has(source.id)}
                            onSelect={() => {
                              handleSelectSuggestion(source);
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Arrow */}
              <div className='text-muted-foreground flex justify-center'>
                <ArrowDown className='h-5 w-5' aria-hidden='true' />
              </div>

              {/* Model Section */}
              <div className='rounded-xl border border-purple-200 bg-purple-50/30 p-4 dark:border-purple-800 dark:bg-purple-950/30'>
                <div className='mb-4 flex items-center justify-between'>
                  <div className='font-inter flex items-center gap-2 font-medium text-purple-800 dark:text-purple-300'>
                    <Cpu className='h-4 w-4' />
                    <h3>Model</h3>
                  </div>
                  <ModelSelector
                    selectedModel={selectedModel}
                    onModelSelect={onModelSelect}
                    models={availableModels}
                    isLoading={isLoadingModels}
                  />
                </div>
                <div className='bg-card space-y-3 rounded-lg border border-purple-100 p-3 shadow-sm dark:border-purple-800'>
                  <ModelDisplay
                    model={selectedModel}
                    modelCosts={modelCosts}
                    isFactualMode={isFactualMode}
                  />
                </div>
              </div>

              {/* Arrow */}
              <div className='text-muted-foreground flex flex-col items-center gap-1'>
                <ArrowDown className='h-5 w-5' aria-hidden='true' />
                <span className='font-inter text-[10px] font-medium'>Process & Combine</span>
              </div>

              {/* Cost Estimation */}
              <CostEstimationPanel
                model={selectedModel}
                dataSources={activeSources}
                customSourceCount={0}
              />
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
});

// =============================================================================
// ChatView Component
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
          {(workflow.phase === 'searching' || workflow.phase === 'selecting') && workflow.query && (
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
