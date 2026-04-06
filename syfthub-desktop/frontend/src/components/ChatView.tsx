import { useCallback, useMemo, useRef, useState } from 'react';

// TODO(AGENT_ONLY): WifiOff removed from import — only used by ChatModeContent empty state.
// To restore, add WifiOff back to this import.
import { ArrowUp, Bot, Brain, Check, ChevronDown, ChevronRight, Copy, Loader2, MessageSquarePlus, Square } from 'lucide-react';

import { ChatContainerContent, ChatContainerRoot } from '@/components/prompt-kit/chat-container';
import { Loader } from '@/components/prompt-kit/loader';
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
} from '@/components/prompt-kit/message';
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from '@/components/prompt-kit/prompt-input';
import { ScrollButton } from '@/components/prompt-kit/scroll-button';
import { Tool, type ToolPart } from '@/components/prompt-kit/tool';

import { MarkdownMessage } from '@/components/chat/markdown-message';
import { ModelSelector } from '@/components/chat/model-selector';
// TODO(AGENT_ONLY): Imports below hidden — only used by ChatModeContent (standard chat).
// To restore, uncomment these imports and re-enable ChatModeContent in ChatView().
// import { SourceSelector } from '@/components/chat/source-selector';
// import { SourcesSection } from '@/components/chat/sources-section';
// import { StatusIndicator } from '@/components/chat/status-indicator';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';

import { useCopyToClipboard } from '@/components/tool-ui/shared/use-copy-to-clipboard';
// TODO(AGENT_ONLY): useChatWorkflow import hidden — only used by ChatModeContent.
// To restore, uncomment:
// import { useChatWorkflow } from '@/hooks/use-chat-workflow';
// import type { AssistantMessage } from '@/hooks/use-chat-workflow';
import { useAgentWorkflow } from '@/hooks/use-agent-workflow';
import type { AgentEntry } from '@/hooks/use-agent-workflow';
import { useAppStore } from '@/stores/appStore';

// =============================================================================
// Empty State
// =============================================================================

function EmptyState({ hasAggregator, isAgent }: Readonly<{ hasAggregator: boolean; isAgent: boolean }>) {
  // TODO(AGENT_ONLY): Aggregator-missing branch hidden — only agent mode used.
  // To restore, uncomment the hasAggregator check below.
  /* if (!hasAggregator && !isAgent) {
    return (
      <div className='flex h-full flex-col items-center justify-center gap-3 p-8'>
        <WifiOff className='text-muted-foreground h-8 w-8' />
        <p className='text-muted-foreground text-center text-sm'>
          Chat is not available — aggregator URL could not be loaded.
          <br />
          Check your API key and connection, then restart the app.
        </p>
      </div>
    );
  } */

  return (
    <div className='flex h-full flex-col items-center justify-center gap-4 p-8'>
      <div className='bg-muted flex h-12 w-12 items-center justify-center rounded-full'>
        <Bot className='text-muted-foreground h-6 w-6' />
      </div>
      <div className='text-center'>
        {/* TODO(AGENT_ONLY): Simplified to agent-only messaging.
            To restore, use ternary: isAgent ? 'Start an agent session' : 'How can I help you today?' */}
        <p className='text-foreground text-sm font-medium'>
          Start an agent session
        </p>
        <p className='text-muted-foreground mt-1 text-xs'>
          Type a prompt to start an interactive agent session with real-time feedback.
        </p>
      </div>
    </div>
  );
}

// =============================================================================
// Avatar
// =============================================================================

function AssistantAvatar() {
  return (
    <div className='bg-muted mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full'>
      <OpenMinedIcon className='h-5 w-5' />
    </div>
  );
}

// =============================================================================
// Agent Event Renderers
// =============================================================================

function ThinkingEntry({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className='border-border/50 bg-muted/30 rounded-lg border px-3 py-2'>
      <button
        type='button'
        onClick={() => setExpanded(!expanded)}
        className='text-muted-foreground flex w-full items-center gap-2 text-xs font-medium'
      >
        <Brain className='h-3.5 w-3.5 text-purple-400' />
        <span>Thinking</span>
        {expanded ? <ChevronDown className='ml-auto h-3 w-3' /> : <ChevronRight className='ml-auto h-3 w-3' />}
      </button>
      {expanded && (
        <pre className='text-muted-foreground mt-2 whitespace-pre-wrap text-xs leading-relaxed'>
          {content}
        </pre>
      )}
    </div>
  );
}

