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

import { CostEstimationPanel } from './chat/cost-estimation-panel';
import { MarkdownMessage } from './chat/markdown-message';
import { ModelSelector } from './chat/model-selector';
import { SourcesSection } from './chat/sources-section';
import { StatusIndicator } from './chat/status-indicator';
import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

// Memoized AdvancedPanel to prevent unnecessary re-renders
const AdvancedPanel = memo(function AdvancedPanel({
  isOpen,
  onClose,
  sources,
  selectedIds,
  selectedModel
}: Readonly<{
  isOpen: boolean;
  onClose: () => void;
  sources: ChatSource[];
  selectedIds: Set<string>;
  selectedModel: ChatSource | null;
}>) {
  const activeSources = sources.filter((s) => selectedIds.has(s.id));
  const [isFactual, setIsFactual] = useState(true);
  const [customSourceInput, setCustomSourceInput] = useState('');
  const [customSources, setCustomSources] = useState<string[]>([]);

  const handleAddSource = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && customSourceInput.trim()) {
      setCustomSources((previous) => [...previous, customSourceInput.trim()]);
      setCustomSourceInput('');
    }
  };

  const removeCustomSource = (index: number) => {
    setCustomSources((previous) => previous.filter((_, index_) => index_ !== index));
  };

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
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className='fixed top-0 right-0 z-50 flex h-full w-[400px] flex-col border-l border-[#ecebef] bg-white shadow-2xl'
          >
            {/* Header */}
            <div className='flex items-center justify-between border-b border-[#ecebef] bg-[#fcfcfd] p-6'>
              <div className='flex items-center gap-3'>
                <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-[#272532]'>
                  <Settings2 className='h-5 w-5 text-white' />
                </div>
                <div>
                  <h2 className='font-rubik text-lg font-medium text-[#272532]'>
                    Execution Layout
                  </h2>
                  <p className='font-inter text-xs text-[#5e5a72]'>Pipeline configuration</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className='rounded-full p-2 transition-colors hover:bg-[#ecebef]'
              >
                <X className='h-5 w-5 text-[#b4b0bf]' />
              </button>
            </div>

            <div className='flex-1 space-y-4 overflow-y-auto p-6'>
              {/* Data Sources Section */}
              <div className='rounded-xl border border-green-200 bg-green-50/30 p-4'>
                <div className='mb-4 flex items-center justify-between'>
                  <div className='font-inter flex items-center gap-2 font-medium text-green-800'>
                    <Database className='h-4 w-4' />
                    <h3>Data Sources</h3>
                  </div>
                  <div className='flex items-center gap-2'>
                    <Label
                      htmlFor='mode-toggle'
                      className='font-inter cursor-pointer text-[10px] font-medium text-green-800'
                    >
                      {isFactual ? 'Factual' : 'Nuanced'}
                    </Label>
                    <Switch
                      id='mode-toggle'
                      checked={!isFactual}
                      onCheckedChange={(checked) => {
                        setIsFactual(!checked);
                      }}
                      className='h-4 w-8 data-[state=checked]:bg-purple-600 data-[state=unchecked]:bg-green-600'
                    />
                  </div>
                </div>

                <div className='space-y-3'>
                  {activeSources.length === 0 && customSources.length === 0 ? (
                    <div className='font-inter rounded-lg border border-dashed border-green-200 bg-white/50 py-8 text-center text-sm text-green-700/50'>
                      No sources selected
                    </div>
                  ) : (
                    <>
                      {activeSources.map((source) => {
                        const costs = getCostsFromSource(source);
                        const hasInputCost = costs.inputPerToken > 0;
                        const hasOutputCost = costs.outputPerToken > 0;
                        return (
                          <div
                            key={source.id}
                            className='rounded-lg border border-green-100 bg-white p-3 shadow-sm'
                          >
                            <div className='mb-3 flex items-center gap-3'>
                              <div className='font-inter flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-green-100 text-xs font-bold text-green-700'>
                                {source.name.slice(0, 2).toUpperCase()}
                              </div>
                              <span className='font-inter truncate text-sm font-medium text-[#272532]'>
                                {source.name}
                              </span>
                            </div>
                            <div className='flex flex-wrap gap-2'>
                              {hasInputCost || hasOutputCost ? (
                                <>
                                  {hasInputCost ? (
                                    <Badge
                                      variant='secondary'
                                      className='font-inter h-5 border-green-200 bg-green-50 px-2 text-[10px] font-medium text-green-700'
                                    >
                                      In: {formatCostPerUnit(costs.inputPerToken, 'token')}
                                    </Badge>
                                  ) : null}
                                  {hasOutputCost ? (
                                    <Badge
                                      variant='secondary'
                                      className='font-inter h-5 border-green-200 bg-green-50 px-2 text-[10px] font-medium text-green-700'
                                    >
                                      Out: {formatCostPerUnit(costs.outputPerToken, 'token')}
                                    </Badge>
                                  ) : null}
                                </>
                              ) : (
                                <Badge
                                  variant='secondary'
                                  className='font-inter h-5 border-gray-200 bg-gray-50 px-2 text-[10px] font-normal text-gray-500'
                                >
                                  No pricing
                                </Badge>
                              )}
                            </div>
                          </div>
                        );
                      })}
                      {customSources.map((source, index) => (
                        <div
                          key={index}
                          className='group relative rounded-lg border border-green-100 bg-white p-3 shadow-sm'
                        >
                          <button
                            onClick={() => {
                              removeCustomSource(index);
                            }}
                            className='absolute top-2 right-2 rounded p-1 text-red-500 opacity-0 group-hover:opacity-100 hover:bg-red-50'
                          >
                            <X className='h-3 w-3' />
                          </button>
                          <div className='mb-3 flex items-center gap-3'>
                            <div className='font-inter flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-green-100 text-xs font-bold text-green-700'>
                              EXT
                            </div>
                            <span className='font-inter truncate text-sm font-medium text-[#272532]'>
                              {source}
                            </span>
                          </div>
                          <Badge
                            variant='secondary'
                            className='font-inter h-5 border-gray-200 bg-gray-100 px-2 text-[10px] font-normal text-gray-600'
                          >
                            External Source
                          </Badge>
                        </div>
                      ))}
                    </>
                  )}

                  <div className='relative mt-2'>
                    <input
                      type='text'
                      value={customSourceInput}
                      onChange={(event) => {
                        setCustomSourceInput(event.target.value);
                      }}
                      onKeyDown={handleAddSource}
                      placeholder='Add external source (e.g. hf/dataset)...'
                      className='font-inter w-full rounded-lg border border-green-200 bg-white py-2 pr-8 pl-3 text-xs transition-all placeholder:text-green-700/40 focus:border-green-500 focus:ring-1 focus:ring-green-500/20 focus:outline-none'
                    />
                    <div className='font-inter pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-[10px] text-gray-400'>
                      ↵
                    </div>
                  </div>
                </div>
              </div>

              {/* Arrow */}
              <div className='flex justify-center text-[#b4b0bf]'>
                <ArrowDown className='h-5 w-5' />
              </div>

              {/* Synthesizers Section */}
              <div className='rounded-xl border border-purple-200 bg-purple-50/30 p-4'>
                <div className='mb-4 flex items-center justify-between'>
                  <div className='font-inter flex items-center gap-2 font-medium text-purple-800'>
                    <Cpu className='h-4 w-4' />
                    <h3>Model</h3>
                  </div>
                </div>

                <div className='space-y-3 rounded-lg border border-purple-100 bg-white p-3 shadow-sm'>
                  {selectedModel ? (
                    (() => {
                      const modelCosts = getCostsFromSource(selectedModel);
                      const hasInputCost = modelCosts.inputPerToken > 0;
                      const hasOutputCost = modelCosts.outputPerToken > 0;
                      return (
                        <>
                          <div className='flex items-center gap-3'>
                            <div className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-700'>
                              <Brain className='h-4 w-4' />
                            </div>
                            <div className='min-w-0 flex-1'>
                              <span className='font-inter block truncate text-sm font-medium text-[#272532]'>
                                {selectedModel.name}
                              </span>
                              {selectedModel.version ? (
                                <span className='font-inter text-xs text-[#5e5a72]'>
                                  v{selectedModel.version}
                                </span>
                              ) : null}
                            </div>
                          </div>
                          <div className='flex flex-wrap gap-2'>
                            {hasInputCost || hasOutputCost ? (
                              <>
                                {hasInputCost ? (
                                  <Badge
                                    variant='secondary'
                                    className='font-inter h-5 border-purple-200 bg-purple-50 px-2 text-[10px] font-medium text-purple-700'
                                  >
                                    In: {formatCostPerUnit(modelCosts.inputPerToken, 'token')}
                                  </Badge>
                                ) : null}
                                {hasOutputCost ? (
                                  <Badge
                                    variant='secondary'
                                    className='font-inter h-5 border-purple-200 bg-purple-50 px-2 text-[10px] font-medium text-purple-700'
                                  >
                                    Out: {formatCostPerUnit(modelCosts.outputPerToken, 'token')}
                                  </Badge>
                                ) : null}
                              </>
                            ) : (
                              <Badge
                                variant='secondary'
                                className='font-inter h-5 border-gray-200 bg-gray-50 px-2 text-[10px] font-normal text-gray-500'
                              >
                                No pricing
                              </Badge>
                            )}
                          </div>
                        </>
                      );
                    })()
                  ) : (
                    <div className='font-inter rounded-lg border border-dashed border-purple-200 bg-white/50 py-6 text-center text-sm text-purple-700/50'>
                      No model selected
                    </div>
                  )}

                  <div className='font-inter mt-2 flex items-start gap-2 border-t border-purple-50 pt-2 text-xs text-gray-500'>
                    <Info className='mt-0.5 h-3 w-3 shrink-0' />
                    {isFactual
                      ? 'Strict mode enabled. Results will be grounded in retrieved data only.'
                      : 'Nuanced mode enabled. Model can infer and synthesize broader context.'}
                  </div>
                </div>
              </div>

              {/* Arrow */}
              <div className='flex flex-col items-center gap-1 text-[#b4b0bf]'>
                <ArrowDown className='h-5 w-5' />
                <span className='font-inter text-[10px] font-medium'>Process & Combine</span>
              </div>

              {/* Cost Estimation Section */}
              <CostEstimationPanel model={selectedModel} dataSources={activeSources} />
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
    <div className='my-4 w-full max-w-3xl space-y-3'>
      {sources.map((source) => {
        const isSelected = selectedIds.has(source.id);

        let statusColor = 'bg-green-500';
        if (source.status === 'warning') statusColor = 'bg-yellow-500';
        if (source.status === 'inactive') statusColor = 'bg-red-500';

        return (
          <div
            key={source.id}
            onClick={() => {
              onToggle(source.id);
            }}
            className={`group relative flex cursor-pointer items-start gap-4 rounded-xl border p-4 transition-all ${isSelected ? 'border-[#6976ae] bg-[#f7f6f9]' : 'border-[#ecebef] bg-white hover:border-[#cfcdd6]'} `}
          >
            <div className='min-w-0 flex-1'>
              {/* Header */}
              <div className='mb-1 flex flex-wrap items-center gap-2'>
                <span
                  className={`font-inter font-medium transition-colors ${
                    isSelected ? 'text-[#272532]' : 'text-[#272532] group-hover:text-[#6976ae]'
                  }`}
                >
                  {source.name}
                </span>
                {source.tags.slice(0, 2).map((tag) => (
                  <span
                    key={tag}
                    className='font-inter rounded-md bg-[#f1f0f4] px-2 py-0.5 text-xs text-[#5e5a72]'
                  >
                    {tag}
                  </span>
                ))}
                {source.tags.length > 2 ? (
                  <span className='font-inter rounded-md bg-[#f1f0f4] px-2 py-0.5 text-xs text-[#5e5a72]'>
                    +{source.tags.length - 2}
                  </span>
                ) : null}
              </div>

              {/* Description with Status Dot */}
              <div className='mb-2 flex items-start gap-2'>
                <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusColor}`} />
                <p className='font-inter text-sm leading-relaxed text-[#5e5a72]'>
                  {source.description}
                </p>
              </div>

              {/* Footer */}
              <div className='font-inter flex items-center gap-1.5 text-xs text-[#b4b0bf]'>
                <Clock className='h-3.5 w-3.5' />
                <span>Updated {source.updated}</span>
              </div>
            </div>

            {/* Checkbox */}
            <div
              className={`mt-1 flex h-6 w-6 items-center justify-center rounded border transition-colors ${isSelected ? 'border-[#272532] bg-[#272532]' : 'border-[#cfcdd6] bg-white group-hover:border-[#b4b0bf]'} `}
            >
              {isSelected && <Check className='h-3.5 w-3.5 text-white' />}
            </div>
          </div>
        );
      })}
    </div>
  );
});

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  type?: 'text' | 'source-selection';
  sources?: ChatSource[];
  isThinking?: boolean;
  /** Sources from aggregator response (document titles -> endpoint slug & content) */
  aggregatorSources?: SourcesData;
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
          message: 'Preparing request...',
          completedSources: []
        });
      } else {
        setProcessingStatus({
          phase: 'retrieving',
          message: `Searching ${String(event.sourceCount)} data ${event.sourceCount === 1 ? 'source' : 'sources'}...`,
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
          message: `Retrieved from ${String(newCompleted)}/${String(total)} ${total === 1 ? 'source' : 'sources'}...`,
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
        message: 'Generating response...',
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
          message: 'Writing response...'
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

// Helper to check if we already have a source-related message (error or source-selection)
function hasSourceRelatedMessage(messages: Message[]): boolean {
  return messages.some(
    (m) => m.type === 'source-selection' || (m.role === 'assistant' && m.id.startsWith('source-'))
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

  // Build Map for O(1) source lookups by ID (avoids repeated .find() calls)
  const availableSourcesById = useMemo(
    () => new Map(availableSources.map((source) => [source.id, source])),
    [availableSources]
  );

  // Load real data sources from backend and analyze query for relevance
  useEffect(() => {
    let isMounted = true;

    const loadDataSources = async () => {
      try {
        const sources = await getChatDataSources(100); // Load up to 100 endpoints for comprehensive search

        // Guard against state updates after unmount
        if (!isMounted) return;

        setAvailableSources(sources);

        // Analyze the initial query to determine the best action
        const analysis = analyzeQueryForSources(initialQuery, sources);

        if (analysis.action === 'auto-select' && analysis.matchedEndpoint) {
          // Endpoint was explicitly mentioned - auto-select and proceed
          setSelectedSources(new Set([analysis.matchedEndpoint.id]));

          // Add a message indicating auto-selection
          const autoSelectMessage: Message = {
            id: `auto-select-${String(Date.now())}`,
            role: 'assistant',
            content: analysis.mentionedPath
              ? `Found endpoint **${analysis.matchedEndpoint.name}** (${analysis.mentionedPath}). Processing your question...`
              : `Found endpoint **${analysis.matchedEndpoint.name}**. Processing your question...`,
            type: 'text'
          };

          setMessages((previous) => {
            if (hasSourceRelatedMessage(previous)) {
              return previous;
            }
            return [...previous, autoSelectMessage];
          });
        } else if (sources.length === 0) {
          // No sources available
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
        } else if (analysis.relevantSources.length === 0) {
          // Sources exist but none are relevant - show top sources as fallback
          const MAX_SOURCES_TO_SHOW = 3;
          const sourcesToShow = sources.slice(0, MAX_SOURCES_TO_SHOW);

          const noRelevantMessage: Message = {
            id: `source-selection-${String(Date.now())}`,
            role: 'assistant',
            content: `No sources matched your query directly. Here are the top ${String(sourcesToShow.length)} popular sources (${String(sources.length)} total available):`,
            type: 'source-selection',
            sources: sourcesToShow
          };

          setMessages((previous) => {
            if (hasSourceSelectionMessage(previous)) {
              return previous;
            }
            return [...previous, noRelevantMessage];
          });
        } else {
          // Show relevant sources (top 3)
          const MAX_SOURCES_TO_SHOW = 3;
          const relevantSources = analysis.relevantSources;
          const sourcesToShow = relevantSources.slice(0, MAX_SOURCES_TO_SHOW);
          const isFiltered =
            analysis.action === 'show-relevant' && relevantSources.length < sources.length;

          const messageContent = isFiltered
            ? `Based on your question, here are the top ${String(sourcesToShow.length)} most relevant data sources (${String(relevantSources.length)} matched, ${String(sources.length)} total):`
            : `Select data sources to get started (showing top ${String(sourcesToShow.length)} of ${String(sources.length)} available):`;

          const sourceSelectionMessage: Message = {
            id: `source-selection-${String(Date.now())}`,
            role: 'assistant',
            content: messageContent,
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
      } catch (error) {
        // Guard against state updates after unmount
        if (!isMounted) return;

        console.error('Failed to load data sources:', error);

        // Add error message - ATOMIC check to prevent duplicates
        const errorMessageId = `source-error-${String(Date.now())}`;
        const errorMessage: Message = {
          id: errorMessageId,
          role: 'assistant',
          content:
            'Unable to load data sources from the server. You can still add external sources manually using the advanced configuration panel.',
          type: 'text'
        };

        setMessages((previous) => {
          if (hasSourceRelatedMessage(previous)) {
            return previous;
          }
          return [...previous, errorMessage];
        });
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
      const dataSourcePaths = [...selectedSources]
        .map((id) => availableSourcesById.get(id)?.full_path)
        .filter((path): path is string => path !== undefined);

      // Create abort controller for cancellation
      abortControllerReference.current = new AbortController();

      // Initialize processing status
      setProcessingStatus({
        phase: 'retrieving',
        message: 'Starting...',
        completedSources: []
      });

      try {
        let accumulatedContent = '';

        // Use SDK for streaming - SDK resolves paths internally
        for await (const event of syftClient.chat.stream({
          prompt: inputValue,
          model: modelPath,
          dataSources: dataSourcePaths.length > 0 ? dataSourcePaths : undefined,
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
    [inputValue, isProcessing, selectedModel, user?.email, availableSourcesById, selectedSources]
  );

  return (
    <div className='min-h-screen bg-white pb-32'>
      <AdvancedPanel
        isOpen={isPanelOpen}
        onClose={handleClosePanel}
        sources={allSources}
        selectedIds={selectedSources}
        selectedModel={selectedModel}
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
                        ? 'rounded-br-none bg-[#272532] text-[15px] leading-relaxed text-white'
                        : 'rounded-bl-none border border-[#ecebef] bg-[#f7f6f9] text-[#272532]'
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
              </div>
            </div>
          ))}
          <div ref={messagesEndReference} />
        </div>
      </div>

      {/* Input Area */}
      <div className='fixed bottom-0 left-0 z-40 w-full border-t border-[#ecebef] bg-white p-4 pl-24'>
        <div className='mx-auto max-w-3xl'>
          <form onSubmit={handleSubmit} className='relative flex gap-3'>
            <button
              type='button'
              onClick={handleOpenPanel}
              className='group flex items-center justify-center rounded-xl border border-[#ecebef] bg-[#fcfcfd] p-3.5 text-[#5e5a72] transition-colors hover:bg-[#f1f0f4] hover:text-[#272532]'
              title='Open Advanced Configuration'
            >
              <Settings2 className='h-5 w-5 transition-transform duration-500 group-hover:rotate-45' />
            </button>

            <div className='relative flex-1'>
              <input
                type='text'
                value={inputValue}
                onChange={handleInputChange}
                placeholder='Ask a follow-up question...'
                className='font-inter w-full rounded-xl border border-[#ecebef] bg-[#fcfcfd] py-3.5 pr-12 pl-4 shadow-sm transition-all placeholder:text-[#b4b0bf] focus:border-[#272532] focus:ring-2 focus:ring-[#272532]/10 focus:outline-none'
              />
              <button
                type='submit'
                disabled={!inputValue.trim() || isProcessing}
                className='absolute top-1/2 right-2 -translate-y-1/2 rounded-lg bg-[#272532] p-2 text-white transition-colors hover:bg-[#353243] disabled:cursor-not-allowed disabled:opacity-50'
              >
                {isProcessing ? (
                  <Loader2 className='h-4 w-4 animate-spin' />
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
