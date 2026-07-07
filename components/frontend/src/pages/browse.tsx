import { useSearchParams } from 'react-router-dom';

import { BrowseView } from '@/components/browse-view';

/**
 * Browse page - Browse and search data sources.
 * Supports URL-based search via ?q= query parameter.
 * Navigation to individual endpoints is handled by BrowseView via Link components.
 */
export default function BrowsePage() {
  const [searchParams] = useSearchParams();

  // Get initial query from URL params
  const initialQuery = searchParams.get('q') ?? '';

  return <BrowseView initialQuery={initialQuery} />;
}
