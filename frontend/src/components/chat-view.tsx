import React, { useEffect, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown, Brain, Check, Clock, Cpu, Database, Info, Settings2, X } from 'lucide-react';

import { getChatDataSources } from '@/lib/endpoint-api';

import { Badge } from './ui/badge';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Switch } from './ui/switch';

function AdvancedPanel({
  isOpen,
  onClose,
  sources,
  selectedIds
}: Readonly<{
  isOpen: boolean;
  onClose: () => void;
  sources: ChatSource[];
  selectedIds: string[];
}>) {
  const activeSources = sources.filter((s) => selectedIds.includes(s.id));
  const [model, setModel] = useState('syft-1.5-turbo');
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
                      {activeSources.map((source) => (
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
                            <Badge
                              variant='secondary'
                              className='font-inter h-5 cursor-pointer border-blue-100 bg-blue-50 px-2 text-[10px] font-normal text-blue-700 hover:bg-blue-100'
                            >
                              Top-K: 5
                            </Badge>
                            <Badge
                              variant='secondary'
                              className='font-inter h-5 cursor-pointer border-blue-100 bg-blue-50 px-2 text-[10px] font-normal text-blue-700 hover:bg-blue-100'
                            >
                              Tokens: 500
                            </Badge>
                            <Badge
                              variant='secondary'
                              className='font-inter h-5 cursor-pointer border-blue-100 bg-blue-50 px-2 text-[10px] font-normal text-blue-700 hover:bg-blue-100'
                            >
                              Temp: 0.7
                            </Badge>
                          </div>
                        </div>
                      ))}
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
                  <div className='flex items-center gap-3'>
                    <div className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-700'>
                      <Brain className='h-4 w-4' />
                    </div>
                    <Select value={model} onValueChange={setModel}>
                      <SelectTrigger className='font-inter h-8 border-transparent px-2 text-sm hover:bg-gray-50 focus:ring-0'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='syft-1.5-turbo'>syft-1.5-turbo</SelectItem>
                        <SelectItem value='syft-2.0-reasoning'>syft-2.0-reasoning</SelectItem>
                        <SelectItem value='claude-3.5-sonnet'>claude-3.5-sonnet</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className='flex gap-2'>
                    <Badge
                      variant='secondary'
                      className='font-inter h-5 cursor-pointer border-purple-100 bg-purple-50 px-2 text-[10px] font-normal text-purple-700 hover:bg-purple-100'
                    >
                      Tokens: 1000
                    </Badge>
                    <Badge
                      variant='secondary'
                      className='font-inter h-5 cursor-pointer border-purple-100 bg-purple-50 px-2 text-[10px] font-normal text-purple-700 hover:bg-purple-100'
                    >
                      Temp: {isFactual ? '0.1' : '0.7'}
                    </Badge>
                  </div>

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

              {/* Final Response Section */}
              <div className='rounded-xl border border-blue-200 bg-blue-50/30 p-4'>
                <div className='mb-3 flex items-center justify-between'>
                  <span className='font-inter font-medium text-blue-900'>Final Response</span>
                </div>
                <div className='space-y-2 text-sm'>
                  <div className='font-inter flex justify-between text-blue-800/80'>
                    <span>Mode:</span>
                    <span className='font-medium text-[#272532]'>auto</span>
                  </div>
                  <div className='font-inter flex justify-between text-blue-800/80'>
                    <div className='flex items-center gap-1'>
                      <span>Total Price:</span>
                    </div>
                    <span className='font-medium text-green-600'>$0.095</span>
                  </div>
                  <div className='font-inter mt-3 flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-100/50 p-2.5 text-[10px] text-blue-700/60'>
                    <Info className='mt-0.5 h-3 w-3 shrink-0' />
                    Estimated cost per request based on selected data sources and AI model token
                    usage.
                  </div>
                </div>
              </div>
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
                <span className='font-inter rounded-md bg-[#f1f0f4] px-2 py-0.5 text-xs text-[#5e5a72]'>
                  {source.tag}
                </span>
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
}

interface ChatViewProperties {
  initialQuery: string;
}

export function ChatView({ initialQuery }: Readonly<ChatViewProperties>) {
  const [messages, setMessages] = useState<Message[]>([
    { id: '1', role: 'user', content: initialQuery, type: 'text' }
  ]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [availableSources, setAvailableSources] = useState<ChatSource[]>([]);
  const [isLoadingSources, setIsLoadingSources] = useState(true);
  const messagesEndReference = useRef<HTMLDivElement>(null);

  // Load real data sources from backend
  useEffect(() => {
    const loadDataSources = async () => {
      try {
        setIsLoadingSources(true);
        const sources = await getChatDataSources(10); // Load 10 endpoints
        setAvailableSources(sources);

        // Add assistant message with real sources
        const assistantMessage: Message = {
          id: '2',
          role: 'assistant',
          content:
            sources.length > 0
              ? 'Select data sources to get started with your analysis:'
              : 'No data sources are currently available. You can add external sources manually in the advanced configuration panel.',
          type: 'source-selection',
          sources: sources
        };

        setMessages((previous) => [...previous, assistantMessage]);
      } catch (error) {
        console.error('Failed to load data sources:', error);

        // Add error message
        const errorMessage: Message = {
          id: '2',
          role: 'assistant',
          content:
            'Unable to load data sources from the server. You can still add external sources manually using the advanced configuration panel.',
          type: 'text'
        };

        setMessages((previous) => [...previous, errorMessage]);
      } finally {
        setIsLoadingSources(false);
      }
    };

    loadDataSources();
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

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!inputValue.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      type: 'text'
    };

    setMessages((previous) => [...previous, newMessage]);
    setInputValue('');

    // Mock response
    setTimeout(() => {
      setMessages((previous) => [
        ...previous,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `I can help you analyze data from your selected sources: ${
            selectedSources.length > 0 ? selectedSources.join(', ') : 'none selected'
          }. What specific insights are you looking for?`,
          type: 'text'
        }
      ]);
    }, 1000);
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
      />

      <div className='mx-auto max-w-4xl px-6 py-8'>
        <div className='space-y-8'>
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'} max-w-full`}
              >
                {/* Text Content */}
                {message.content && (
                  <div
                    className={`font-inter max-w-2xl rounded-2xl px-5 py-3 text-[15px] leading-relaxed shadow-sm ${
                      message.role === 'user'
                        ? 'rounded-br-none bg-[#272532] text-white'
                        : 'rounded-bl-none border border-[#ecebef] bg-[#f7f6f9] text-[#272532]'
                    } `}
                  >
                    {message.content}
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
                disabled={!inputValue.trim()}
                className='absolute top-1/2 right-2 -translate-y-1/2 rounded-lg bg-[#272532] p-2 text-white transition-colors hover:bg-[#353243] disabled:cursor-not-allowed disabled:opacity-50'
              >
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
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
