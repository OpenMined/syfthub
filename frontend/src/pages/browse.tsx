import { useNavigate, useSearchParams } from 'react-router-dom';

import { BrowseView } from '@/components/browse-view';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';

/**
 * Browse page - Browse and search data sources.
 * Supports URL-based search via ?q= query parameter.
 */
export default function BrowsePage() {
  const { user } = useAuth();
  const { openLogin } = useModal();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Get initial query from URL params
  const initialQuery = searchParams.get('q') ?? '';

  const handleViewEndpoint = (slug: string, owner = 'anonymous') => {
    // Navigate to GitHub-style URL: /username/endpoint-slug
    navigate(`/${owner}/${slug}`);
  };

  return (
    <BrowseView
      initialQuery={initialQuery}
      onViewEndpoint={handleViewEndpoint}
      onAuthRequired={user ? undefined : openLogin}
    />
  );
}
