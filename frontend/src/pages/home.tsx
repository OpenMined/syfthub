import { useNavigate } from 'react-router-dom';

import { Hero } from '@/components/hero';
import { RecentModels } from '@/components/recent-models';
import { RecentSources } from '@/components/recent-sources';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';
import { useAPI } from '@/hooks/use-api';
import { getPublicEndpoints, getTrendingEndpoints } from '@/lib/endpoint-utils';

/**
 * Home page - Landing page with hero, search, and recent items.
 */
export default function HomePage() {
  const { user } = useAuth();
  const { openLogin } = useModal();
  const navigate = useNavigate();

  // Fetch recent endpoints (sorted by updated_at)
  const { data: recentEndpoints, isLoading: isLoadingRecent } = useAPI(
    () => getPublicEndpoints({ limit: 4 }),
    { immediate: true }
  );

  // Fetch trending endpoints (sorted by stars)
  const { data: trendingEndpoints, isLoading: isLoadingTrending } = useAPI(
    () => getTrendingEndpoints({ limit: 4 }),
    { immediate: true }
  );

  const handleSearch = (query: string) => {
    // Navigate to chat with the search query in state
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
    navigate('/chat', { state: { query } });
  };

  // Determine if we have any endpoints to show
  const isLoading = isLoadingRecent || isLoadingTrending;
  const hasRecentEndpoints = (recentEndpoints?.length ?? 0) > 0;
  const hasTrendingEndpoints = (trendingEndpoints?.length ?? 0) > 0;
  const hasAnyEndpoints = hasRecentEndpoints || hasTrendingEndpoints;

  // Center hero when no endpoints exist (and not loading)
  const shouldCenterHero = !isLoading && !hasAnyEndpoints;

  return (
    <>
      <Hero
        onSearch={handleSearch}
        onAuthRequired={user ? undefined : openLogin}
        fullHeight={shouldCenterHero}
      />
      {/* Only show the recent sections if there are endpoints registered */}
      {(isLoading || hasAnyEndpoints) && (
        <section className='bg-white px-6 py-6'>
          <div className='mx-auto grid max-w-4xl gap-10 md:grid-cols-2'>
            <RecentSources endpoints={recentEndpoints ?? []} isLoading={isLoadingRecent} />
            <RecentModels endpoints={trendingEndpoints ?? []} isLoading={isLoadingTrending} />
          </div>
        </section>
      )}
    </>
  );
}
