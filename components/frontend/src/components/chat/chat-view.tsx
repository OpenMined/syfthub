/**
 * ChatView Component
 *
 * Main chat interface for querying data sources.
 * Uses shared hooks for model management, data sources, and workflow execution.
 * Orchestrates sub-components: ModelSelector, AddSourcesModal, etc.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatHistoryMessage, WorkflowResult } from '@/hooks/use-chat-workflow';
import type { PendingSubscription } from '@/hooks/use-xendit-precheck';
import type { SearchableChatSource } from '@/lib/search-service';
import type { ChatSource } from '@/lib/types';
import type { SourcesData } from './sources-section';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';

import { OnboardingWelcomeBanner } from '@/components/onboarding';
import { ChatContainerContent, ChatContainerRoot } from '@/components/prompt-kit/chat-container';
import {
  Message,
  MessageAction,
  MessageActions,
  MessageAvatar,
  MessageContent
} from '@/components/prompt-kit/message';
import { ScrollButton } from '@/components/prompt-kit/scroll-button';
import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import { useDataSources } from '@/hooks/use-data-sources';
import { useModels } from '@/hooks/use-models';
import { useSuggestedSources } from '@/hooks/use-suggested-sources';
import { useXenditPrecheck } from '@/hooks/use-xendit-precheck';
import { useContextSelectionStore } from '@/stores/context-selection-store';
import { useOnboardingStore } from '@/stores/onboarding-store';

import { AddSourcesModal } from './add-sources-modal';
import { MarkdownMessage } from './markdown-message';
import { PaymentGate } from './payment-gate';
import { SearchInput } from './search-input';
import { SourcesSection } from './sources-section';
import { StatusIndicator } from './status-indicator';
import { SuggestedSources } from './suggested-sources';

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
  /** Position-annotated response for citation highlighting (from done event). */
  annotatedResponse?: string;
}

export interface ChatViewProperties {
  /** Initial query from navigation (e.g., from home page search) */
  initialQuery: string;
  /** Optional pre-selected model from navigation */
  initialModel?: ChatSource | null;
  /** Optional initial result if workflow was completed before navigation */
  initialResult?: WorkflowResult | null;
  /** Optional pre-selected data sources from browse page "Add to context" flow */
  contextSources?: ChatSource[];
}

// =============================================================================
// Component
// =============================================================================

