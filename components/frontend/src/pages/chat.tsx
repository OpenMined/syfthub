import type { WorkflowResult } from '@/hooks/use-chat-workflow';
import type { ChatSource } from '@/lib/types';

import { useLocation } from 'react-router-dom';

import { ChatView } from '@/components/chat/chat-view';

interface LocationState {
  query?: string;
  model?: ChatSource | null;
  initialResult?: WorkflowResult | null;
}

/**
 * Chat page - AI-powered chat interface.
 * Receives initial query and optional pre-selected model from navigation state (e.g., from home page search).
 * Can also receive an initialResult if the query was already executed on the home page.
 * Pre-selected data sources are read directly from the ContextSelectionStore (Zustand).
 */
export default function ChatPage() {
  const location = useLocation();
  const state = location.state as LocationState | null;

  // Get initial query, model, and result from navigation state
  const initialQuery = state?.query ?? '';
  const initialModel = state?.model ?? null;
  const initialResult = state?.initialResult ?? null;

  return (
    <ChatView
      initialQuery={initialQuery}
      initialModel={initialModel}
      initialResult={initialResult}
    />
  );
}