function StatusEntry({ content, isActive }: { content: string; isActive: boolean }) {
  return (
    <div className='text-muted-foreground flex items-center gap-2 px-1 text-xs'>
      {isActive ? (
        <Loader2 className='h-3 w-3 animate-spin' />
      ) : (
        <div className='h-1.5 w-1.5 rounded-full bg-current opacity-30 mx-[3px]' />
      )}
      <span>{content}</span>
    </div>
  );
}

/**
 * Pre-scan entries to pair each tool_call with its nearest following tool_result.
 * Returns a map from tool_call entry index → tool_result entry index.
 * Also returns the set of tool_result indices that were consumed (so they can be skipped).
 */
function pairToolEntries(entries: AgentEntry[]): { callToResult: Map<number, number>; consumedResults: Set<number> } {
  const callToResult = new Map<number, number>();
  const consumedResults = new Set<number>();

  for (let i = 0; i < entries.length; i++) {
    if (entries[i].kind !== 'tool_call') continue;
    // Scan forward for the nearest unconsumed tool_result
    for (let j = i + 1; j < entries.length; j++) {
      if (entries[j].kind === 'tool_result' && !consumedResults.has(j)) {
        callToResult.set(i, j);
        consumedResults.add(j);
        break;
      }
      // Stop scanning if we hit another tool_call (result belongs to a later call)
      if (entries[j].kind === 'tool_call') break;
    }
  }

  return { callToResult, consumedResults };
}

/** Build a ToolPart from a tool_call entry, optionally paired with its tool_result. */
function buildToolPart(
  callEntry: AgentEntry,
  resultEntry: AgentEntry | undefined,
  isRunning: boolean,
): ToolPart {
  const data = callEntry.data ?? {};
  const toolName = String(data.tool_name ?? 'tool');
  const args = data.arguments as Record<string, unknown> | undefined;
  const toolCallId = data.tool_call_id ? String(data.tool_call_id) : undefined;

  if (resultEntry) {
    const rd = resultEntry.data ?? {};
    const status = String(rd.status ?? 'success');
    const isSuccess = status === 'success';
    const result = rd.result as Record<string, unknown> | string | undefined;
    const output = result != null
      ? (typeof result === 'string' ? { result } : result)
      : undefined;

    return {
      type: toolName,
      state: isSuccess ? 'output-available' : 'output-error',
      input: args,
      output,
      toolCallId,
      errorText: isSuccess ? undefined : String(rd.error ?? rd.result ?? status),
    };
  }

  return {
    type: toolName,
    state: isRunning ? 'input-streaming' : 'input-available',
    input: args,
    toolCallId,
  };
}

function RequestInputEntry({ prompt }: { prompt: string }) {
  return (
    <div className='border-primary/30 bg-primary/5 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
      <Bot className='h-3.5 w-3.5 text-primary shrink-0' />
      <span className='text-foreground'>{prompt}</span>
    </div>
  );
}

// =============================================================================
// Shared Chat Input Area
// =============================================================================

interface ChatInputAreaProps {
  isLoading: boolean;
  inputDisabled: boolean;
  value: string;
  onValueChange: (v: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  canSubmit: boolean;
  placeholder: string;
  stopTooltip: string;
  sendTooltip: string;
  isActive: boolean;
  promptInputDisabled?: boolean;
  banner?: React.ReactNode;
  footer?: React.ReactNode;
}

function ChatInputArea({
  isLoading,
  inputDisabled,
  value,
  onValueChange,
  onSubmit,
  onStop,
  canSubmit,
  placeholder,
  stopTooltip,
  sendTooltip,
  isActive,
  promptInputDisabled,
  banner,
  footer,
}: Readonly<ChatInputAreaProps>) {
  const endpoints = useAppStore((s) => s.endpoints);
  const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);
  const chatSelectedSources = useAppStore((s) => s.chatSelectedSources);
  const setChatSelectedModel = useAppStore((s) => s.setChatSelectedModel);
  const toggleChatSource = useAppStore((s) => s.toggleChatSource);

