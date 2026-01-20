import { useSearchParams } from 'react-router-dom';

import { BrowseView } from '@/components/browse-view';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';

/**
 * Browse page - Browse and search data sources.
 * Supports URL-based search via ?q= query parameter.
 * Navigation to individual endpoints is handled by BrowseView via Link components.
 */
export default function BrowsePage() {
  const { user } = useAuth();
  const { openLogin } = useModal();
  const [searchParams] = useSearchParams();

  // Get initial query from URL params
  const initialQuery = searchParams.get('q') ?? '';

  return <BrowseView initialQuery={initialQuery} onAuthRequired={user ? undefined : openLogin} />;
}
