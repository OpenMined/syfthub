import type { ChatSource } from '@/lib/types';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import BookOpen from 'lucide-react/dist/esm/icons/book-open';
import Code from 'lucide-react/dist/esm/icons/code';
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
              className='font-inter border-border/60 text-muted-foreground hover:border-border hover:text-foreground flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm transition-colors'
            >
              <BookOpen className='h-3.5 w-3.5' />
              How it works
            </button>
            <button
              type='button'
              onClick={handleJoinNetwork}
              className='font-inter bg-primary/10 text-primary hover:bg-primary/20 flex items-center gap-2 rounded-full px-4 py-1.5 text-sm transition-colors'
            >
              <UserPlus className='h-3.5 w-3.5' />
              Join the Network
            </button>
            <button
              type='button'
              onClick={() => navigate('/build')}
              className='font-inter bg-primary/10 text-primary hover:bg-primary/20 flex items-center gap-2 rounded-full px-4 py-1.5 text-sm transition-colors'
            >
              <Code className='h-3.5 w-3.5' />
              Build with it
              <ArrowRight className='h-3 w-3' />
            </button>
          </div>
        }
      />
    </>
  );
}
