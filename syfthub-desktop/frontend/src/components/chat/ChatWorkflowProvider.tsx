// ChatWorkflowProvider wraps useAgentWorkflow in a React context so both the
// live chat pane AND the review pane (for continuation) can drive the SAME
// agent session state — entries, isRunning, awaitingInput, and the start/send/
// stop methods.
//
// Without this, useAgentWorkflow would be called twice (once in each pane)
// and produce two disjoint sets of state — continuation from a review would
// not be visible in the live pane's transcript. With it, ReviewChatPane.onSubmit
// → startSessionWithHistory mutates the same workflow that AgentChatContent
// reads from, so switching activeChat to 'live' shows the continuation.
//
// The provider is mounted once at ChatView (above both panes) and parametrized
// by the currently-selected agent. Pane components consume via useChatWorkflow().

import { createContext, useContext, type ReactNode } from 'react';

import { useAgentWorkflow } from '@/hooks/use-agent-workflow';
import type {
  AgentEntry,
  AgentStreamEvent,
  PendingPayment,
  TranscriptMessage,
} from '@/hooks/use-agent-workflow';

export type { AgentEntry, AgentStreamEvent, PendingPayment, TranscriptMessage };

interface ChatWorkflowValue {
  entries: AgentEntry[];
  isRunning: boolean;
  awaitingInput: boolean;
  startSession: (prompt: string) => Promise<void>;
  startSessionWithHistory: (
    history: TranscriptMessage[],
    prompt: string,
    overrides?: { endpointPath: string; endpointName: string; originReviewId?: string },
  ) => Promise<void>;
  sendInput: (content: string) => Promise<void>;
  stopSession: () => Promise<void>;
  clearEntries: () => void;
  pendingPayment: PendingPayment | null;
  dismissPayment: () => void;
}

const ChatWorkflowContext = createContext<ChatWorkflowValue | null>(null);

export interface ChatWorkflowProviderProps {
  endpointPath: string | null;
  endpointName: string;
  children: ReactNode;
}

/** ChatWorkflowProvider must be mounted exactly once at the chat surface root.
 *  It owns the single useAgentWorkflow instance for the chat session. */
export function ChatWorkflowProvider({
  endpointPath,
  endpointName,
  children,
}: Readonly<ChatWorkflowProviderProps>) {
  const workflow = useAgentWorkflow({ endpointPath, endpointName });
  return (
    <ChatWorkflowContext.Provider value={workflow}>
      {children}
    </ChatWorkflowContext.Provider>
  );
}

/** useChatWorkflow returns the active workflow. Throws when called outside
 *  a ChatWorkflowProvider so a missing provider mount surfaces immediately
 *  rather than as silent "nothing happens" bugs. */
export function useChatWorkflow(): ChatWorkflowValue {
  const ctx = useContext(ChatWorkflowContext);
  if (!ctx) {
    throw new Error('useChatWorkflow must be used inside ChatWorkflowProvider');
  }
  return ctx;
}