  // TODO(AGENT_ONLY): Store already filters to agent-only. To restore, change filter back to:
  //   (e) => e.type === 'model' || e.type === 'agent'
  const modelEndpoints = endpoints;
  // TODO(AGENT_ONLY): Data source endpoints hidden. To restore, uncomment:
  // const dataSourceEndpoints = useMemo(
  //   () => endpoints.filter((e) => e.type === 'data_source'),
  //   [endpoints],
  // );

  return (
    <div className='shrink-0 p-4'>
      <div className='mx-auto max-w-4xl px-6'>
        {banner}
        <PromptInput
          isLoading={isLoading}
          value={value}
          onValueChange={onValueChange}
          onSubmit={onSubmit}
          disabled={promptInputDisabled}
          className='shadow-sm'
        >
          <PromptInputTextarea
            placeholder={placeholder}
            disabled={inputDisabled}
          />

          {/* TODO(AGENT_ONLY): Changed to justify-end since SourceSelector (left element) is hidden.
              To restore, change back to justify-between and uncomment SourceSelector. */}
          <PromptInputActions className='justify-end pt-1'>
            <div className='flex items-center gap-1'>
              <ModelSelector
                models={modelEndpoints}
                selectedModel={chatSelectedModel}
                onModelSelect={setChatSelectedModel}
                isLoading={false}
              />
              {isActive ? (
                <PromptInputAction tooltip={stopTooltip}>
                  <button
                    type='button'
                    onClick={onStop}
                    className='bg-foreground text-background flex h-8 w-8 items-center justify-center rounded-full transition-opacity hover:opacity-80'
                  >
                    <Square className='h-3 w-3 fill-current' aria-hidden='true' />
                  </button>
                </PromptInputAction>
              ) : (
                <PromptInputAction tooltip={sendTooltip}>
                  <button
                    type='button'
                    onClick={onSubmit}
                    disabled={!canSubmit}
                    className='bg-foreground text-background flex h-8 w-8 items-center justify-center rounded-full transition-opacity disabled:opacity-30 hover:opacity-80'
                  >
                    <ArrowUp className='h-4 w-4' aria-hidden='true' />
                  </button>
                </PromptInputAction>
              )}
            </div>
          </PromptInputActions>
        </PromptInput>

        {footer}
      </div>
    </div>
  );
}

// =============================================================================
// Shared User Message Bubble
// =============================================================================

function UserBubble({ id, content }: { id: string; content: string }) {
  return (
    <Message key={id} className='justify-end'>
      <div className='flex max-w-full flex-col items-end'>
        <MessageContent className='font-inter bg-primary text-primary-foreground max-w-2xl rounded-2xl rounded-br-none px-5 py-3 text-sm leading-relaxed shadow-sm'>
          {content}
        </MessageContent>
      </div>
    </Message>
  );
}

// =============================================================================
// Agent Chat Content (calls useAgentWorkflow internally)
// =============================================================================

