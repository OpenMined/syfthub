import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatStreamEvent } from '@/lib/sdk-client';
import type { ChatSource } from '@/lib/types';
import type { SourcesData } from './chat/sources-section';
import type { ProcessingStatus } from './chat/status-indicator';

import { AnimatePresence, motion } from 'framer-motion';
import ArrowDown from 'lucide-react/dist/esm/icons/arrow-down';
import Brain from 'lucide-react/dist/esm/icons/brain';
import Check from 'lucide-react/dist/esm/icons/check';
import Clock from 'lucide-react/dist/esm/icons/clock';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Info from 'lucide-react/dist/esm/icons/info';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Settings2 from 'lucide-react/dist/esm/icons/settings-2';
import X from 'lucide-react/dist/esm/icons/x';

import { useAuth } from '@/context/auth-context';
import { triggerBalanceRefresh } from '@/hooks/use-accounting-api';
import { formatCostPerUnit, getCostsFromSource } from '@/lib/cost-utils';
import { analyzeQueryForSources, getChatDataSources, getChatModels } from '@/lib/endpoint-utils';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError,
  syftClient
} from '@/lib/sdk-client';
import { categorizeResults, MIN_QUERY_LENGTH, searchDataSources } from '@/lib/search-service';
import { filterSourcesForAutocomplete, validateEndpointPath } from '@/lib/validation';

import { CostEstimationPanel } from './chat/cost-estimation-panel';
import { MarkdownMessage } from './chat/markdown-message';
import { ModelSelector } from './chat/model-selector';
import { NoMatchMessage } from './chat/no-match-message';
import { SourceSearchLoader } from './chat/source-search-loader';
import { SourcesSection } from './chat/sources-section';
import { StatusIndicator } from './chat/status-indicator';
import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

// AdvancedPanel Props Interface
interface AdvancedPanelProps {
  isOpen: boolean;
  onClose: () => void;
  // Data sources
  availableSources: ChatSource[];
  selectedSourceIds: Set<string>;
  onToggleSource: (id: string) => void;
  // Custom sources (lifted state)
  customSources: string[];
  onAddCustomSource: (path: string) => void;
  onRemoveCustomSource: (path: string) => void;
  customSourceError: string | null;
  onCustomSourceErrorClear: () => void;
  // Mode (lifted state)
  isFactualMode: boolean;
  onModeChange: (isFactual: boolean) => void;
  // Model
  selectedModel: ChatSource | null;
  availableModels: ChatSource[];
  onModelSelect: (model: ChatSource) => void;
  isLoadingModels: boolean;
}

// ============================================================================
// Sub-components to reduce AdvancedPanel cognitive complexity
// ============================================================================

interface CostBadgesProps {
  inputPerToken: number;
  outputPerToken: number;
  colorScheme: 'green' | 'purple';
}

/** Renders cost badges or "No pricing" badge */
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
      {hasInputCost ? (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          In: {formatCostPerUnit(inputPerToken, 'request')}
        </Badge>
      ) : null}
      {hasOutputCost ? (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          Out: {formatCostPerUnit(outputPerToken, 'request')}
        </Badge>
      ) : null}
    </>
  );
}

interface SourceCardProps {
  source: ChatSource;
  onRemove: () => void;
}

/** Renders a single data source card with remove button */
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
          {source.full_path ? (
            <span className='font-inter text-muted-foreground truncate text-xs'>
              {source.full_path}
            </span>
          ) : null}
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

interface CustomSourceCardProps {
  sourcePath: string;
  onRemove: () => void;
}

/** Renders a custom source card */
function CustomSourceCard({ sourcePath, onRemove }: Readonly<CustomSourceCardProps>) {
  return (
    <div className='group bg-card relative rounded-lg border border-amber-200 p-3 shadow-sm dark:border-amber-800'>
      <button
        onClick={onRemove}
        className='absolute top-2 right-2 rounded p-1 text-red-500 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-950'
        aria-label={`Remove custom source ${sourcePath}`}
      >
        <X className='h-3 w-3' aria-hidden='true' />
      </button>
      <div className='mb-3 flex items-center gap-3'>
        <div className='font-inter flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-xs font-bold text-amber-700 dark:bg-amber-900 dark:text-amber-300'>
          EXT
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='font-inter text-foreground block truncate text-sm font-medium'
            title={sourcePath}
          >
            {sourcePath}
          </span>
        </div>
      </div>
      <Badge
        variant='secondary'
        className='font-inter h-5 border-amber-200 bg-amber-50 px-2 text-[10px] font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300'
      >
        Custom Source (pricing unknown)
      </Badge>
    </div>
  );
}

interface SuggestionItemProps {
  source: ChatSource;
  isSelected: boolean;
  onSelect: () => void;
}

/** Renders an autocomplete suggestion item */
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
      {isSelected ? <Check className='h-3 w-3 text-green-600' /> : null}
    </button>
  );
}

