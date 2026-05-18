import { useMemo, useState } from 'react';

import type { Collective } from '@/lib/collectives-api';
import type { ReactNode } from 'react';

import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Search from 'lucide-react/dist/esm/icons/search';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link } from 'react-router-dom';

import { CollectiveCard } from '@/components/collectives/collective-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useCollectives } from '@/hooks/use-collectives';

type FilterType = 'all' | 'verified' | 'open';
type SortType = 'relevance' | 'members' | 'newest';

const FILTER_LABELS: Record<FilterType, string> = {
  all: 'All',
  verified: 'Verified',
  open: 'Open to join'
};

/**
 * Browse and discover collectives (`/collectives/browse`).
 *
 * The backend list endpoint has no search; filtering, sorting and tag
 * selection are applied client-side over the fetched page (limit 100).
 */
export default function BrowseCollectivesPage() {
  const { data: collectives, isLoading, isError, error } = useCollectives();

  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<SortType>('relevance');
  const [selectedTag, setSelectedTag] = useState('');

  // Eight most common tags across all collectives.
  const allTags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const collective of collectives ?? []) {
      for (const tag of collective.tags) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .toSorted((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([tag]) => tag);
  }, [collectives]);

  const filtered = useMemo(() => {
    let result: Collective[] = [...(collectives ?? [])];

    const query = searchQuery.trim().toLowerCase();
    if (query) {
      result = result.filter(
        (c) =>
          c.name.toLowerCase().includes(query) ||
          c.description.toLowerCase().includes(query) ||
          c.tags.some((tag) => tag.toLowerCase().includes(query))
      );
    }

    if (filterType === 'verified') {
      result = result.filter((c) => c.verified);
    } else if (filterType === 'open') {
      result = result.filter((c) => c.auto_approve);
    }

    if (selectedTag) {
      result = result.filter((c) => c.tags.includes(selectedTag));
    }

    result = result.toSorted((a, b) => {
      switch (sortBy) {
        case 'relevance': {
          if (a.verified !== b.verified) return a.verified ? -1 : 1;
          return b.member_count - a.member_count;
        }
        case 'members': {
          return b.member_count - a.member_count;
        }
        case 'newest': {
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        default: {
          return 0;
        }
      }
    });

    return result;
  }, [collectives, searchQuery, filterType, selectedTag, sortBy]);

  const hasActiveFilters = Boolean(searchQuery || selectedTag || filterType !== 'all');

  const resultCount = (
    <div className='text-muted-foreground mb-4 text-sm'>
      {filtered.length} collective{filtered.length === 1 ? '' : 's'} found
    </div>
  );

  let resultsView: ReactNode;
  if (isLoading) {
    resultsView = (
      <div className='flex justify-center py-16'>
        <LoadingSpinner />
      </div>
    );
  } else if (isError) {
    resultsView = (
      <div className='py-12 text-center'>
        <p className='text-destructive mb-4'>
          {error instanceof Error ? error.message : 'Failed to load collectives'}
        </p>
      </div>
    );
  } else if (filtered.length > 0) {
    resultsView = (
      <>
        {resultCount}
        <div className='grid grid-cols-1 gap-4 md:grid-cols-2'>
          {filtered.map((collective) => (
            <CollectiveCard key={collective.id} collective={collective} />
          ))}
        </div>
      </>
    );
  } else {
    resultsView = (
      <>
        {resultCount}
        <div className='py-12 text-center'>
          <Users className='text-muted-foreground mx-auto mb-4 h-12 w-12' />
          <p className='text-muted-foreground mb-4'>No collectives found</p>
          {hasActiveFilters ? (
            <Button
              variant='outline'
              onClick={() => {
                setSearchQuery('');
                setSelectedTag('');
                setFilterType('all');
              }}
            >
              Clear filters
            </Button>
          ) : (
            <Button asChild>
              <Link to='/collectives/create'>Create the first one</Link>
            </Button>
          )}
        </div>
      </>
    );
  }

  return (
    <div className='container mx-auto max-w-6xl px-6 py-8'>
      <div className='mb-8'>
        <h1 className='mb-2 text-2xl font-bold'>Browse Collectives</h1>
        <p className='text-muted-foreground'>
          Find collectives grouping endpoints around a shared identity
        </p>
      </div>

      {/* Search + filters */}
      <div className='mb-8 space-y-4'>
        <div className='flex gap-3'>
          <div className='relative flex-1'>
            <Search className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2' />
            <Input
              placeholder='Search collectives...'
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              className='pl-10'
            />
          </div>
          <Button asChild variant='outline'>
            <Link to='/collectives/create'>
              <Plus className='mr-2 h-4 w-4' />
              Create
            </Link>
          </Button>
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <span className='text-muted-foreground text-sm'>Filter:</span>
          {(['all', 'verified', 'open'] as FilterType[]).map((type) => (
            <Button
              key={type}
              variant={filterType === type ? 'default' : 'outline'}
              size='sm'
              onClick={() => {
                setFilterType(type);
              }}
              className='h-8'
            >
              {type === 'verified' && <CheckCircle className='mr-1 h-3 w-3' />}
              {FILTER_LABELS[type]}
            </Button>
          ))}

          <div className='ml-auto'>
            <select
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value as SortType);
              }}
              className='border-input bg-background h-8 rounded-md border px-3 text-sm'
              aria-label='Sort collectives'
            >
              <option value='relevance'>Most relevant</option>
              <option value='members'>Most endpoints</option>
              <option value='newest'>Newest</option>
            </select>
          </div>
        </div>

        {allTags.length > 0 && (
          <div className='flex flex-wrap items-center gap-2'>
            <span className='text-muted-foreground text-sm'>Topics:</span>
            <Badge
              variant={selectedTag ? 'outline' : 'default'}
              className='cursor-pointer text-xs'
              onClick={() => {
                setSelectedTag('');
              }}
            >
              All
            </Badge>
            {allTags.map((tag) => (
              <Badge
                key={tag}
                variant={selectedTag === tag ? 'default' : 'outline'}
                className='cursor-pointer text-xs'
                onClick={() => {
                  setSelectedTag(tag === selectedTag ? '' : tag);
                }}
              >
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Results */}
      {resultsView}
    </div>
  );
}