function AgentChatContent() {
  const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);

  const {
    entries,
    isRunning,
    awaitingInput,
    startSession,
    sendInput,
    stopSession,
    clearEntries,
  } = useAgentWorkflow({
    endpointSlug: chatSelectedModel?.slug ?? null,
  });

  const { copiedId, copy: handleCopy } = useCopyToClipboard();
  const [inputValue, setInputValue] = useState('');

  const handleSubmit = useCallback(async () => {
    const prompt = inputValue.trim();
    if (!prompt || !chatSelectedModel) return;

    if (awaitingInput) {
      setInputValue('');
      await sendInput(prompt);
    } else if (!isRunning) {
      setInputValue('');
      await startSession(prompt);
    }
  }, [inputValue, chatSelectedModel, awaitingInput, isRunning, sendInput, startSession]);

  const handleStop = useCallback(async () => {
    await stopSession();
  }, [stopSession]);

  const handleNewChat = useCallback(() => {
    clearEntries();
  }, [clearEntries]);

  const canSubmit = Boolean(inputValue.trim()) && Boolean(chatSelectedModel) && (!isRunning || awaitingInput);

  // Derive a stable fingerprint that only changes when tool_call/tool_result
  // entries are added (not on every token flush). This avoids O(n^2) pairing
  // work during streaming when only message/token entries are appended.
  const toolFingerprint = useMemo(() => {
    let count = 0;
    for (const e of entries) {
      if (e.kind === 'tool_call' || e.kind === 'tool_result') count++;
    }
    return count;
  }, [entries]);

  // Keep a ref so pairToolEntries can access current entries without
  // adding `entries` itself (a new array each render) to the dep array.
  const entriesRef = useRef(entries);
  entriesRef.current = entries;

  const { callToResult, consumedResults } = useMemo(() => {
    return pairToolEntries(entriesRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolFingerprint]);

  const lastStatusIdx = useMemo(() => {
    return entries.reduce((last, e, i) => e.kind === 'status' ? i : last, -1);
  }, [entries]);

  return (
    <div className='flex h-full flex-col'>
      {/* Top bar */}
      <div className='border-border flex shrink-0 items-center justify-between border-b px-4 py-2'>
        <div className='flex items-center gap-2'>
          <span className='text-foreground text-sm font-semibold'>Agent</span>
          {isRunning && (
            <span className='flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-0.5 text-[10px] text-green-400'>
              <span className='h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse' />
              Running
            </span>
          )}
        </div>
        {entries.length > 0 && !isRunning ? (
          <button
            type='button'
            onClick={handleNewChat}
            className='text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs transition-colors'
          >
            <MessageSquarePlus className='h-3.5 w-3.5' />
            <span>New session</span>
          </button>
        ) : null}
      </div>

      {/* Scrollable entries */}
      <div className='relative min-h-0 flex-1'>
        <ChatContainerRoot className='h-full'>
          <ChatContainerContent className='mx-auto w-full max-w-4xl space-y-3 px-6 py-6'>
            {entries.length === 0 ? (
              <EmptyState hasAggregator={false} isAgent />
            ) : entries.map((entry, entryIndex) => {
                if (entry.kind === 'user') {
                  return <UserBubble key={entry.id} id={entry.id} content={entry.content} />;
                }

                if (entry.kind === 'thinking') {
                  return (
                    <Message key={entry.id} className='max-w-3xl items-start'>
                      <AssistantAvatar />
                      <div className='min-w-0 flex-1'>
                        <ThinkingEntry content={entry.content} />
                      </div>
                    </Message>
                  );
                }

                if (entry.kind === 'status') {
                  // Hide internal lifecycle events — the Tool component conveys state visually
                  const status = entry.data?.status as string | undefined;
                  if (status === 'connected' || status === 'running' || status === 'thinking') return null;
                  const isActive = isRunning && !awaitingInput && entryIndex === lastStatusIdx;
                  return (
                    <div key={entry.id} className='ml-10'>
                      <StatusEntry content={entry.content} isActive={isActive} />
                    </div>
                  );
                }

                if (entry.kind === 'tool_call') {
                  const resultIdx = callToResult.get(entryIndex);
                  const pairedResult = resultIdx != null ? entries[resultIdx] : undefined;
                  const toolPart = buildToolPart(entry, pairedResult, isRunning);
                  return (
                    <div key={entry.id} className='ml-10 max-w-2xl'>
                      <Tool toolPart={toolPart} className='mt-0' />
                    </div>
                  );
                }

                // Skip tool_result entries consumed by a tool_call above
                if (entry.kind === 'tool_result') {
                  if (consumedResults.has(entryIndex)) return null;
                  // Orphan tool_result — render standalone
                  const toolPart = buildToolPart(
                    { ...entry, data: { tool_name: String(entry.data?.tool_name ?? 'tool'), ...entry.data } },
                    entry,
                    isRunning,
                  );
                  return (
                    <div key={entry.id} className='ml-10 max-w-2xl'>
                      <Tool toolPart={toolPart} className='mt-0' />
                    </div>
                  );
                }

                if (entry.kind === 'message' || entry.kind === 'token') {
                  return (
                    <Message key={entry.id} className='group/message max-w-3xl items-start'>
                      <AssistantAvatar />
                      <div className='flex min-w-0 flex-1 flex-col'>
                        <MarkdownMessage content={entry.content} />
                        {entry.kind === 'message' && entry.content && (
                          <MessageActions className='mt-2 opacity-0 transition-opacity group-hover/message:opacity-100'>
                            <MessageAction tooltip='Copy'>
                              <button
                                type='button'
                                onClick={() => handleCopy(entry.content, entry.id)}
                                className='hover:text-foreground text-muted-foreground rounded p-1 transition-colors'
                              >
                                {copiedId === entry.id ? <Check className='h-3.5 w-3.5 text-green-500' /> : <Copy className='h-3.5 w-3.5' />}
                              </button>
                            </MessageAction>
                          </MessageActions>
                        )}
                      </div>
                    </Message>
                  );
                }

                if (entry.kind === 'request_input') {
                  // The input box is already visible and re-enabled by
                  // awaitingInput — no need to show the prompt text.
                  return null;
                }

                if (entry.kind === 'error') {
                  return (
                    <div key={entry.id} className='ml-10'>
                      <div className='text-destructive text-xs'>
                        {entry.content}
                      </div>
                    </div>
                  );
                }

                if (entry.kind === 'completed') {
                  return (
                    <div key={entry.id} className='ml-10'>
                      <div className='text-muted-foreground text-xs italic'>
                        Session completed
                      </div>
                    </div>
                  );
                }

                return null;
              })}

            {isRunning && !awaitingInput && entries.length > 0 &&
              entries[entries.length - 1]?.kind !== 'token' &&
              entries[entries.length - 1]?.kind !== 'request_input' && (
              <div className='ml-10'>
                <Loader variant='typing' size='sm' />
              </div>
            )}
          </ChatContainerContent>
          <ScrollButton className='absolute bottom-4 right-4' />
        </ChatContainerRoot>
      </div>

      {/* Input area */}
      <ChatInputArea
        isLoading={isRunning && !awaitingInput}
        inputDisabled={isRunning && !awaitingInput}
        value={inputValue}
        onValueChange={setInputValue}
        onSubmit={handleSubmit}
        onStop={handleStop}
        canSubmit={canSubmit}
        placeholder={
          awaitingInput
            ? 'Type your response to the agent…'
            : !chatSelectedModel
              ? 'Select an agent to start…'
              : isRunning
                ? 'Agent is working…'
                : 'Type a prompt to start the agent…'
        }
        stopTooltip='Stop agent'
        sendTooltip='Send (Enter)'
        isActive={isRunning}
        footer={chatSelectedModel ? (
          <p className='text-muted-foreground mt-1.5 text-center text-[10px]'>
            <span className='font-medium'>{chatSelectedModel.name}</span>
          </p>
        ) : undefined}
      />
    </div>
  );
}

