import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ArrowUp, Bot, Brain, Check, ChevronDown, ChevronRight, Copy, Loader2, Paperclip, Square, Upload } from 'lucide-react';
import { OnFileDrop, OnFileDropOff } from '../../wailsjs/runtime/runtime';
import {
  BrowseForAttachment,
  SaveAgentAttachment,
} from '../../wailsjs/go/main/App';

import { AttachmentChip } from '@/components/chat/AttachmentChip';
import { useAttachments, type AttachmentSummary } from '@/hooks/use-attachments';

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
import { OpenMinedIcon } from '@/components/ui/openmined-icon';

import { useCopyToClipboard } from '@/components/tool-ui/shared/use-copy-to-clipboard';
import { useAgentWorkflow } from '@/hooks/use-agent-workflow';
import type { AgentEntry } from '@/hooks/use-agent-workflow';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';

// Generic agent-suitable suggestion chips for the welcome screen. Kept short
// (≤ ~6 words) so two columns fit on a max-w-3xl message column without wrap.
const SUGGESTED_PROMPTS: readonly string[] = [
  'Summarize the latest changes in my repo',
  'Explain how this codebase handles auth',
  'Draft release notes from recent commits',
  'Help me debug a failing test',
];

// =============================================================================
// Empty State
// =============================================================================

