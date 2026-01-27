import type { ChatSource } from '@/lib/types';

import { useLocation } from 'react-router-dom';

import { ChatView } from '@/components/chat-view';

interface LocationState {
  query?: string;
  selectedModel?: ChatSource | null;
}

/**
 * Chat page - AI-powered chat interface.
 * Receives initial query and optionally a pre-selected model from navigation state
 * (e.g., from home page search).
 */
export default function ChatPage() {
  const location = useLocation();
  const state = location.state as LocationState | null;

  // Get initial query and selected model from navigation state
  const initialQuery = state?.query ?? '';
  const initialModel = state?.selectedModel ?? null;

  return <ChatView initialQuery={initialQuery} initialModel={initialModel} />;
}