/* TODO(AGENT_ONLY): Entire ChatModeContent component commented out — only agent mode is active.
   To restore:
   1. Uncomment this entire function
   2. Uncomment the SourceSelector, SourcesSection, StatusIndicator, useChatWorkflow, AssistantMessage imports above
   3. Add WifiOff back to the lucide-react import
   4. In ChatView(), restore the isAgent conditional: if (isAgent) return <AgentChatContent />; return <ChatModeContent />;

function ChatModeContent() {
  const aggregatorURL = useAppStore((s) => s.aggregatorURL);
  const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);
  const chatSelectedSources = useAppStore((s) => s.chatSelectedSources);

  const {
    messages,
    workflowState,
    sendMessage,
    stopStream,
    clearMessages,
    isStreaming,
  } = useChatWorkflow({
    selectedModel: chatSelectedModel,
    selectedSources: chatSelectedSources,
  });

  const { copiedId, copy: handleCopy } = useCopyToClipboard();
  const [inputValue, setInputValue] = useState('');

  const hasAggregator = Boolean(aggregatorURL);
  const isActive = isStreaming;

  const handleSubmit = useCallback(async () => {
    const prompt = inputValue.trim();
    if (!prompt || !chatSelectedModel) return;
    if (isStreaming) return;
    setInputValue('');
    await sendMessage(prompt);
  }, [inputValue, chatSelectedModel, isStreaming, sendMessage]);

  const handleStop = useCallback(async () => {
    await stopStream();
  }, [stopStream]);

  const handleNewChat = useCallback(() => {
    clearMessages();
  }, [clearMessages]);

  const canSubmit = Boolean(inputValue.trim()) && Boolean(chatSelectedModel) && !isStreaming;

  return (
    <div className='flex h-full flex-col'>
      <div className='border-border flex shrink-0 items-center justify-between border-b px-4 py-2'>
        <span className='text-foreground text-sm font-semibold'>Chat</span>
        {messages.length > 0 ? (
          <button
            type='button'
            onClick={handleNewChat}
            className='text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs transition-colors'
            title='New chat'
          >
            <MessageSquarePlus className='h-3.5 w-3.5' />
            <span>New chat</span>
          </button>
        ) : null}
      </div>

      <div className='relative min-h-0 flex-1'>
        <ChatContainerRoot className='h-full'>
          <ChatContainerContent className='mx-auto w-full max-w-4xl space-y-8 px-6 py-8'>
            {messages.length === 0 ? (
              <EmptyState hasAggregator={hasAggregator} isAgent={false} />
            ) : (
              <>
                {messages.map((msg) => {
                  if (msg.role === 'user') {
                    return <UserBubble key={msg.id} id={msg.id} content={msg.content} />;
                  }

                  const assistant = msg as AssistantMessage;
                  const showLoader = assistant.isStreaming && assistant.content.length === 0;

                  return (
                    <Message key={msg.id} className='group/message max-w-3xl items-start'>
                      <AssistantAvatar />
                      <div className='flex min-w-0 flex-1 flex-col'>
                        {showLoader ? (
                          <div className='flex min-w-0 flex-1 flex-col gap-3'>
                            <Loader variant='typing' size='sm' />
                            {workflowState.processingStatus && (
                              <StatusIndicator status={workflowState.processingStatus} />
                            )}
                          </div>
                        ) : (
                          <MarkdownMessage
                            content={assistant.content}
                            annotatedContent={
                              assistant.isStreaming ? undefined : assistant.annotatedResponse
                            }
                          />
                        )}
                        {!assistant.isStreaming &&
                          assistant.sources &&
                          Object.keys(assistant.sources).length > 0 && (
                            <div className='mt-4'>
                              <SourcesSection sources={assistant.sources} />
                            </div>
                          )}
                        {!assistant.isStreaming && assistant.content && (
                          <MessageActions className='mt-2 opacity-0 transition-opacity group-hover/message:opacity-100'>
                            <MessageAction tooltip='Copy message'>
                              <button
                                type='button'
                                aria-label='Copy message'
                                onClick={() => {
                                  handleCopy(assistant.content, msg.id);
                                }}
                                className='hover:text-foreground text-muted-foreground rounded p-1 transition-colors'
                              >
                                {copiedId === msg.id ? (
                                  <Check className='h-3.5 w-3.5 text-green-500' />
                                ) : (
                                  <Copy className='h-3.5 w-3.5' />
                                )}
                              </button>
                            </MessageAction>
                          </MessageActions>
                        )}
                      </div>
                    </Message>
                  );
                })}
              </>
            )}
          </ChatContainerContent>

          <ScrollButton className='absolute bottom-4 right-4' />
        </ChatContainerRoot>
      </div>

      <ChatInputArea
        isLoading={isActive}
        inputDisabled={!hasAggregator}
        value={inputValue}
        onValueChange={setInputValue}
        onSubmit={handleSubmit}
        onStop={handleStop}
        canSubmit={canSubmit}
        placeholder={
          !hasAggregator
            ? 'Chat unavailable — aggregator not configured'
            : !chatSelectedModel
              ? 'Select a model to start chatting…'
              : 'Ask a question…'
        }
        stopTooltip='Stop generation'
        sendTooltip='Send message (Enter)'
        isActive={isActive}
        promptInputDisabled={!hasAggregator}
        footer={chatSelectedModel ? (
          <p className='text-muted-foreground mt-1.5 text-center text-[10px]'>
            Using <span className='font-medium'>{chatSelectedModel.name}</span>
            {chatSelectedSources.length > 0
              ? ` · ${chatSelectedSources.length} source${chatSelectedSources.length === 1 ? '' : 's'}`
              : ''}
          </p>
        ) : undefined}
      />
    </div>
  );
}
*/

// =============================================================================
// Main Component (thin wrapper — conditionally renders one mode)
// =============================================================================

export function ChatView() {
  // TODO(AGENT_ONLY): Always render AgentChatContent — standard chat mode hidden.
  // To restore, uncomment the isAgent check and ChatModeContent fallback below:
  //   const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);
  //   const isAgent = chatSelectedModel?.type === 'agent';
  //   if (isAgent) return <AgentChatContent />;
  //   return <ChatModeContent />;
  return <AgentChatContent />;
}
