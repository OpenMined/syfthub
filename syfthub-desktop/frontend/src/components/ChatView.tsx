import { useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import ArrowUp from 'lucide-react/dist/esm/icons/arrow-up';
import Bot from 'lucide-react/dist/esm/icons/bot';
import MessageSquarePlus from 'lucide-react/dist/esm/icons/message-square-plus';
import Square from 'lucide-react/dist/esm/icons/square';
import WifiOff from 'lucide-react/dist/esm/icons/wifi-off';

import { ChatContainerContent, ChatContainerRoot } from '@/components/prompt-kit/chat-container';
import { Loader } from '@/components/prompt-kit/loader';
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from '@/components/prompt-kit/prompt-input';
import { ScrollButton } from '@/components/prompt-kit/scroll-button';

import { MarkdownMessage } from '@/components/chat/markdown-message';
import { ModelSelector } from '@/components/chat/model-selector';
import { SourcesSection } from '@/components/chat/sources-section';
import { StatusIndicator } from '@/components/chat/status-indicator';

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
// Message Bubbles
// =============================================================================

function UserBubble({ content }: Readonly<{ content: string }>) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className='flex justify-end px-4'
    >
      <div className='bg-muted text-foreground max-w-[80%] rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed'>
        {content}
      </div>
    </motion.div>
  );
}

function AssistantBubble({ message }: Readonly<{ message: AssistantMessage }>) {
  const showLoader = message.isStreaming && message.content.length === 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className='px-4'
    >
      <div className='max-w-[90%]'>
        {showLoader ? (
          <div className='py-2'>
            <Loader variant='typing' size='sm' />
          </div>
        ) : (
          <MarkdownMessage
            content={message.content}
            annotatedContent={message.isStreaming ? undefined : message.annotatedResponse}
          />
        )}

        {!message.isStreaming && message.sources && Object.keys(message.sources).length > 0 ? (
          <div className='mt-3'>
            <SourcesSection sources={message.sources} />
          </div>
        ) : null}
      </div>
    </motion.div>
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
  } = useAppStore((s) => ({
    endpoints: s.endpoints,
    aggregatorURL: s.aggregatorURL,
    chatSelectedModel: s.chatSelectedModel,
    chatSelectedSources: s.chatSelectedSources,
    setChatSelectedModel: s.setChatSelectedModel,
  }));

  const [inputValue, setInputValue] = useState('');

  const { messages, workflowState, sendMessage, stopStream, clearMessages, isStreaming } =
    useChatWorkflow({
      selectedModel: chatSelectedModel,
      selectedSources: chatSelectedSources,
    });

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
          <ChatContainerContent className='py-4'>
            {messages.length === 0 ? (
              <EmptyState hasAggregator={hasAggregator} />
            ) : (
              <div className='space-y-6'>
                {messages.map((msg) =>
                  msg.role === 'user' ? (
                    <UserBubble key={msg.id} content={msg.content} />
                  ) : (
                    <AssistantBubble key={msg.id} message={msg as AssistantMessage} />
                  )
                )}
              </div>
            )}

            {/* Processing status */}
            <AnimatePresence>
              {workflowState.processingStatus ? (
                <div className='px-4 pt-4'>
                  <StatusIndicator status={workflowState.processingStatus} />
                </div>
              ) : null}
            </AnimatePresence>
          </ChatContainerContent>

          <ScrollButton className='absolute bottom-4 right-4' />
        </ChatContainerRoot>
      </div>

      {/* Input area */}
      <div className='border-border shrink-0 border-t px-4 py-3'>
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
            {/* Left: model selector */}
            <div className='flex items-center gap-2'>
              <ModelSelector
                models={endpoints}
                selectedModel={chatSelectedModel}
                onModelSelect={setChatSelectedModel}
                isLoading={false}
              />
            </div>

            {/* Right: send / stop */}
            <div className='flex items-center gap-1'>
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
  );
}
