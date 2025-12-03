import { useLocation } from 'react-router-dom';

import { ChatView } from '@/components/chat-view';

interface LocationState {
  query?: string;
}

/**
 * Chat page - AI-powered chat interface.
 * Receives initial query from navigation state (e.g., from home page search).
 */
export default function ChatPage() {
  const location = useLocation();
  const state = location.state as LocationState | null;

  // Get initial query from navigation state
  const initialQuery = state?.query ?? '';

  return <ChatView initialQuery={initialQuery} />;
}
