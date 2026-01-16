import React, { useEffect, useRef, useState } from 'react';

import type { ChatStreamEvent } from '@/lib/sdk-client';
import type { ChatSource } from '@/lib/types';
import type { ProcessingStatus } from './chat/status-indicator';

import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowDown,
  Brain,
  Check,
  Clock,
  Cpu,
  Database,
  Info,
  Loader2,
  Settings2,
  X
} from 'lucide-react';

import { useAuth } from '@/context/auth-context';
import { triggerBalanceRefresh } from '@/hooks/use-accounting-api';
import { formatCostPerUnit, getCostsFromSource } from '@/lib/cost-utils';
import { getChatDataSources, getChatModels } from '@/lib/endpoint-utils';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError,
  syftClient
} from '@/lib/sdk-client';

import { CostEstimationPanel } from './chat/cost-estimation-panel';
import { MarkdownMessage } from './chat/markdown-message';
import { ModelSelector } from './chat/model-selector';
import { StatusIndicator } from './chat/status-indicator';
import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

function AdvancedPanel({
  isOpen,
  onClose,
  sources,
  selectedIds,
  selectedModel
}: Readonly<{
  isOpen: boolean;
  onClose: () => void;
  sources: ChatSource[];
  selectedIds: string[];
  selectedModel: ChatSource | null;
}>) {
  const activeSources = sources.filter((s) => selectedIds.includes(s.id));
  const [isFactual, setIsFactual] = useState(true);
  const [customSourceInput, setCustomSourceInput] = useState('');
  const [customSources, setCustomSources] = useState<string[]>([]);

  const handleAddSource = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && customSourceInput.trim()) {
      setCustomSources([...customSources, customSourceInput.trim()]);
      setCustomSourceInput('');
    }
  };

  const removeCustomSource = (index: number) => {
    setCustomSources(customSources.filter((_, index_) => index_ !== index));
  };

  return (
    <AnimatePresence>
      {isOpen && (
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
                                  {hasInputCost && (
                                    <Badge
                                      variant='secondary'
                                      className='font-inter h-5 border-green-200 bg-green-50 px-2 text-[10px] font-medium text-green-700'
                                    >
                                      In: {formatCostPerUnit(costs.inputPerToken, 'token')}
                                    </Badge>
                                  )}
                                  {hasOutputCost && (
                                    <Badge
                                      variant='secondary'
                                      className='font-inter h-5 border-green-200 bg-green-50 px-2 text-[10px] font-medium text-green-700'
                                    >
                                      Out: {formatCostPerUnit(costs.outputPerToken, 'token')}
                                    </Badge>
                                  )}
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
                              {selectedModel.version && (
                                <span className='font-inter text-xs text-[#5e5a72]'>
                                  v{selectedModel.version}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className='flex flex-wrap gap-2'>
                            {hasInputCost || hasOutputCost ? (
                              <>
                                {hasInputCost && (
                                  <Badge
                                    variant='secondary'
                                    className='font-inter h-5 border-purple-200 bg-purple-50 px-2 text-[10px] font-medium text-purple-700'
                                  >
                                    In: {formatCostPerUnit(modelCosts.inputPerToken, 'token')}
                                  </Badge>
                                )}
                                {hasOutputCost && (
                                  <Badge
                                    variant='secondary'
                                    className='font-inter h-5 border-purple-200 bg-purple-50 px-2 text-[10px] font-medium text-purple-700'
                                  >
                                    Out: {formatCostPerUnit(modelCosts.outputPerToken, 'token')}
                                  </Badge>
                                )}
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
      )}
    </AnimatePresence>
  );
}

interface SourceSelectorProperties {
  sources: ChatSource[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}

function SourceSelector({ sources, selectedIds, onToggle }: Readonly<SourceSelectorProperties>) {
  return (
    <div className='my-4 w-full max-w-3xl space-y-3'>
      {sources.map((source) => {
        const isSelected = selectedIds.includes(source.id);

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
                {source.tags.length > 2 && (
                  <span className='font-inter rounded-md bg-[#f1f0f4] px-2 py-0.5 text-xs text-[#5e5a72]'>
                    +{source.tags.length - 2}
                  </span>
                )}
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
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content?: string;
  type?: 'text' | 'source-selection';
  sources?: ChatSource[];
  isThinking?: boolean;
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
          message: `Searching ${event.sourceCount} data ${event.sourceCount === 1 ? 'source' : 'sources'}...`,
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
        const newDocsFound = (previous.retrieval?.documentsFound ?? 0) + event.documentsRetrieved;
        const total = previous.retrieval?.total ?? 1;

        return {
          ...previous,
          message: `Retrieved from ${newCompleted}/${total} ${total === 1 ? 'source' : 'sources'}...`,
          retrieval: {
            completed: newCompleted,
            total,
            documentsFound: newDocsFound
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
        return {
          ...previous,
          message:
            documentCount > 0
              ? `Found ${documentCount} relevant ${documentCount === 1 ? 'document' : 'documents'}`
              : 'No relevant documents found',
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

export function ChatView({ initialQuery }: Readonly<ChatViewProperties>) {
  const { user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([
    { id: '1', role: 'user', content: initialQuery, type: 'text' }
  ]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
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

  // Load real data sources from backend
  useEffect(() => {
    let isMounted = true;

    const loadDataSources = async () => {
      try {
        const sources = await getChatDataSources(10); // Load 10 endpoints

        // Guard against state updates after unmount
        if (!isMounted) return;

        setAvailableSources(sources);

        // Add assistant message with real sources - ATOMIC check to prevent duplicates
        const messageId = `source-selection-${String(Date.now())}`;
        const assistantMessage: Message = {
          id: messageId,
          role: 'assistant',
          content:
            sources.length > 0
              ? 'Select data sources to get started with your analysis:'
              : 'No data sources are currently available. You can add external sources manually in the advanced configuration panel.',
          type: 'source-selection',
          sources: sources
        };

        setMessages((previous) => {
          if (hasSourceSelectionMessage(previous)) {
            return previous;
          }
          return [...previous, assistantMessage];
        });
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
  }, []);

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

  const toggleSource = (id: string) => {
    setSelectedSources((previous) =>
      previous.includes(id) ? previous.filter((index) => index !== id) : [...previous, id]
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
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

    // Build data source paths
    const dataSourcePaths = selectedSources
      .map((id) => {
        const source = availableSources.find((s) => s.id === id);
        return source?.full_path;
      })
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
      }

      // Refresh balance after successful chat completion (credits may have been consumed)
      triggerBalanceRefresh();
    } catch (error) {
      // Handle SDK-specific errors
      let errorMessage = 'An unexpected error occurred';

      if (error instanceof Error && error.name === 'AbortError') {
        // Don't show error if it was aborted - clean up status
        setProcessingStatus(null);
        return;
      }

      if (error instanceof AuthenticationError) {
        errorMessage = 'Authentication required. Please log in again.';
      } else if (error instanceof AggregatorError) {
        errorMessage = `Chat service error: ${error.message}`;
      } else if (error instanceof EndpointResolutionError) {
        errorMessage = `Could not resolve endpoint: ${error.message}`;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      setMessages((previous) =>
        updateMessageContent(previous, assistantMessageId, `Error: ${errorMessage}`)
      );
      setProcessingStatus(null);
    } finally {
      setIsProcessing(false);
      abortControllerReference.current = null;
    }
  };

  return (
    <div className='min-h-screen bg-white pb-32'>
      <AdvancedPanel
        isOpen={isPanelOpen}
        onClose={() => {
          setIsPanelOpen(false);
        }}
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
                {message.isThinking && !message.content && processingStatus && (
                  <StatusIndicator status={processingStatus} />
                )}

                {/* Text Content */}
                {message.content && (
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
                )}

                {/* Source Selection UI */}
                {message.type === 'source-selection' && message.sources && (
                  <SourceSelector
                    sources={message.sources}
                    selectedIds={selectedSources}
                    onToggle={toggleSource}
                  />
                )}
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
              onClick={() => {
                setIsPanelOpen(true);
              }}
              className='group flex items-center justify-center rounded-xl border border-[#ecebef] bg-[#fcfcfd] p-3.5 text-[#5e5a72] transition-colors hover:bg-[#f1f0f4] hover:text-[#272532]'
              title='Open Advanced Configuration'
            >
              <Settings2 className='h-5 w-5 transition-transform duration-500 group-hover:rotate-45' />
            </button>

            <div className='relative flex-1'>
              <input
                type='text'
                value={inputValue}
                onChange={(event) => {
                  setInputValue(event.target.value);
                }}
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