interface ModelDisplayProps {
  model: ChatSource | null;
  modelCosts: { inputPerToken: number; outputPerToken: number } | null;
  isFactualMode: boolean;
}

/** Renders the model display section */
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

// ============================================================================
// AdvancedPanel Component
// ============================================================================

// Memoized AdvancedPanel to prevent unnecessary re-renders
const AdvancedPanel = memo(function AdvancedPanel({
  isOpen,
  onClose,
  availableSources,
  selectedSourceIds,
  onToggleSource,
  customSources,
  onAddCustomSource,
  onRemoveCustomSource,
  customSourceError,
  onCustomSourceErrorClear,
  isFactualMode,
  onModeChange,
  selectedModel,
  availableModels,
  onModelSelect,
  isLoadingModels
}: Readonly<AdvancedPanelProps>) {
  // Memoize active sources for performance
  const activeSources = useMemo(
    () => availableSources.filter((s) => selectedSourceIds.has(s.id)),
    [availableSources, selectedSourceIds]
  );

  // Local state for custom source input
  const [customSourceInput, setCustomSourceInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputReference = useRef<HTMLInputElement>(null);
  const panelReference = useRef<HTMLDivElement>(null);

  // Memoize model costs for performance
  const modelCosts = useMemo(
    () => (selectedModel ? getCostsFromSource(selectedModel) : null),
    [selectedModel]
  );

  // Filter suggestions based on input
  const suggestions = useMemo(() => {
    if (!customSourceInput.trim()) return [];
    return filterSourcesForAutocomplete(availableSources, customSourceInput, 5);
  }, [availableSources, customSourceInput]);

  // Handle keyboard events for accessibility
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  // Focus trap - focus panel when opened
  useEffect(() => {
    if (isOpen && panelReference.current) {
      // Focus the panel for accessibility
      const timer = setTimeout(() => {
        panelReference.current?.focus();
      }, 100);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isOpen]);

  // Handle adding custom source with validation
  const handleAddSource = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Enter' && customSourceInput.trim()) {
        event.preventDefault();
        onAddCustomSource(customSourceInput.trim());
        setCustomSourceInput('');
        setShowSuggestions(false);
      }
    },
    [customSourceInput, onAddCustomSource]
  );

  // Handle selecting a suggestion
  const handleSelectSuggestion = useCallback(
    (source: ChatSource) => {
      if (source.full_path) {
        // If the source is already available, toggle it instead of adding as custom
        if (availableSources.some((s) => s.id === source.id)) {
          onToggleSource(source.id);
        } else {
          onAddCustomSource(source.full_path);
        }
      }
      setCustomSourceInput('');
      setShowSuggestions(false);
    },
    [availableSources, onToggleSource, onAddCustomSource]
  );

  // Handle input change
  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      setCustomSourceInput(event.target.value);
      setShowSuggestions(event.target.value.trim().length > 0);
      // Clear error when user starts typing
      if (customSourceError) {
        onCustomSourceErrorClear();
      }
    },
    [customSourceError, onCustomSourceErrorClear]
  );

  // Handle input blur
  const handleInputBlur = useCallback(() => {
    // Delay hiding suggestions to allow click events
    setTimeout(() => {
      setShowSuggestions(false);
    }, 200);
  }, []);

  return (
    <AnimatePresence>
      {isOpen ? (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className='fixed inset-0 z-50 bg-black/20 backdrop-blur-sm'
            aria-hidden='true'
          />

          {/* Panel */}
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
                      ({activeSources.length + customSources.length} selected)
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
                  {activeSources.length === 0 && customSources.length === 0 ? (
                    <div className='font-inter bg-card/50 rounded-lg border border-dashed border-green-200 py-8 text-center text-sm text-green-700/50 dark:border-green-800 dark:text-green-400/50'>
                      <p>No sources selected</p>
                      <p className='mt-1 text-xs'>Select sources from the chat or add below</p>
                    </div>
                  ) : (
                    <>
                      {/* Selected sources from available list */}
                      {activeSources.map((source) => (
                        <SourceCard
                          key={source.id}
                          source={source}
                          onRemove={() => {
                            onToggleSource(source.id);
                          }}
                        />
                      ))}
                      {/* Custom sources */}
                      {customSources.map((sourcePath) => (
                        <CustomSourceCard
                          key={sourcePath}
                          sourcePath={sourcePath}
                          onRemove={() => {
                            onRemoveCustomSource(sourcePath);
                          }}
                        />
                      ))}
                    </>
                  )}

                  {/* Custom source input with autocomplete */}
                  <div className='relative mt-2'>
                    <label htmlFor='custom-source-input' className='sr-only'>
                      Add source (owner/endpoint-name)
                    </label>
                    <input
                      ref={inputReference}
                      id='custom-source-input'
                      type='text'
                      value={customSourceInput}
                      onChange={handleInputChange}
                      onKeyDown={handleAddSource}
                      onFocus={() => {
                        setShowSuggestions(customSourceInput.trim().length > 0);
                      }}
                      onBlur={handleInputBlur}
                      placeholder='Add source (owner/endpoint-name)…'
                      className={`font-inter bg-card w-full rounded-lg border py-2 pr-8 pl-3 text-xs transition-colors transition-shadow placeholder:text-green-700/40 focus:ring-1 focus:outline-none dark:placeholder:text-green-400/40 ${
                        customSourceError
                          ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20'
                          : 'border-green-200 focus:border-green-500 focus:ring-green-500/20 dark:border-green-800'
                      }`}
                      autoComplete='off'
                      aria-invalid={!!customSourceError}
                      aria-describedby={customSourceError ? 'custom-source-error' : undefined}
                    />
                    <div
                      className='font-inter text-muted-foreground pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-[10px]'
                      aria-hidden='true'
                    >
                      ↵
                    </div>

                    {/* Error message */}
                    {customSourceError ? (
                      <p
                        id='custom-source-error'
                        className='font-inter mt-1 text-xs text-red-600'
                        role='alert'
                      >
                        {customSourceError}
                      </p>
                    ) : null}

                    {/* Autocomplete suggestions */}
                    {showSuggestions && suggestions.length > 0 ? (
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
                    ) : null}
                  </div>
                </div>
              </div>

              {/* Arrow */}
              <div className='text-muted-foreground flex justify-center'>
                <ArrowDown className='h-5 w-5' aria-hidden='true' />
              </div>

              {/* Model Section with inline selector */}
              <div className='rounded-xl border border-purple-200 bg-purple-50/30 p-4 dark:border-purple-800 dark:bg-purple-950/30'>
                <div className='mb-4 flex items-center justify-between'>
                  <div className='font-inter flex items-center gap-2 font-medium text-purple-800 dark:text-purple-300'>
                    <Cpu className='h-4 w-4' />
                    <h3>Model</h3>
                  </div>
                  {/* Inline model selector */}
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

              {/* Cost Estimation Section */}
              <CostEstimationPanel
                model={selectedModel}
                dataSources={activeSources}
                customSourceCount={customSources.length}
              />
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  );
});