export function ChatView({
  initialQuery,
  initialModel,
  initialResult,
  contextSources
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
  const { sources, sourcesById, isLoading: isLoadingDataSources } = useDataSources();
  const showSourcesStep = useOnboardingStore((s) => s.showSourcesStep);
  const showQueryInputStep = useOnboardingStore((s) => s.showQueryInputStep);

  const contextStore = useContextSelectionStore();
  const selectedSources = useContextSelectionStore((s) => s.selectedSources);

  // Welcome banner: shown on first arrival at /chat for users who haven't
  // completed onboarding and aren't already mid-tour.
  const [showWelcomeBanner, setShowWelcomeBanner] = useState(false);
  useEffect(() => {
    const { hasCompletedOnboarding, currentStep } = useOnboardingStore.getState();
    if (!hasCompletedOnboarding && currentStep === null) {
      setShowWelcomeBanner(true);
    }
  }, []);

  // Source modal state
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);

  // Suggested sources: track input text and compute suggestions
  const [inputText, setInputText] = useState('');
  const selectedSourceIds = useMemo(
    () => new Set<string>(selectedSources.keys()),
    [selectedSources]
  );

  // Stable ID shared with the seeded initial-query message and the auto-trigger
  // effect, so onComplete recognises the pre-existing bubble and won't duplicate.
  const initialQueryMessageIdReference = useRef<string | null>(
    initialQuery && !initialResult ? crypto.randomUUID() : null
  );

  // Local state for messages and UI
  const [messages, setMessages] = useState<Message[]>(() => {
    // Initialize with initial query as first message if provided
    if (initialResult) {
      // If we have an initial result from Hero, add both user and assistant messages
      return [
        {
          id: crypto.randomUUID(),
          role: 'user' as const,
          content: initialResult.query,
          type: 'text' as const
        },
        {
          id: crypto.randomUUID(),
          role: 'assistant' as const,
          content: initialResult.content,
          type: 'text' as const,
          aggregatorSources: initialResult.sources,
          annotatedResponse: initialResult.annotatedResponse
        }
      ];
    }
    if (initialQuery) {
      return [
        {
          // Re-use the ID from initialQueryMessageIdReference so pendingMessageIdReference can be set
          // to this same ID in the auto-trigger useEffect, preventing a duplicate message.
          id: initialQueryMessageIdReference.current ?? crypto.randomUUID(),
          role: 'user' as const,
          content: initialQuery,
          type: 'text' as const
        }
      ];
    }
    return [];
  });

  const pendingMessageIdReference = useRef<string | null>(null);
  const lastQueryReference = useRef<string>('');

  // Copy-to-clipboard state for assistant messages
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const handleCopy = useCallback((content: string, messageId: string) => {
    void navigator.clipboard.writeText(content);
    setCopiedId(messageId);
    setTimeout(() => {
      setCopiedId((previous) => (previous === messageId ? null : previous));
    }, 2000);
  }, []);

  // Use workflow hook
  const workflow = useChatWorkflow({
    model: selectedModel,
    dataSources: sources,
    dataSourcesById: sourcesById,
    contextSources: contextSources ?? contextStore.getSourcesArray(),
    onComplete: (result) => {
      showSourcesStep();
      setMessages((previous) => {
        // User message was already added optimistically in handleSubmit
        const hasUserMessage =
          pendingMessageIdReference.current !== null &&
          previous.some((m) => m.id === pendingMessageIdReference.current);

        const base = hasUserMessage
          ? previous
          : [
              ...previous,
              {
                id: crypto.randomUUID(),
                role: 'user' as const,
                content: result.query,
                type: 'text' as const
              }
            ];

        pendingMessageIdReference.current = null;

        return [
          ...base,
          {
            id: crypto.randomUUID(),
            role: 'assistant' as const,
            content: result.content,
            type: 'text' as const,
            aggregatorSources: result.sources,
            annotatedResponse: result.annotatedResponse
          }
        ];
      });
    }
  });

  // One-shot latch so the home-page initial query doesn't refire after the
  // gate modal opens (workflow stays in 'idle' until submitQuery actually runs).
  const autoTriggeredReference = useRef(false);

  // Determine if workflow is in a blocking state
  const isWorkflowActive =
    workflow.phase !== 'idle' && workflow.phase !== 'complete' && workflow.phase !== 'error';

  // Suggested data sources based on current input text
  const { suggestions, isSearching, clearSuggestions } = useSuggestedSources({
    query: inputText,
    selectedSourceIds,
    enabled: !isWorkflowActive,
    maxResults: 5
  });

  // Handle text changes from SearchInput (for suggested sources)
  const handleTextChange = useCallback((text: string) => {
    setInputText(text);
  }, []);

  // Handle adding a suggested source to context
  const handleAddSuggestion = useCallback(
    (source: SearchableChatSource) => {
      if (!contextStore.isSelected(source.id)) {
        contextStore.addSource(source);
      }
    },
    [contextStore]
  );

  // Gate state holds the pending wallets and the ID of the user-bubble
  // shown above the gate (so Cancel can pop it). What to run on confirm is
  // stashed in proceedReference (function-in-state would clash with setState).
  const [gateState, setGateState] = useState<
    { open: false } | { open: true; pending: PendingSubscription[]; messageId: string | null }
  >({ open: false });
  const proceedReference = useRef<(() => void) | null>(null);

  const xenditPrecheck = useXenditPrecheck({
    model: selectedModel,
    dataSources: contextStore.getSourcesArray()
  });

  // Submit the workflow query (without re-adding a user bubble).
  const submitWorkflow = useCallback(
    (query: string, history: ChatHistoryMessage[]) => {
      const preSelectedSources = contextStore.getSourcesArray();
      if (preSelectedSources.length > 0) {
        const sourceIds = new Set(preSelectedSources.map((s) => s.id));
        void workflow.submitQuery(query, sourceIds, history);
      } else {
        void workflow.submitQuery(query, undefined, history);
      }
    },
    [workflow, contextStore]
  );

  // Run the Xendit precheck, then either open the inline gate or invoke
  // `proceed`. The user bubble is added eagerly by the caller so it shows
  // above the gate while it's open — `messageId` lets Cancel pop it.
  // A flaky precheck must not block the user — on any error we proceed and
  // let the server-side policy enforcement be the safety net.
  const runPrecheckThenProceed = useCallback(
    (proceed: () => void, messageId: string | null) => {
      void (async () => {
        let pending: PendingSubscription[] = [];
        try {
          pending = await xenditPrecheck.runPrecheck();
        } catch {
          /* swallow — fall through to proceed */
        }
        if (pending.length > 0) {
          proceedReference.current = proceed;
          setGateState({ open: true, pending, messageId });
          return;
        }
        proceed();
      })();
    },
    [xenditPrecheck]
  );

  // Handle query submission from the chat input.
  const handleSubmit = useCallback(
    (query: string) => {
      const history: ChatHistoryMessage[] = messages
        .filter((m): m is Message & { content: string } => !!m.content)
        .map((m) => ({ role: m.role, content: m.content }));

      // Add user bubble immediately so it shows above the gate (if precheck
      // blocks) and matches the optimistic-send pattern.
      const messageId = crypto.randomUUID();
      pendingMessageIdReference.current = messageId;
      lastQueryReference.current = query;
      setMessages((previous) => [
        ...previous,
        { id: messageId, role: 'user' as const, content: query, type: 'text' as const }
      ]);
      clearSuggestions();
      setInputText('');

      runPrecheckThenProceed(() => {
        submitWorkflow(query, history);
      }, messageId);
    },
    [messages, runPrecheckThenProceed, submitWorkflow, clearSuggestions]
  );

  // Auto-trigger workflow for the initial query (navigated from home page).
  // The user bubble is already in `messages` from the useState initializer
  // (id = initialQueryMessageIdReference.current).
  useEffect(() => {
    if (
      autoTriggeredReference.current ||
      !initialQuery ||
      initialResult ||
      workflow.phase !== 'idle' ||
      !selectedModel ||
      isLoadingDataSources
    ) {
      return;
    }
    autoTriggeredReference.current = true;
    pendingMessageIdReference.current = initialQueryMessageIdReference.current;
    lastQueryReference.current = initialQuery;
    runPrecheckThenProceed(() => {
      void workflow.submitQuery(initialQuery);
    }, initialQueryMessageIdReference.current);
  }, [
    initialQuery,
    initialResult,
    selectedModel,
    isLoadingDataSources,
    runPrecheckThenProceed,
    workflow
  ]);

  // Handle modal confirm
  const handleSourceModalConfirm = useCallback(
    (selectedSources: ChatSource[]) => {
      // Sync context store with modal selection
      contextStore.clearSources();
      for (const source of selectedSources) {
        contextStore.addSource(source);
      }
      setIsSourceModalOpen(false);
      showQueryInputStep();
    },
    [contextStore, showQueryInputStep]
  );

  // Handle removing a chip
  const handleRemoveSource = useCallback(
    (id: string) => {
      contextStore.removeSource(id);
    },
    [contextStore]
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

  return (
    <div className='bg-card flex h-screen flex-col overflow-hidden'>
      {/* Messages Area — prompt-kit ChatContainer handles auto-scroll */}
      <ChatContainerRoot className='relative flex-1'>
        <ChatContainerContent className='mx-auto w-full max-w-4xl space-y-8 px-6 py-8 pt-16'>
          {messages.length === 0 && !initialQuery && workflow.phase === 'idle' ? (
            <div className='flex flex-col items-center justify-center px-4 py-24'>
              {isLoadingModels ? (
                <div className='space-y-3'>
                  <div className='bg-muted mx-auto h-4 w-48 animate-pulse rounded' />
                  <div className='bg-muted mx-auto h-4 w-32 animate-pulse rounded' />
                </div>
              ) : (
                <>
                  <p className='font-inter text-muted-foreground mb-6 text-sm'>
                    Ask anything using the input below.
                  </p>
                  <div className='flex flex-wrap justify-center gap-2'>
                    {[
                      'Summarize this dataset',
                      'What trends do you see?',
                      'Compare these sources'
                    ].map((example) => (
                      <button
                        key={example}
                        type='button'
                        onClick={() => {
                          handleSubmit(example);
                        }}
                        className='font-inter text-muted-foreground hover:text-foreground border-border hover:bg-muted rounded-full border px-4 py-2 text-xs transition-colors'
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          ) : (
            <>
              {/* Existing messages */}
              {messages.map((message) =>
                message.role === 'user' ? (
                  /* ── User bubble ── right-aligned pill */
                  <Message key={message.id} className='justify-end'>
                    <div className='flex max-w-full flex-col items-end'>
                      {message.content && (
                        <MessageContent className='font-inter bg-primary text-primary-foreground max-w-2xl rounded-2xl rounded-br-none px-5 py-3 text-sm leading-relaxed shadow-sm'>
                          {message.content}
                        </MessageContent>
                      )}
                    </div>
                  </Message>
                ) : (
                  /* ── Assistant response ── avatar + free-flowing content + hover actions */
                  <Message key={message.id} className='group/message max-w-3xl items-start'>
                    <MessageAvatar
                      src='/favicon/openmined-icon.svg'
                      alt='SyftHub'
                      fallback='S'
                      className='mt-0.5'
                    />
                    <div className='flex min-w-0 flex-1 flex-col'>
                      {message.content && (
                        <MarkdownMessage
                          content={message.content}
                          annotatedContent={message.annotatedResponse}
                          id={message.id}
                        />
                      )}
                      {message.aggregatorSources &&
                        Object.keys(message.aggregatorSources).length > 0 && (
                          <div className='mt-4'>
                            <SourcesSection sources={message.aggregatorSources} />
                          </div>
                        )}
                      <MessageActions className='mt-2 opacity-0 transition-opacity group-hover/message:opacity-100'>
                        <MessageAction tooltip='Copy message'>
                          <button
                            type='button'
                            aria-label='Copy message'
                            onClick={() => {
                              handleCopy(message.content ?? '', message.id);
                            }}
                            className='hover:text-foreground text-muted-foreground rounded p-1 transition-colors'
                          >
                            {copiedId === message.id ? (
                              <Check className='h-3.5 w-3.5 text-green-500' />
                            ) : (
                              <Copy className='h-3.5 w-3.5' />
                            )}
                          </button>
                        </MessageAction>
                      </MessageActions>
                    </div>
                  </Message>
                )
              )}

              {/* Payment gate — appears below the user bubble when one or
                  more selected endpoints carry an unfunded Xendit policy. */}
              {gateState.open && (
                <PaymentGate
                  pending={gateState.pending}
                  onCancel={() => {
                    // Pop the user bubble that triggered this gate.
                    const droppedId = gateState.messageId;
                    if (droppedId) {
                      setMessages((previous) => previous.filter((m) => m.id !== droppedId));
                    }
                    pendingMessageIdReference.current = null;
                    proceedReference.current = null;
                    setGateState({ open: false });
                  }}
                  onConfirmSend={() => {
                    setGateState({ open: false });
                    const proceed = proceedReference.current;
                    proceedReference.current = null;
                    proceed?.();
                  }}
                  onRemovePending={(removed) => {
                    // Drop those endpoints from the chat selection. Data
                    // sources are removed by ID; if the row covers the
                    // active model, clear the model too.
                    const removedModel = removed.endpoints.some((ep) => ep.role === 'model');
                    for (const ep of removed.endpoints) {
                      if (ep.role === 'data_source') {
                        contextStore.removeSource(ep.id);
                      } else if (ep.id === selectedModel?.id) {
                        setSelectedModel(null);
                      }
                    }
                    // Each row is uniquely identified by (walletKey, endpoint).
                    // Multiple rows can share a walletKey when sibling endpoints
                    // come from the same publisher wallet, so filtering by
                    // walletKey alone would drop every sibling row at once.
                    const removedPath = removed.endpoints[0]?.path ?? '';
                    const next = gateState.pending.filter(
                      (p) =>
                        p.walletKey !== removed.walletKey ||
                        (p.endpoints[0]?.path ?? '') !== removedPath
                    );
                    // Removing the model invalidates the queued send —
                    // no model left to chat with. Behave like Cancel.
                    if (removedModel) {
                      const droppedId = gateState.messageId;
                      if (droppedId) {
                        setMessages((previous) => previous.filter((m) => m.id !== droppedId));
                      }
                      pendingMessageIdReference.current = null;
                      proceedReference.current = null;
                      setGateState({ open: false });
                      return;
                    }
                    if (next.length === 0) {
                      // Last data-source blocker removed — fire the
                      // queued send (model is still selected).
                      const proceed = proceedReference.current;
                      proceedReference.current = null;
                      proceed?.();
                      setGateState({ open: false });
                      return;
                    }
                    setGateState({ open: true, pending: next, messageId: gateState.messageId });
                  }}
                />
              )}

              {/* Workflow UI - Processing Status & Streaming */}
              {(workflow.phase === 'preparing' || workflow.phase === 'streaming') && (
                <Message className='max-w-3xl items-start'>
                  <MessageAvatar
                    src='/favicon/openmined-icon.svg'
                    alt='SyftHub'
                    fallback='S'
                    className='mt-0.5'
                  />
                  <div className='flex min-w-0 flex-1 flex-col gap-3'>
                    {workflow.processingStatus && (
                      <StatusIndicator status={workflow.processingStatus} />
                    )}
                    {workflow.streamedContent && (
                      <MarkdownMessage content={workflow.streamedContent} id='streaming' />
                    )}
                  </div>
                </Message>
              )}

              {/* Error display */}
              {workflow.phase === 'error' && workflow.error && (
                <div className='max-w-3xl'>
                  <div className='font-inter flex items-start gap-2.5 rounded-lg border border-red-200/60 bg-red-50/60 px-4 py-3 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-950/40 dark:text-red-300'>
                    <span>{workflow.error}</span>
                  </div>
                  {lastQueryReference.current && (
                    <button
                      type='button'
                      onClick={() => {
                        handleSubmit(lastQueryReference.current);
                      }}
                      className='font-inter text-muted-foreground hover:text-foreground mt-2 text-xs underline underline-offset-2'
                    >
                      Retry
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </ChatContainerContent>

        {/* Scroll-to-bottom button — must be inside ChatContainerRoot for StickToBottom context */}
        <div className='absolute bottom-4 z-10 flex w-full justify-center'>
          <ScrollButton />
        </div>
      </ChatContainerRoot>

      {/* Input Area - in flex flow to prevent content overlap and eliminate double scrollbar */}
      <div className='bg-card p-4'>
        <div className='mx-auto max-w-4xl px-6'>
          {/* Suggested data sources based on input text */}
          <SuggestedSources
            suggestions={suggestions}
            onAdd={handleAddSuggestion}
            isSearching={isSearching}
          />

          <SearchInput
            onSubmit={handleSubmit}
            disabled={isWorkflowActive}
            isProcessing={workflow.phase === 'streaming'}
            placeholder={
              contextStore.count() > 0
                ? 'Ask about these sources...'
                : 'Start making queries, use @ for specific sources'
            }
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
            onTextChange={handleTextChange}
          />
        </div>
      </div>

      {/* Add Sources Modal */}
      <AddSourcesModal
        isOpen={isSourceModalOpen}
        onClose={() => {
          setIsSourceModalOpen(false);
          showQueryInputStep();
        }}
        availableSources={sources}
        selectedSourceIds={new Set(contextStore.getSourcesArray().map((s) => s.id))}
        onConfirm={handleSourceModalConfirm}
      />

      {/* Onboarding welcome banner */}
      <OnboardingWelcomeBanner
        isVisible={showWelcomeBanner}
        onDismiss={() => {
          setShowWelcomeBanner(false);
        }}
      />
    </div>
  );
}
