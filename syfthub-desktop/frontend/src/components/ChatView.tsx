import { useCallback, useMemo, useState } from 'react';

import { ArrowUp, Bot, Check, Copy, MessageSquarePlus, Square, WifiOff } from 'lucide-react';

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

import { MarkdownMessage } from '@/components/chat/markdown-message';
import { ModelSelector } from '@/components/chat/model-selector';
import { SourceSelector } from '@/components/chat/source-selector';
import { SourcesSection } from '@/components/chat/sources-section';
import { StatusIndicator } from '@/components/chat/status-indicator';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';

import { useChatWorkflow } from '@/hooks/use-chat-workflow';
import type { AssistantMessage } from '@/hooks/use-chat-workflow';
import { useAppStore } from '@/stores/appStore';

// =============================================================================
// Empty State
// =============================================================================

function EmptyState({ hasAggregator }: Readonly<{ hasAggregator: boolean }>) {
  if (!hasAggregator) {
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
  }

  return (
    <div className='flex h-full flex-col items-center justify-center gap-4 p-8'>
      <div className='bg-muted flex h-12 w-12 items-center justify-center rounded-full'>
        <Bot className='text-muted-foreground h-6 w-6' />
      </div>
      <div className='text-center'>
        <p className='text-foreground text-sm font-medium'>How can I help you today?</p>
        <p className='text-muted-foreground mt-1 text-xs'>
          Select a model, then type a message to start chatting.
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
// Main Component
// =============================================================================

export function ChatView() {
  const {
    endpoints,
    aggregatorURL,
    chatSelectedModel,
    chatSelectedSources,
    setChatSelectedModel,
    toggleChatSource,
  } = useAppStore();

  // Endpoints split by type: models go to ModelSelector, everything else to SourceSelector
  const modelEndpoints = useMemo(
    () => endpoints.filter((e) => e.type === 'model'),
    [endpoints],
  );
  const dataSourceEndpoints = useMemo(
    () => endpoints.filter((e) => e.type !== 'model'),
    [endpoints],
  );

  const [inputValue, setInputValue] = useState('');

  const { messages, workflowState, sendMessage, stopStream, clearMessages, isStreaming } =
    useChatWorkflow({
      selectedModel: chatSelectedModel,
      selectedSources: chatSelectedSources,
    });

  // Copy-to-clipboard state
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const handleCopy = useCallback((content: string, messageId: string) => {
    void navigator.clipboard.writeText(content);
    setCopiedId(messageId);
    setTimeout(() => {
      setCopiedId((prev) => (prev === messageId ? null : prev));
    }, 2000);
  }, []);

  const handleSubmit = useCallback(async () => {
    const prompt = inputValue.trim();
    if (!prompt || !chatSelectedModel || isStreaming) return;
    setInputValue('');
    await sendMessage(prompt);
  }, [inputValue, chatSelectedModel, isStreaming, sendMessage]);

  const handleStop = useCallback(async () => {
    await stopStream();
  }, [stopStream]);

  const handleNewChat = useCallback(() => {
    clearMessages();
  }, [clearMessages]);

  const hasAggregator = Boolean(aggregatorURL);
  const canSubmit = Boolean(inputValue.trim()) && Boolean(chatSelectedModel) && !isStreaming;

  return (
    <div className='flex h-full flex-col'>
      {/* Top bar */}
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

      {/* Scrollable message area */}
      <div className='relative min-h-0 flex-1'>
        <ChatContainerRoot className='h-full'>
          <ChatContainerContent className='mx-auto w-full max-w-4xl space-y-8 px-6 py-8'>
            {messages.length === 0 ? (
              <EmptyState hasAggregator={hasAggregator} />
            ) : (
              <>
                {messages.map((msg) => {
                  if (msg.role === 'user') {
                    /* ── User bubble ── right-aligned pill */
                    return (
                      <Message key={msg.id} className='justify-end'>
                        <div className='flex max-w-full flex-col items-end'>
                          <MessageContent className='font-inter bg-primary text-primary-foreground max-w-2xl rounded-2xl rounded-br-none px-5 py-3 text-sm leading-relaxed shadow-sm'>
                            {msg.content}
                          </MessageContent>
                        </div>
                      </Message>
                    );
                  }

                  /* ── Assistant response ── avatar + free-flowing content + hover actions */
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

            {/* Processing status — shown inline inside the streaming assistant message */}
          </ChatContainerContent>

          <ScrollButton className='absolute bottom-4 right-4' />
        </ChatContainerRoot>
      </div>

      {/* Input area */}
      <div className='bg-card shrink-0 p-4'>
        <div className='mx-auto max-w-4xl px-6'>
          <PromptInput
            isLoading={isStreaming}
            value={inputValue}
            onValueChange={setInputValue}
            onSubmit={handleSubmit}
            disabled={!hasAggregator}
            className='shadow-sm'
          >
            <PromptInputTextarea
              placeholder={
                !hasAggregator
                  ? 'Chat unavailable — aggregator not configured'
                  : !chatSelectedModel
                    ? 'Select a model to start chatting…'
                    : 'Ask a question…'
              }
              disabled={!hasAggregator}
            />

            <PromptInputActions className='justify-between pt-1'>
              {/* Left: source / context selector */}
              <SourceSelector
                endpoints={dataSourceEndpoints}
                selectedSources={chatSelectedSources}
                onToggle={toggleChatSource}
                disabled={!hasAggregator}
              />

              {/* Right: model selector + send / stop */}
              <div className='flex items-center gap-1'>
                <ModelSelector
                  models={modelEndpoints}
                  selectedModel={chatSelectedModel}
                  onModelSelect={setChatSelectedModel}
                  isLoading={false}
                />
                {isStreaming ? (
                  <PromptInputAction tooltip='Stop generation'>
                    <button
                      type='button'
                      onClick={handleStop}
                      className='bg-foreground text-background flex h-8 w-8 items-center justify-center rounded-full transition-opacity hover:opacity-80'
                    >
                      <Square className='h-3 w-3 fill-current' aria-hidden='true' />
                    </button>
                  </PromptInputAction>
                ) : (
                  <PromptInputAction tooltip='Send message (Enter)'>
                    <button
                      type='button'
                      onClick={handleSubmit}
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

          {/* Hint text */}
          {chatSelectedModel ? (
            <p className='text-muted-foreground mt-1.5 text-center text-[10px]'>
              Using <span className='font-medium'>{chatSelectedModel.name}</span>
              {chatSelectedSources.length > 0
                ? ` · ${chatSelectedSources.length} source${chatSelectedSources.length === 1 ? '' : 's'}`
                : ''}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
