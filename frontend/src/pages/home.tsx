import { UserPlus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Hero } from '@/components/hero';
import { RecentModels } from '@/components/recent-models';
import { RecentSources } from '@/components/recent-sources';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';
import { useAPI } from '@/hooks/use-api';
import {
  getPublicEndpoints,
  getTotalEndpointsCount,
  getTrendingEndpoints
} from '@/lib/endpoint-utils';

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

  // Fetch total endpoints count
  const { data: totalCount, isLoading: isLoadingTotalCount } = useAPI(
    () => getTotalEndpointsCount(),
    { immediate: true }
  );

  const handleSearch = (query: string) => {
    // Navigate to chat with the search query in state
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
    navigate('/chat', { state: { query } });
  };

  const handleJoinNetwork = () => {
    if (user) {
      // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
      navigate('/endpoints');
    } else {
      openLogin();
    }
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

      {/* Active Nodes Count and Action Buttons */}
      <section className='bg-white px-6 py-4'>
        <div className='mx-auto max-w-4xl'>
          <div className='flex items-center justify-center gap-8 py-4'>
            {/* Active Nodes Count */}
            <div className='flex items-center gap-3'>
              <div className='flex -space-x-2'>
                <div className='flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-gray-400'>
                  <span className='font-inter text-sm font-bold text-white'>A</span>
                </div>
                <div className='flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-gray-500'>
                  <span className='font-inter text-sm font-bold text-white'>R</span>
                </div>
                <div className='flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-gray-600'>
                  <span className='font-inter text-sm font-bold text-white'>K</span>
                </div>
              </div>
              <div className='flex flex-col'>
                <span className='font-inter text-lg font-semibold text-gray-800'>
                  {isLoadingTotalCount ? '...' : `${totalCount ?? 0} Nodes`}
                </span>
                <span className='font-inter text-xs text-gray-500'>Active contributors</span>
              </div>
            </div>

            {/* Action Buttons */}
            <div className='flex items-center gap-4'>
              <button
                onClick={() => navigate('/about')}
                className='font-inter flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50'
              >
                <svg className='h-4 w-4' fill='currentColor' viewBox='0 0 24 24'>
                  <path d='M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' />
                </svg>
                How it works
              </button>
              <button
                onClick={handleJoinNetwork}
                className='from-syft-secondary to-syft-purple hover:from-syft-purple hover:to-syft-green font-inter flex items-center gap-2 rounded-lg bg-gradient-to-r px-4 py-2 text-sm text-white transition-colors'
              >
                <UserPlus className='h-4 w-4' />
                Join the Network
              </button>
            </div>
          </div>
        </div>
      </section>

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
