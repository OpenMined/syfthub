import type { ChatSource } from '@/lib/types';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Star from 'lucide-react/dist/esm/icons/star';
import { Link } from 'react-router-dom';

// Color palette for endpoint items (warm tones for trending)
const ITEM_COLORS: readonly { bg: string; border: string }[] = [
  { bg: 'bg-[#f79763]', border: 'hover:border-l-[#f79763]' },
  { bg: 'bg-[#cc677b]', border: 'hover:border-l-[#cc677b]' },
  { bg: 'bg-[#6976ae]', border: 'hover:border-l-[#6976ae]' },
  { bg: 'bg-[#52a8c5]', border: 'hover:border-l-[#52a8c5]' }
] as const;

// Helper to get colors by index (safe access)
function getItemColors(index: number): { bg: string; border: string } {
  return ITEM_COLORS[index % ITEM_COLORS.length] as { bg: string; border: string };
}

// Format large numbers (e.g., 15600 -> "15.6k")
function formatCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return String(count);
}

interface RecentModelsProps {
  endpoints: ChatSource[];
  isLoading: boolean;
}

export function RecentModels({ endpoints, isLoading }: Readonly<RecentModelsProps>) {
  // Don't render anything if no endpoints and not loading
  if (!isLoading && endpoints.length === 0) {
    return null;
  }

  return (
    <div>
      <div className='mb-5 flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <div className='h-6 w-1 rounded-full bg-gradient-to-b from-[#f79763] via-[#cc677b] to-[#6976ae]'></div>
          <h4 className='font-rubik text-foreground text-sm tracking-wide uppercase'>Trending</h4>
        </div>
        <Link
          to='/browse'
          className='group text-secondary hover:text-foreground flex items-center gap-1 text-xs transition-colors'
        >
          View all{' '}
          <ArrowRight
            className='h-3 w-3 transition-transform group-hover:translate-x-0.5'
            aria-hidden='true'
          />
        </Link>
      </div>
      <div className='space-y-1.5'>
        {isLoading ? (
          // Loading skeleton
          <>
            {[0, 1, 2, 3].map((index) => (
              <div
                key={index}
                className='flex animate-pulse items-center gap-3 rounded-lg px-4 py-3'
              >
                <div className='bg-muted h-2 w-2 rounded-full'></div>
                <div className='bg-muted h-4 flex-1 rounded'></div>
                <div className='bg-muted h-6 w-12 rounded-full'></div>
              </div>
            ))}
          </>
        ) : (
          endpoints.map((endpoint, index) => {
            const colors = getItemColors(index);
            const href = endpoint.owner_username
              ? `/${endpoint.owner_username}/${endpoint.slug}`
              : '/browse';

            return (
              <Link
                key={endpoint.id}
                to={href}
                title={`View ${endpoint.name}`}
                className={`group hover:bg-syft-surface flex items-center gap-3 rounded-lg border-l-2 border-transparent px-4 py-3 transition-colors transition-shadow ${colors.border} hover:shadow-sm`}
              >
                <div className={`h-2 w-2 rounded-full ${colors.bg} flex-shrink-0`}></div>
                <span className='font-inter text-foreground group-hover:text-foreground flex-1 truncate text-sm transition-colors'>
                  {endpoint.name}
                </span>
                <span
                  className='font-inter bg-accent text-foreground flex shrink-0 items-center gap-1 rounded-full px-3 py-1 text-xs tabular-nums'
                  title={`${String(endpoint.stars_count)} stars`}
                >
                  <Star className='h-3 w-3' aria-hidden='true' />
                  {formatCount(endpoint.stars_count)}
                </span>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}
