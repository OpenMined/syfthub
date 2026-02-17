import type { ChatSource } from '@/lib/types';

import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import { useNavigate } from 'react-router-dom';

import { GlobalDirectory } from '@/components/global-directory';
import { Hero } from '@/components/hero';
import { useAuth } from '@/context/auth-context';
import { usePublicEndpoints } from '@/hooks/use-endpoint-queries';
import { useModalStore } from '@/stores/modal-store';

/**
 * Home page - Landing page with hero, search, and recent items.
 */
export default function HomePage() {
  const { user } = useAuth();
  const { openLogin } = useModalStore();
  const navigate = useNavigate();

  // Fetch all public endpoints for the global directory
  const { data: allEndpoints, isLoading: isLoadingAll } = usePublicEndpoints(50);

  const handleSearch = (query: string, selectedModel: ChatSource | null) => {
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
    navigate('/chat', { state: { query, model: selectedModel } });
  };

  const handleJoinNetwork = () => {
    if (user) {
      // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
      navigate('/endpoints');
    } else {
      openLogin();
    }
  };

  return (
    <>
      <Hero
        onSearch={handleSearch}
        onAuthRequired={user ? undefined : openLogin}
        sidePanel={<GlobalDirectory endpoints={allEndpoints ?? []} isLoading={isLoadingAll} />}
        actionButtons={
          <div className='flex items-center gap-3'>
            <button
              type='button'
              onClick={() => navigate('/about')}
              className='font-inter border-border text-muted-foreground hover:bg-accent flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors'
            >
              <svg className='h-4 w-4' fill='currentColor' viewBox='0 0 24 24'>
                <path d='M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' />
              </svg>
              How it works
            </button>
            <button
              type='button'
              onClick={handleJoinNetwork}
              className='from-secondary to-chart-3 hover:from-chart-3 hover:to-chart-1 font-inter flex items-center gap-2 rounded-lg bg-gradient-to-r px-4 py-2 text-sm text-white transition-colors'
            >
              <UserPlus className='h-4 w-4' />
              Join the Network
            </button>
          </div>
        }
      />
    </>
  );
}