function EmptyState({ onSelectPrompt }: Readonly<{ onSelectPrompt?: (prompt: string) => void }>) {
  const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);

  return (
    <div className='flex h-full flex-col items-center justify-center px-6 py-12'>
      <OpenMinedIcon className='mb-6 h-16 w-16 opacity-90' />
      <h2 className='text-foreground text-xl font-semibold tracking-tight'>
        What can I help you build?
      </h2>
      <p className='text-muted-foreground mt-2 max-w-md text-center text-sm leading-relaxed'>
        {chatSelectedModel ? (
          <>
            Start an interactive session with{' '}
            <span className='text-foreground font-medium'>{chatSelectedModel.name}</span>.
          </>
        ) : (
          <>Select an agent below, then type a prompt to begin.</>
        )}
      </p>

      {onSelectPrompt && (
        <div className='mt-8 grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2'>
          {SUGGESTED_PROMPTS.map((p) => (
            <button
              key={p}
              type='button'
              onClick={() => onSelectPrompt(p)}
              className='border-border bg-card text-muted-foreground hover:border-border hover:bg-muted/60 hover:text-foreground focus-visible:ring-ring rounded-lg border px-4 py-3 text-left text-sm transition-colors focus:outline-none focus-visible:ring-2'
            >
              {p}
            </button>
          ))}
        </div>
      )}
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
    <div className='border-border bg-muted/40 rounded-lg border px-3 py-2'>
      <button
        type='button'
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className='text-muted-foreground hover:text-foreground flex w-full items-center gap-2 text-xs font-medium transition-colors'
      >
        <Brain className='h-3.5 w-3.5' aria-hidden='true' />
        <span>Thinking</span>
        {expanded ? (
          <ChevronDown className='ml-auto h-3 w-3' aria-hidden='true' />
        ) : (
          <ChevronRight className='ml-auto h-3 w-3' aria-hidden='true' />
        )}
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
    <div
      className={cn(
        'flex items-center gap-2 px-1 text-xs transition-colors',
        isActive ? 'text-primary' : 'text-muted-foreground',
      )}
    >
      {isActive ? (
        <Loader2 className='h-3 w-3 animate-spin' aria-hidden='true' />
      ) : (
        <Check className='h-3 w-3 opacity-40' aria-hidden='true' />
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
      <Bot className='text-primary h-3.5 w-3.5 shrink-0' aria-hidden='true' />
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
  // Optional attachment props — only the agent path passes these. When the
  // staged list / handlers are provided, the input renders the paperclip
  // button + the staged-files chip strip.
  staged?: AttachmentSummary[];
  onPickAttachment?: () => void;
  onRemoveAttachment?: (fileId: string) => void;
  attachmentsBusy?: boolean;
  attachmentError?: string | null;
  attachmentsDisabled?: boolean;
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
  staged,
  onPickAttachment,
  onRemoveAttachment,
  attachmentsBusy,
  attachmentError,
  attachmentsDisabled,
}: Readonly<ChatInputAreaProps>) {
  const networkAgents = useAppStore((s) => s.networkAgents);
  const networkAgentsLoading = useAppStore((s) => s.networkAgentsLoading);
  const chatSelectedModel = useAppStore((s) => s.chatSelectedModel);
  const chatSelectedSources = useAppStore((s) => s.chatSelectedSources);
  const setChatSelectedModel = useAppStore((s) => s.setChatSelectedModel);
  const toggleChatSource = useAppStore((s) => s.toggleChatSource);
  const fetchNetworkAgents = useAppStore((s) => s.fetchNetworkAgents);

  // Agent dropdown is sourced from the hub browse list (network-wide), not
  // local endpoints — see appStore.fetchNetworkAgents.
  const modelEndpoints = networkAgents;

  const showAttachmentButton = onPickAttachment !== undefined;
  const stagedFiles = staged ?? [];

  return (
    <div className='shrink-0 p-4'>
      {/* Subtle top gradient: messages fade behind the input as they scroll
          rather than terminating at a hard line. */}
      <div className='pointer-events-none -mt-8 mb-2 h-8 bg-gradient-to-t from-background to-transparent' />
      <div className='mx-auto max-w-3xl px-6'>
        {banner}
        {/* Staged-attachment chip strip — visible only when something is staged.
            aria-live announces additions to screen readers. */}
        {stagedFiles.length > 0 && (
          <div
            role='region'
            aria-label='Staged attachments'
            aria-live='polite'
            className='animate-in fade-in mb-2 flex flex-wrap items-center gap-1.5 duration-150'
          >
            {stagedFiles.map((s) => (
              <AttachmentChip
                key={s.file_id}
                fileId={s.file_id}
                name={s.name}
                mime={s.mime}
                sizeBytes={s.size_bytes}
                staged
                onRemove={onRemoveAttachment}
              />
            ))}
          </div>
        )}
        {attachmentError && (
          <p
            role='alert'
            className='text-destructive animate-in fade-in slide-in-from-top-1 mb-2 text-xs duration-150'
          >
            {attachmentError}
          </p>
        )}
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

          <PromptInputActions className='justify-between pt-1'>
            <div className='flex items-center gap-1'>
              {showAttachmentButton && (
                <PromptInputAction
                  tooltip={
                    attachmentsDisabled
                      ? 'Start a session to attach files'
                      : 'Attach file (or drag and drop)'
                  }
                >
                  <button
                    type='button'
                    onClick={onPickAttachment}
                    disabled={attachmentsDisabled || attachmentsBusy}
                    className='text-muted-foreground hover:text-foreground hover:bg-muted focus-visible:ring-ring focus-visible:ring-offset-background flex h-8 w-8 items-center justify-center rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-30'
                    aria-label='Attach file'
                  >
                    {attachmentsBusy ? (
                      <Loader2
                        className='h-4 w-4 animate-spin'
                        aria-hidden='true'
                      />
                    ) : (
                      <Paperclip className='h-4 w-4' aria-hidden='true' />
                    )}
                  </button>
                </PromptInputAction>
              )}
            </div>
            <div className='flex items-center gap-1'>
              <ModelSelector
                models={modelEndpoints}
                selectedModel={chatSelectedModel}
                onModelSelect={setChatSelectedModel}
                isLoading={networkAgentsLoading}
                onOpen={() => { void fetchNetworkAgents(); }}
              />
              {isActive ? (
                <PromptInputAction tooltip={stopTooltip}>
                  <button
                    type='button'
                    onClick={onStop}
                    aria-label={typeof stopTooltip === 'string' ? stopTooltip : 'Stop'}
                    className='bg-foreground text-background flex h-8 w-8 items-center justify-center rounded-md transition-opacity hover:opacity-80'
                  >
                    <Square className='h-3.5 w-3.5' aria-hidden='true' />
                  </button>
                </PromptInputAction>
              ) : (
                <PromptInputAction tooltip={sendTooltip}>
                  <button
                    type='button'
                    onClick={onSubmit}
                    disabled={!canSubmit}
                    aria-label={typeof sendTooltip === 'string' ? sendTooltip : 'Send'}
                    className='bg-foreground text-background flex h-8 w-8 items-center justify-center rounded-md transition-opacity hover:opacity-80 disabled:opacity-50'
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

/**
 * User message bubble.
 *
 * Visual: neutral muted surface (not the brand color). The single asymmetric
 * corner (rounded-br-md) preserves the chat convention "the sender's tail
 * points back to them" without flooding long conversations with saturated
 * teal — which is reserved for true accents (send button, focus rings,
 * citation badges, attachment-saved confirmation).
 *
 * isTurnBoundary adds extra top margin so the eye can clearly see where one
 * back-and-forth ended and the next began.
 */
function UserBubble({
  id,
  content,
  isTurnBoundary,
}: {
  id: string;
  content: string;
  isTurnBoundary?: boolean;
}) {
  return (
    <Message
      key={id}
      role='article'
      aria-label='You said'
      className={cn('justify-end', isTurnBoundary && 'mt-6')}
    >
      <div className='flex max-w-full flex-col items-end'>
        <MessageContent className='font-inter bg-muted text-foreground max-w-2xl rounded-lg rounded-br-sm px-4 py-2.5 text-[15px] leading-relaxed'>
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
  const fetchNetworkAgents = useAppStore((s) => s.fetchNetworkAgents);

  // Refresh the hub catalog on entering the chat view; the hub has no push
  // signal, so the dropdown would otherwise show whatever was cached at boot.
  // TTL inside fetchNetworkAgents coalesces rapid remounts.
  useEffect(() => {
    void fetchNetworkAgents();
  }, [fetchNetworkAgents]);

  const {
    entries,
    isRunning,
    awaitingInput,
    startSession,
    sendInput,
    stopSession,
  } = useAgentWorkflow({
    endpointPath: chatSelectedModel ? `${chatSelectedModel.ownerUsername}/${chatSelectedModel.slug}` : null,
  });

  const { copiedId, copy: handleCopy } = useCopyToClipboard();
  const [inputValue, setInputValue] = useState('');

  // ── Attachments ──────────────────────────────────────────────────────────
  const {
    staged,
    attach,
    remove: removeStaged,
    clear: clearStaged,
    busy: attachmentsBusy,
    error: attachmentError,
  } = useAttachments();

  // Drop overlay is visible while a file is being dragged into the window.
  const [dragActive, setDragActive] = useState(false);
  // Track whether the active session has accepted at least one inbound staged
  // file so the UI can warn users who drop before starting a session.
  const sessionActive = isRunning || awaitingInput;

  const handlePickAttachment = useCallback(async () => {
    if (!sessionActive) return;
    try {
      const path = await BrowseForAttachment();
      if (path) await attach(path);
    } catch {
      /* attach() already records the error via the hook */
    }
  }, [sessionActive, attach]);

  // Save an agent-emitted attachment to ~/Downloads. Returns the absolute
  // path so the chip can show a "Saved to …" confirmation tooltip.
  const handleDownloadAttachment = useCallback(
    async (fileId: string, fileName: string): Promise<string> => {
      return await SaveAgentAttachment(fileId, fileName);
    },
    [],
  );

  // Wails native file-drop. Paths are absolute strings. We only act when a
  // session is live — the runner won't see anything until a session exists.
  useEffect(() => {
    OnFileDrop((_x, _y, paths) => {
      if (!sessionActive) return;
      setDragActive(false);
      void (async () => {
        for (const p of paths) {
          try {
            await attach(p);
          } catch {
            /* hook records the per-file error; keep iterating */
          }
        }
      })();
    }, /* useDropTarget */ true);

    // HTML5 drag events are needed to flash the overlay; the actual drop is
    // handled by Wails (above). dragenter/dragleave use a counter pattern to
    // avoid flicker when entering child elements.
    let depth = 0;
    const onEnter = () => {
      depth++;
      if (sessionActive) setDragActive(true);
    };
    const onLeave = () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragActive(false);
    };
    const onDrop = () => {
      depth = 0;
      setDragActive(false);
    };
    window.addEventListener('dragenter', onEnter);
    window.addEventListener('dragleave', onLeave);
    window.addEventListener('drop', onDrop);

    return () => {
      OnFileDropOff();
      window.removeEventListener('dragenter', onEnter);
      window.removeEventListener('dragleave', onLeave);
      window.removeEventListener('drop', onDrop);
    };
  }, [sessionActive, attach]);

  const handleSubmit = useCallback(async () => {
    const prompt = inputValue.trim();
    if (!prompt || !chatSelectedModel) return;

    if (awaitingInput) {
      setInputValue('');
      // Staged files were already delivered to the runner when the user
      // dropped/picked them (AttachToActiveSession queued them on the
      // session). The chip strip just gives visual confirmation; clear it
      // now that we're sending the follow-up text.
      clearStaged();
      await sendInput(prompt);
    } else if (!isRunning) {
      setInputValue('');
      // Note: any pre-session staged files (dropped before clicking send)
      // currently fail because AttachToActiveSession requires an active
      // session. We could buffer them, but for v1 the staged chip strip is
      // visible-only-while-running.
      clearStaged();
      await startSession(prompt);
    }
  }, [inputValue, chatSelectedModel, awaitingInput, isRunning, sendInput, startSession, clearStaged]);

  const handleStop = useCallback(async () => {
    await stopSession();
  }, [stopSession]);

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

  // Suggestion-chip handler — populates the textarea so the user can edit
  // before sending. Auto-send would feel surprising.
  const handleSelectPrompt = useCallback((p: string) => {
    setInputValue(p);
  }, []);

  return (
    <div className='flex h-full flex-col'>
      {/* Scrollable entries */}
      <div className='relative min-h-0 flex-1'>
        <ChatContainerRoot className='h-full'>
          <ChatContainerContent className='mx-auto w-full max-w-3xl space-y-4 px-6 py-6'>
            {entries.length === 0 ? (
              <EmptyState onSelectPrompt={handleSelectPrompt} />
            ) : entries.map((entry, entryIndex) => {
                if (entry.kind === 'user') {
                  // Anything past the first user message starts a fresh turn.
                  return (
                    <UserBubble
                      key={entry.id}
                      id={entry.id}
                      content={entry.content}
                      isTurnBoundary={entryIndex > 0}
                    />
                  );
                }

                if (entry.kind === 'thinking') {
                  return (
                    <Message
                      key={entry.id}
                      role='article'
                      aria-label='Assistant thinking'
                      className='max-w-3xl items-start'
                    >
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

                if (entry.kind === 'attachment') {
                  const d = entry.data ?? {};
                  const attName = String(d.name ?? entry.content);
                  return (
                    <Message
                      key={entry.id}
                      role='article'
                      aria-label='Assistant attachment'
                      className='max-w-3xl items-start'
                    >
                      <AssistantAvatar />
                      <div className='min-w-0 flex-1'>
                        <AttachmentChip
                          fileId={String(d.file_id ?? '')}
                          name={attName}
                          mime={String(d.mime ?? 'application/octet-stream')}
                          sizeBytes={Number(d.size_bytes ?? 0)}
                          onDownload={(fid) => handleDownloadAttachment(fid, attName)}
                        />
                      </div>
                    </Message>
                  );
                }

                if (entry.kind === 'message' || entry.kind === 'token') {
                  return (
                    <Message
                      key={entry.id}
                      role='article'
                      aria-label='Assistant said'
                      className='group/message max-w-3xl items-start'
                    >
                      <AssistantAvatar />
                      <div className='flex min-w-0 flex-1 flex-col'>
                        <MarkdownMessage content={entry.content} />
                        {entry.kind === 'message' && entry.content && (
                          <MessageActions className='mt-2 opacity-0 transition-opacity group-hover/message:opacity-100'>
                            <MessageAction tooltip='Copy'>
                              <button
                                type='button'
                                onClick={() => handleCopy(entry.content, entry.id)}
                                aria-label='Copy message'
                                className='hover:text-foreground hover:bg-muted text-muted-foreground rounded-md p-1 transition-colors'
                              >
                                {copiedId === entry.id ? (
                                  <Check className='text-success h-3.5 w-3.5' aria-hidden='true' />
                                ) : (
                                  <Copy className='h-3.5 w-3.5' aria-hidden='true' />
                                )}
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
                    <div
                      key={entry.id}
                      role='alert'
                      className='border-destructive/30 bg-destructive/10 text-destructive ml-10 rounded-lg border px-3 py-2 text-xs'
                    >
                      {entry.content}
                    </div>
                  );
                }

                if (entry.kind === 'completed') {
                  return (
                    <div key={entry.id} className='ml-10 flex items-center gap-2 py-2'>
                      <Check className='text-success h-3.5 w-3.5' aria-hidden='true' />
                      <span className='text-muted-foreground text-xs'>Session completed</span>
                      <div className='bg-border/60 ml-2 h-px flex-1' />
                    </div>
                  );
                }

                if (entry.kind === 'cancelled') {
                  return (
                    <div key={entry.id} className='ml-10 flex items-center gap-2 py-2'>
                      <div
                        className='bg-muted-foreground/50 h-1.5 w-1.5 rounded-full'
                        aria-hidden='true'
                      />
                      <span className='text-muted-foreground text-xs'>Session stopped</span>
                      <div className='bg-border/60 ml-2 h-px flex-1' />
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
          <ScrollButton className='absolute bottom-6 right-6' />
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
        staged={staged}
        onPickAttachment={handlePickAttachment}
        onRemoveAttachment={removeStaged}
        attachmentsBusy={attachmentsBusy}
        attachmentError={attachmentError}
        attachmentsDisabled={!sessionActive}
        footer={chatSelectedModel ? (
          <p className='text-muted-foreground mt-1.5 text-center text-[10px]'>
            <span className='font-medium'>{chatSelectedModel.name}</span>
          </p>
        ) : undefined}
      />

      {/* Drop overlay — fades in when files are dragged over the window AND
          a session is active. The Wails-recognized drop target uses the
          --wails-drop-target CSS custom property (see main.go DragAndDrop
          options) so the runtime knows we accept the drop here. */}
      {dragActive && sessionActive && (
        <div
          // eslint-disable-next-line react/forbid-dom-props
          style={{ '--wails-drop-target': 'drop' } as React.CSSProperties}
          className='bg-background/60 animate-in fade-in pointer-events-none fixed inset-0 z-50 flex items-center justify-center backdrop-blur-md duration-150'
          role='presentation'
        >
          <div className='border-primary/40 bg-card text-foreground animate-in fade-in zoom-in-95 flex flex-col items-center gap-3 rounded-xl border-2 border-dashed px-10 py-8 shadow-2xl duration-200'>
            <div className='bg-primary/10 text-primary flex h-12 w-12 items-center justify-center rounded-lg'>
              <Upload className='h-6 w-6' aria-hidden='true' />
            </div>
            <p className='text-base font-medium'>Drop to attach</p>
            <p className='text-muted-foreground text-sm'>
              Files will be sent on your next message
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatView() {
  return <AgentChatContent />;
}