interface SourceSelectorProperties {
  sources: ChatSource[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
}

// Memoized SourceSelector to prevent unnecessary re-renders when parent state changes
const SourceSelector = memo(function SourceSelector({
  sources,
  selectedIds,
  onToggle
}: Readonly<SourceSelectorProperties>) {
  return (
    <div className='my-4 w-full max-w-3xl space-y-3' role='group' aria-label='Select data sources'>
      {sources.map((source) => {
        const isSelected = selectedIds.has(source.id);

        let statusColor = 'bg-green-500';
        if (source.status === 'warning') statusColor = 'bg-yellow-500';
        if (source.status === 'inactive') statusColor = 'bg-red-500';

        return (
          <button
            key={source.id}
            type='button'
            onClick={() => {
              onToggle(source.id);
            }}
            aria-pressed={isSelected}
            className={`group relative flex w-full cursor-pointer items-start gap-4 rounded-xl border p-4 text-left transition-colors focus-visible:ring-2 focus-visible:ring-[#272532]/50 focus-visible:outline-none ${isSelected ? 'border-secondary bg-muted' : 'border-border bg-card hover:border-input'} `}
          >
            <div className='min-w-0 flex-1'>
              {/* Header */}
              <div className='mb-1 flex flex-wrap items-center gap-2'>
                <span
                  className={`font-inter font-medium transition-colors ${
                    isSelected ? 'text-foreground' : 'text-foreground group-hover:text-secondary'
                  }`}
                >
                  {source.name}
                </span>
                {source.tags.slice(0, 2).map((tag) => (
                  <span
                    key={tag}
                    className='font-inter bg-accent text-muted-foreground rounded-md px-2 py-0.5 text-xs'
                  >
                    {tag}
                  </span>
                ))}
                {source.tags.length > 2 ? (
                  <span className='font-inter bg-accent text-muted-foreground rounded-md px-2 py-0.5 text-xs'>
                    +{source.tags.length - 2}
                  </span>
                ) : null}
              </div>

              {/* Description with Status Dot */}
              <div className='mb-2 flex items-start gap-2'>
                <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusColor}`} />
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  {source.description}
                </p>
              </div>

              {/* Footer */}
              <div className='font-inter text-muted-foreground flex items-center gap-1.5 text-xs'>
                <Clock className='h-3.5 w-3.5' aria-hidden='true' />
                <span>Updated {source.updated}</span>
              </div>
            </div>

            {/* Checkbox indicator */}
            <div
              className={`mt-1 flex h-6 w-6 items-center justify-center rounded border transition-colors ${isSelected ? 'border-foreground bg-primary' : 'border-input bg-card group-hover:border-muted-foreground'} `}
              aria-hidden='true'
            >
              {isSelected && <Check className='h-3.5 w-3.5 text-white' />}
            </div>
          </button>
        );
      })}
    </div>
  );
});

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  type?: 'text' | 'source-selection' | 'source-search' | 'no-match';
  sources?: ChatSource[];
  isThinking?: boolean;
  /** Sources from aggregator response (document titles -> endpoint slug & content) */
  aggregatorSources?: SourcesData;
  /** Original query for no-match messages */
  searchQuery?: string;
}

interface ChatViewProperties {
  initialQuery: string;
}

// Helper function to process SDK streaming events (handles token content)
function processStreamEvent(event: ChatStreamEvent, onToken: (content: string) => void): void {
  switch (event.type) {
    case 'token': {
      onToken(event.content);
      break;
    }
    case 'error': {
      throw new Error(event.message);
    }
    default: {
      // Other events handled by updateStatusFromEvent
      break;
    }
  }
}

// Helper to extract a display name from an endpoint path (e.g., "owner/my-data-source" → "My Data Source")
function extractSourceDisplayName(path: string): string {
  const parts = path.split('/');
  const name = parts.at(-1) ?? path;
  return name
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

// Helper to update processing status from streaming events
function updateStatusFromEvent(
  event: ChatStreamEvent,
  setProcessingStatus: React.Dispatch<React.SetStateAction<ProcessingStatus | null>>
): void {
  switch (event.type) {
    case 'retrieval_start': {
      if (event.sourceCount === 0) {
        // No data sources - show preparing message
        setProcessingStatus({
          phase: 'retrieving',
          message: 'Preparing request…',
          completedSources: []
        });
      } else {
        setProcessingStatus({
          phase: 'retrieving',
          message: `Searching ${String(event.sourceCount)} data ${event.sourceCount === 1 ? 'source' : 'sources'}…`,
          retrieval: {
            completed: 0,
            total: event.sourceCount,
            documentsFound: 0
          },
          completedSources: []
        });
      }
      break;
    }

    case 'source_complete': {
      setProcessingStatus((previous) => {
        if (!previous) return null;
        const newCompleted = (previous.retrieval?.completed ?? 0) + 1;
        const newDocumentsFound =
          (previous.retrieval?.documentsFound ?? 0) + event.documentsRetrieved;
        const total = previous.retrieval?.total ?? 1;

        return {
          ...previous,
          message: `Retrieved from ${String(newCompleted)}/${String(total)} ${total === 1 ? 'source' : 'sources'}…`,
          retrieval: {
            completed: newCompleted,
            total,
            documentsFound: newDocumentsFound
          },
          completedSources: [
            ...previous.completedSources,
            {
              path: event.path,
              displayName: extractSourceDisplayName(event.path),
              status: event.status as 'success' | 'error' | 'timeout',
              documents: event.documentsRetrieved
            }
          ]
        };
      });
      break;
    }

    case 'retrieval_complete': {
      setProcessingStatus((previous) => {
        if (!previous) return null;
        const documentCount = event.totalDocuments;
        const documentLabel = documentCount === 1 ? 'document' : 'documents';
        const message =
          documentCount > 0
            ? `Found ${String(documentCount)} relevant ${documentLabel}`
            : 'No relevant documents found';
        return {
          ...previous,
          message,
          timing: {
            ...previous.timing,
            retrievalMs: event.timeMs
          }
        };
      });
      break;
    }

    case 'generation_start': {
      setProcessingStatus((previous) => ({
        phase: 'generating',
        message: 'Generating response…',
        completedSources: previous?.completedSources ?? [],
        retrieval: previous?.retrieval,
        timing: previous?.timing
      }));
      break;
    }

    case 'token': {
      // Update phase to streaming on first token (prevents excessive re-renders)
      setProcessingStatus((previous) => {
        if (!previous || previous.phase === 'streaming') return previous;
        return {
          ...previous,
          phase: 'streaming',
          message: 'Writing response…'
        };
      });
      break;
    }

    case 'done': {
      // Clear status - the response content is now visible
      setProcessingStatus(null);
      break;
    }

    case 'error': {
      setProcessingStatus((previous) => ({
        phase: 'error',
        message: event.message,
        completedSources: previous?.completedSources ?? [],
        retrieval: previous?.retrieval,
        timing: previous?.timing
      }));
      break;
    }
  }
}

// Helper to update a specific message in the messages array (also clears thinking state)
function updateMessageContent(messages: Message[], messageId: string, content: string): Message[] {
  return messages.map((message) =>
    message.id === messageId ? { ...message, content, isThinking: false } : message
  );
}

// Helper to add aggregator sources to a message
function addAggregatorSources(
  messages: Message[],
  messageId: string,
  aggregatorSources: SourcesData
): Message[] {
  return messages.map((message) =>
    message.id === messageId ? { ...message, aggregatorSources } : message
  );
}

// Helper to check if a source-selection message already exists (prevents duplicates from Strict Mode / remounts)
function hasSourceSelectionMessage(messages: Message[]): boolean {
  return messages.some((m) => m.type === 'source-selection');
}

// Helper to check if we already have a source-related message (error, source-selection, no-match, or search)
function hasSourceRelatedMessage(messages: Message[]): boolean {
  return messages.some(
    (m) =>
      m.type === 'source-selection' ||
      m.type === 'source-search' ||
      m.type === 'no-match' ||
      (m.role === 'assistant' && m.id.startsWith('source-'))
  );
}

// Helper to convert chat errors to user-friendly messages
function getChatErrorMessage(error: unknown): string {
  if (error instanceof AuthenticationError) {
    return 'Authentication required. Please log in again.';
  }
  if (error instanceof AggregatorError) {
    return `Chat service error: ${error.message}`;
  }
  if (error instanceof EndpointResolutionError) {
    return `Could not resolve endpoint: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

export function ChatView({ initialQuery }: Readonly<ChatViewProperties>) {
  const { user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([
    { id: '1', role: 'user', content: initialQuery, type: 'text' }
  ]);
  // Use Set for O(1) lookup performance when checking source selection
  const [selectedSources, setSelectedSources] = useState<Set<string>>(() => new Set());
  const [inputValue, setInputValue] = useState('');
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [availableSources, setAvailableSources] = useState<ChatSource[]>([]);
  const messagesEndReference = useRef<HTMLDivElement>(null);
  const abortControllerReference = useRef<AbortController | null>(null);

  // Model selection state
  const [selectedModel, setSelectedModel] = useState<ChatSource | null>(null);
  const [availableModels, setAvailableModels] = useState<ChatSource[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);

  // Chat processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus | null>(null);

  // Custom sources state (lifted from AdvancedPanel)
  const [customSources, setCustomSources] = useState<string[]>([]);
  const [customSourceError, setCustomSourceError] = useState<string | null>(null);

  // Factual/Nuanced mode state (lifted from AdvancedPanel)
  const [isFactualMode, setIsFactualMode] = useState(true);

  // Build Map for O(1) source lookups by ID (avoids repeated .find() calls)
  const availableSourcesById = useMemo(
    () => new Map(availableSources.map((source) => [source.id, source])),
    [availableSources]
  );

  // Load real data sources from backend and use RAG search for relevance
  useEffect(() => {
    let isMounted = true;
    const searchMessageId = `source-search-${String(Date.now())}`;

    // Filter predicate defined at useEffect level to avoid nesting depth issues
    const isNotSearchPlaceholder = (m: Message) => m.id !== searchMessageId;

    // Helper to update messages: filters out search placeholder and optionally adds new message
    const updateMessagesWithFilter = (
      newMessage: Message | null,
      checkFn: (msgs: Message[]) => boolean
    ) => {
      setMessages((previous) => {
        // eslint-disable-next-line unicorn/no-array-callback-reference -- Using named predicate to reduce nesting depth
        const filtered = previous.filter(isNotSearchPlaceholder);
        // Check against filtered array, not previous, since we've removed the search placeholder
        return newMessage && !checkFn(filtered) ? [...filtered, newMessage] : filtered;
      });
    };

    const loadDataSources = async () => {
      try {
        // First, load available sources for the source panel
        const sources = await getChatDataSources(100);

        // Guard against state updates after unmount
        if (!isMounted) return;

        setAvailableSources(sources);

        // Check for exact path mentions first (e.g., "owner/endpoint-name")
        const analysis = analyzeQueryForSources(initialQuery, sources);

        if (analysis.action === 'auto-select' && analysis.matchedEndpoint) {
          // Endpoint was explicitly mentioned - auto-select and proceed
          setSelectedSources(new Set([analysis.matchedEndpoint.id]));

          const autoSelectMessage: Message = {
            id: `auto-select-${String(Date.now())}`,
            role: 'assistant',
            content: analysis.mentionedPath
              ? `Found endpoint **${analysis.matchedEndpoint.name}** (${analysis.mentionedPath}). Processing your question…`
              : `Found endpoint **${analysis.matchedEndpoint.name}**. Processing your question…`,
            type: 'text'
          };

          setMessages((previous) => {
            if (hasSourceRelatedMessage(previous)) {
              return previous;
            }
            return [...previous, autoSelectMessage];
          });
          return;
        }

        // Use RAG semantic search if query is long enough
        if (initialQuery.trim().length >= MIN_QUERY_LENGTH) {
          // Show searching indicator
          setMessages((previous) => {
            if (hasSourceRelatedMessage(previous)) {
              return previous;
            }
            return [
              ...previous,
              {
                id: searchMessageId,
                role: 'assistant',
                type: 'source-search'
              }
            ];
          });

          // Perform semantic search
          const searchResults = await searchDataSources(initialQuery, { top_k: 5 });

          // Guard against state updates after unmount
          if (!isMounted) return;

          // Filter results by relevance threshold (>= 0.5)
          const { highRelevance } = categorizeResults(searchResults);

          if (highRelevance.length > 0) {
            // High relevance results found - show top 3
            const MAX_SOURCES_TO_SHOW = 3;
            const sourcesToShow = highRelevance.slice(0, MAX_SOURCES_TO_SHOW);

            const relevanceMessage: Message = {
              id: `source-selection-${String(Date.now())}`,
              role: 'assistant',
              content: `Based on your question, I found ${String(highRelevance.length)} highly relevant data source${highRelevance.length === 1 ? '' : 's'}:`,
              type: 'source-selection',
              sources: sourcesToShow
            };

            updateMessagesWithFilter(relevanceMessage, hasSourceSelectionMessage);
          } else {
            // No results meet the threshold - show AI assistant no-match message
            const noMatchMessage: Message = {
              id: `no-match-${String(Date.now())}`,
              role: 'assistant',
              type: 'no-match',
              searchQuery: initialQuery
            };

            updateMessagesWithFilter(noMatchMessage, hasSourceRelatedMessage);
          }
        } else {
          // Query too short for semantic search - use keyword analysis
          if (sources.length === 0) {
            const noSourcesMessage: Message = {
              id: `source-selection-${String(Date.now())}`,
              role: 'assistant',
              content:
                'No data sources are currently available. You can add external sources manually in the advanced configuration panel.',
              type: 'source-selection',
              sources: []
            };

            setMessages((previous) => {
              if (hasSourceSelectionMessage(previous)) {
                return previous;
              }
              return [...previous, noSourcesMessage];
            });
          } else {
            // Show top sources for short queries
            const MAX_SOURCES_TO_SHOW = 3;
            const sourcesToShow = sources.slice(0, MAX_SOURCES_TO_SHOW);

            const sourceSelectionMessage: Message = {
              id: `source-selection-${String(Date.now())}`,
              role: 'assistant',
              content: `Select data sources to get started (showing top ${String(sourcesToShow.length)} of ${String(sources.length)} available):`,
              type: 'source-selection',
              sources: sourcesToShow
            };

            setMessages((previous) => {
              if (hasSourceSelectionMessage(previous)) {
                return previous;
              }
              return [...previous, sourceSelectionMessage];
            });
          }
        }
      } catch (error) {
        // Guard against state updates after unmount
        if (!isMounted) return;

        console.error('Failed to load data sources:', error);

        // Add error message
        const errorMessage: Message = {
          id: `source-error-${String(Date.now())}`,
          role: 'assistant',
          content:
            'Unable to load data sources from the server. You can still add external sources manually using the advanced configuration panel.',
          type: 'text'
        };

        updateMessagesWithFilter(errorMessage, hasSourceRelatedMessage);
      }
    };

    void loadDataSources();

    // Cleanup: prevent state updates after unmount
    return () => {
      isMounted = false;
    };
  }, [initialQuery]);

  // Load available models from backend
  useEffect(() => {
    let isMounted = true;

    const loadModels = async () => {
      try {
        setIsLoadingModels(true);
        const models = await getChatModels(20); // Load up to 20 models

        // Guard against state updates after unmount
        if (!isMounted) return;

        setAvailableModels(models);

        // Auto-select the first model if available and not already selected
        setSelectedModel((current) => {
          if (current !== null) return current; // Already selected, don't override
          return models.length > 0 && models[0] ? models[0] : null;
        });
      } catch (error) {
        console.error('Failed to load models:', error);
      } finally {
        if (isMounted) {
          setIsLoadingModels(false);
        }
      }
    };

    void loadModels();

    // Cleanup: prevent state updates after unmount
    return () => {
      isMounted = false;
    };
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndReference.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Use available sources for the panel (now loaded from backend)
  const allSources = availableSources;

  // Memoized toggleSource using functional setState for stable reference
  // Uses Set for O(1) lookup and deletion performance
  const toggleSource = useCallback((id: string) => {
    setSelectedSources((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Memoized panel handlers for stable references
  const handleOpenPanel = useCallback(() => {
    setIsPanelOpen(true);
  }, []);

  const handleClosePanel = useCallback(() => {
    setIsPanelOpen(false);
  }, []);

  // Handler for adding sources by path - validates against available backend sources
  const handleAddCustomSource = useCallback(
    (path: string) => {
      // Validate the path format
      const validation = validateEndpointPath(path);
      if (!validation.isValid) {
        setCustomSourceError(validation.error ?? 'Invalid path format');
        return;
      }

      const normalizedPath = validation.normalizedPath ?? path.toLowerCase();

      // Check if the source exists in available sources from the backend
      const matchingSource = availableSources.find(
        (source) => source.full_path?.toLowerCase() === normalizedPath
      );

      if (!matchingSource) {
        setCustomSourceError('Data source not found. Please select from available sources.');
        return;
      }

      // Check if already selected
      if (selectedSources.has(matchingSource.id)) {
        setCustomSourceError('This source is already selected');
        return;
      }

      // Select the matching source
      toggleSource(matchingSource.id);
      setCustomSourceError(null);
    },
    [availableSources, selectedSources, toggleSource]
  );

  // Handler for removing custom sources
  const handleRemoveCustomSource = useCallback((path: string) => {
    setCustomSources((previous) => previous.filter((p) => p !== path));
  }, []);

  // Handler for clearing custom source error
  const handleClearCustomSourceError = useCallback(() => {
    setCustomSourceError(null);
  }, []);

  // Handler for mode change
  const handleModeChange = useCallback((isFactual: boolean) => {
    setIsFactualMode(isFactual);
  }, []);

  // Memoized input handler using functional setState
  const handleInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(event.target.value);
  }, []);

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!inputValue.trim() || isProcessing) return;

      // Validate model is selected
      if (!selectedModel) {
        setMessages((previous) => [
          ...previous,
          {
            id: Date.now().toString(),
            role: 'assistant',
            content: 'Please select a model before sending a message.',
            type: 'text'
          }
        ]);
        return;
      }

      // Validate user is authenticated
      if (!user?.email) {
        setMessages((previous) => [
          ...previous,
          {
            id: Date.now().toString(),
            role: 'assistant',
            content: 'Please log in to use the chat feature.',
            type: 'text'
          }
        ]);
        return;
      }

      const userMessage: Message = {
        id: Date.now().toString(),
        role: 'user',
        content: inputValue,
        type: 'text'
      };

      setMessages((previous) => [...previous, userMessage]);
      setInputValue('');
      setIsProcessing(true);

      // Create assistant message placeholder for streaming with thinking state
      const assistantMessageId = (Date.now() + 1).toString();
      setMessages((previous) => [
        ...previous,
        {
          id: assistantMessageId,
          role: 'assistant',
          content: '',
          type: 'text',
          isThinking: true
        }
      ]);

      // Build endpoint paths using "owner/slug" format
      // The SDK will resolve these to full endpoint references internally
      const modelPath = selectedModel.full_path;
      if (!modelPath) {
        setMessages((previous) =>
          updateMessageContent(
            previous,
            assistantMessageId,
            'Error: Selected model does not have a valid path configured.'
          )
        );
        setIsProcessing(false);
        return;
      }

      // Build data source paths from selected sources Set using Map for O(1) lookups
      const selectedSourcePaths = [...selectedSources]
        .map((id) => availableSourcesById.get(id)?.full_path)
        .filter((path): path is string => path !== undefined);

      // Combine with custom sources (already validated) and deduplicate
      const allDataSourcePaths = [...new Set([...selectedSourcePaths, ...customSources])];

      // Create abort controller for cancellation
      abortControllerReference.current = new AbortController();

      // Calculate total source count for status message
      const totalSourceCount = allDataSourcePaths.length;

      // Initialize processing status
      setProcessingStatus({
        phase: 'retrieving',
        message: totalSourceCount > 0 ? 'Starting...' : 'Preparing request...',
        completedSources: []
      });

      try {
        let accumulatedContent = '';

        // Use SDK for streaming - SDK resolves paths internally
        // Pass custom aggregator URL if user has configured one
        // Note: isFactualMode could be passed to SDK if/when supported
        for await (const event of syftClient.chat.stream({
          prompt: inputValue,
          model: modelPath,
          dataSources: allDataSourcePaths.length > 0 ? allDataSourcePaths : undefined,
          aggregatorUrl: user.aggregator_url ?? undefined,
          signal: abortControllerReference.current.signal
        })) {
          // Update processing status from event
          updateStatusFromEvent(event, setProcessingStatus);

          // Handle token content
          processStreamEvent(event, (content) => {
            accumulatedContent += content;
            setMessages((previous) =>
              updateMessageContent(previous, assistantMessageId, accumulatedContent)
            );
          });

          // Capture sources from done event
          if (event.type === 'done') {
            const doneEvent = event;
            if (Object.keys(doneEvent.sources).length > 0) {
              setMessages((previous) =>
                addAggregatorSources(previous, assistantMessageId, doneEvent.sources)
              );
            }
          }
        }

        // Refresh balance after successful chat completion (credits may have been consumed)
        triggerBalanceRefresh();
      } catch (error) {
        // Don't show error if it was aborted - clean up status
        if (error instanceof Error && error.name === 'AbortError') {
          setProcessingStatus(null);
          return;
        }

        const errorMessage = getChatErrorMessage(error);
        setMessages((previous) =>
          updateMessageContent(previous, assistantMessageId, `Error: ${errorMessage}`)
        );
        setProcessingStatus(null);
      } finally {
        setIsProcessing(false);
        abortControllerReference.current = null;
      }
    },
    [
      inputValue,
      isProcessing,
      selectedModel,
      user?.email,
      user?.aggregator_url,
      availableSourcesById,
      selectedSources,
      customSources
    ]
  );

  return (
    <div className='bg-card min-h-screen pb-32'>
      <AdvancedPanel
        isOpen={isPanelOpen}
        onClose={handleClosePanel}
        availableSources={allSources}
        selectedSourceIds={selectedSources}
        onToggleSource={toggleSource}
        customSources={customSources}
        onAddCustomSource={handleAddCustomSource}
        onRemoveCustomSource={handleRemoveCustomSource}
        customSourceError={customSourceError}
        onCustomSourceErrorClear={handleClearCustomSourceError}
        isFactualMode={isFactualMode}
        onModeChange={handleModeChange}
        selectedModel={selectedModel}
        availableModels={availableModels}
        onModelSelect={setSelectedModel}
        isLoadingModels={isLoadingModels}
      />

      {/* Model Selector - Fixed top left */}
      <div className='fixed top-4 left-24 z-40'>
        <ModelSelector
          selectedModel={selectedModel}
          onModelSelect={setSelectedModel}
          models={availableModels}
          isLoading={isLoadingModels}
        />
      </div>

      <div className='mx-auto max-w-4xl px-6 py-8 pt-16'>
        <div className='space-y-8'>
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'} max-w-full`}
              >
                {/* Status Indicator - shows real-time progress during processing */}
                {message.isThinking && !message.content && processingStatus ? (
                  <StatusIndicator status={processingStatus} />
                ) : null}

                {/* Text Content */}
                {message.content ? (
                  <div
                    className={`font-inter max-w-2xl rounded-2xl px-5 py-3 shadow-sm ${
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground rounded-br-none text-[15px] leading-relaxed'
                        : 'border-border bg-muted text-foreground rounded-bl-none border'
                    } `}
                  >
                    {message.role === 'assistant' ? (
                      <MarkdownMessage content={message.content} />
                    ) : (
                      message.content
                    )}
                  </div>
                ) : null}

                {/* Aggregator Sources Section - shows after assistant messages with sources */}
                {message.role === 'assistant' &&
                message.aggregatorSources &&
                Object.keys(message.aggregatorSources).length > 0 ? (
                  <div className='mt-2 w-full max-w-2xl'>
                    <SourcesSection sources={message.aggregatorSources} />
                  </div>
                ) : null}

                {/* Source Selection UI */}
                {message.type === 'source-selection' && message.sources ? (
                  <SourceSelector
                    sources={message.sources}
                    selectedIds={selectedSources}
                    onToggle={toggleSource}
                  />
                ) : null}

                {/* Search Loading Indicator */}
                {message.type === 'source-search' ? <SourceSearchLoader /> : null}

                {/* No Match Message - AI assistant response when no relevant endpoints found */}
                {message.type === 'no-match' ? (
                  <NoMatchMessage
                    query={message.searchQuery ?? ''}
                    onBrowseCatalog={() => {
                      window.open('/browse', '_blank');
                    }}
                    onAddCustomSource={handleOpenPanel}
                  />
                ) : null}
              </div>
            </div>
          ))}
          <div ref={messagesEndReference} />
        </div>
      </div>

      {/* Input Area */}
      <div className='border-border bg-card fixed bottom-0 left-0 z-40 w-full border-t p-4 pl-24'>
        <div className='mx-auto max-w-3xl'>
          <form onSubmit={handleSubmit} className='relative flex gap-3'>
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

            <div className='relative flex-1'>
              <label htmlFor='chat-followup-input' className='sr-only'>
                Ask a follow-up question
              </label>
              <input
                id='chat-followup-input'
                type='text'
                value={inputValue}
                onChange={handleInputChange}
                placeholder='Ask a follow-up question…'
                className='font-inter border-border bg-background placeholder:text-muted-foreground focus:border-foreground focus:ring-foreground/10 w-full rounded-xl border py-3.5 pr-12 pl-4 shadow-sm transition-colors transition-shadow focus:ring-2 focus:outline-none'
                autoComplete='off'
              />
              <button
                type='submit'
                disabled={!inputValue.trim() || isProcessing}
                className='bg-primary hover:bg-primary/90 absolute top-1/2 right-2 -translate-y-1/2 rounded-lg p-2 text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50'
                aria-label={isProcessing ? 'Processing…' : 'Send message'}
              >
                {isProcessing ? (
                  <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
                ) : (
                  <svg
                    width='16'
                    height='16'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    strokeWidth='2'
                    strokeLinecap='round'
                    strokeLinejoin='round'
                    aria-hidden='true'
                  >
                    <path d='M5 12h14M12 5l7 7-7 7' />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
