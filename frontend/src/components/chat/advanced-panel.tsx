/**
 * AdvancedPanel Component
 *
 * Slide-out panel for configuring the execution pipeline.
 * Allows users to manage data sources, select models, toggle reasoning modes,
 * and view cost estimation.
 */
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import ArrowDown from 'lucide-react/dist/esm/icons/arrow-down';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Settings2 from 'lucide-react/dist/esm/icons/settings-2';
import X from 'lucide-react/dist/esm/icons/x';

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { getCostsFromSource } from '@/lib/cost-utils';
import { filterSourcesForAutocomplete } from '@/lib/validation';

import { CostEstimationPanel } from './cost-estimation-panel';
import { ModelDisplay } from './model-display';
import { ModelSelector } from './model-selector';
import { SourceCard } from './source-card';
import { SuggestionItem } from './suggestion-item';

// =============================================================================
// Types
// =============================================================================

export interface AdvancedPanelProps {
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

// =============================================================================
// Component
// =============================================================================

export const AdvancedPanel = memo(function AdvancedPanel({
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
