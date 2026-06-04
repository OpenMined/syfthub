import { useEffect, useMemo, useRef, useState } from 'react';

import type { CollectiveFilters } from '@/components/collectives/collective-filters-modal';
import type { ReactNode } from 'react';

import Plus from 'lucide-react/dist/esm/icons/plus';
import Search from 'lucide-react/dist/esm/icons/search';
import X from 'lucide-react/dist/esm/icons/x';
import { Link } from 'react-router-dom';

import { BrowseSearchBar } from '@/components/browse-search-bar';
import { CollectiveCard } from '@/components/collectives/collective-card';
import {
  collectiveFilterCount,
  CollectiveFiltersModal,
  createDefaultCollectiveFilters,
  extractCollectiveTags,
  hasActiveCollectiveFilters
} from '@/components/collectives/collective-filters-modal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Pagination,
  PaginationButton,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious
} from '@/components/ui/pagination';
import { usePaginatedCollectives } from '@/hooks/use-collectives';

const PAGE_SIZE = 12;
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Collectives tab of the Browse page. Mirrors the data-source / model tabs:
 * server-side paginated search, with verified / open / tag filters applied
 * client-side over the current page via {@link CollectiveFiltersModal}.
 */
export function CollectivesBrowse() {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<CollectiveFilters>(createDefaultCollectiveFilters);

  const searchDebounceReference = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Debounce the search query for server-side filtering.
  useEffect(() => {
    clearTimeout(searchDebounceReference.current);
    searchDebounceReference.current = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(searchDebounceReference.current);
    };
  }, [searchQuery]);

  const { data, isLoading, error, isFetching } = usePaginatedCollectives(
    page,
    PAGE_SIZE,
    debouncedSearchQuery || undefined
  );

  const collectives = useMemo(() => data?.items ?? [], [data]);
  const hasNextPage = data?.hasNextPage ?? false;
  const hasPreviousPage = page > 1;

  // Tags offered in the filter modal come from the current page.
  const availableTags = useMemo(() => extractCollectiveTags(collectives), [collectives]);

  // Verified / open / tag filters apply client-side over the current page.
  const filteredCollectives = useMemo(() => {
    let result = collectives;
    if (filters.verified) result = result.filter((c) => c.verified);
    if (filters.open) result = result.filter((c) => c.auto_approve);
    if (filters.tags.size > 0) {
      result = result.filter((c) => c.tags.some((tag) => filters.tags.has(tag)));
    }
    return result;
  }, [collectives, filters]);

  const filtersActive = hasActiveCollectiveFilters(filters);
  const activeFilterCount = collectiveFilterCount(filters);

  const handleClearFilters = () => {
    setFilters(createDefaultCollectiveFilters());
  };

  const getNoResultsMessage = () => {
    const hasSearch = debouncedSearchQuery.trim().length > 0;
    if (!hasSearch && !filtersActive) return 'No collectives available';
    const parts: string[] = [];
    if (hasSearch) parts.push('search');
    if (filtersActive) parts.push('filters');
    return `No collectives match your ${parts.join(' and ')}`;
  };

  let content: ReactNode;
  if (isLoading) {
    content = (
      <div className='py-16 text-center'>
        <LoadingSpinner size='lg' message='Loading collectives…' className='justify-center' />
      </div>
    );
  } else if (error) {
    content = (
      <div className='py-16 text-center'>
        <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-50'>
          <Search className='h-8 w-8 text-red-500' />
        </div>
        <h3 className='font-inter text-foreground mb-2 text-lg font-medium'>
          Error Loading Collectives
        </h3>
        <p className='font-inter text-muted-foreground'>
          {error instanceof Error ? error.message : 'Failed to load collectives'}
        </p>
      </div>
    );
  } else if (filteredCollectives.length === 0) {
    content = (
      <div className='py-16 text-center'>
        <div className='bg-muted mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full'>
          <Search className='text-muted-foreground h-8 w-8' />
        </div>
        <h3 className='font-inter text-foreground mb-2 text-lg font-medium'>No Results Found</h3>
        <p className='font-inter text-muted-foreground'>{getNoResultsMessage()}</p>
        {filtersActive ? (
          <button
            type='button'
            onClick={handleClearFilters}
            className='font-inter text-primary hover:text-primary/80 mt-4 text-sm underline transition-colors'
          >
            Clear all filters
          </button>
        ) : (
          <Button asChild className='mt-4'>
            <Link to='/collectives/create'>
              <Plus className='mr-2 h-4 w-4' />
              Create a collective
            </Link>
          </Button>
        )}
      </div>
    );
  } else {
    content = (
      <>
        <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {filteredCollectives.map((collective) => (
            <CollectiveCard key={collective.id} collective={collective} />
          ))}
        </div>

        {(hasPreviousPage || hasNextPage) && (
          <div className='mt-8'>
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    onClick={() => {
                      setPage((p) => Math.max(1, p - 1));
                    }}
                    disabled={!hasPreviousPage || isFetching}
                    aria-disabled={!hasPreviousPage}
                  />
                </PaginationItem>
                <PaginationItem>
                  <PaginationButton isActive disabled className='pointer-events-none'>
                    {page}
                  </PaginationButton>
                </PaginationItem>
                <PaginationItem>
                  <PaginationNext
                    onClick={() => {
                      if (hasNextPage) setPage((p) => p + 1);
                    }}
                    disabled={!hasNextPage || isFetching}
                    aria-disabled={!hasNextPage}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <BrowseSearchBar
        searchId='collective-search'
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchLabel='Search collectives'
        searchPlaceholder='Search collectives…'
        onOpenFilters={() => {
          setIsFiltersOpen(true);
        }}
        filtersActive={filtersActive}
        activeFilterCount={activeFilterCount}
      />

      {/* Active filters bar */}
      {filtersActive && (
        <div className='mb-4 flex flex-wrap items-center gap-2'>
          <span className='font-inter text-muted-foreground text-sm'>Active filters:</span>
          {filters.verified && (
            <Badge variant='secondary' className='font-inter flex items-center gap-1 text-xs'>
              Verified
              <button
                type='button'
                onClick={() => {
                  setFilters((previous) => ({ ...previous, verified: false }));
                }}
                className='hover:text-foreground ml-0.5'
                aria-label='Remove verified filter'
              >
                <X className='h-3 w-3' />
              </button>
            </Badge>
          )}
          {filters.open && (
            <Badge variant='secondary' className='font-inter flex items-center gap-1 text-xs'>
              Open to join
              <button
                type='button'
                onClick={() => {
                  setFilters((previous) => ({ ...previous, open: false }));
                }}
                className='hover:text-foreground ml-0.5'
                aria-label='Remove open-to-join filter'
              >
                <X className='h-3 w-3' />
              </button>
            </Badge>
          )}
          {[...filters.tags].map((tag) => (
            <Badge
              key={tag}
              variant='secondary'
              className='font-inter flex items-center gap-1 text-xs'
            >
              {tag}
              <button
                type='button'
                onClick={() => {
                  setFilters((previous) => {
                    const nextTags = new Set(previous.tags);
                    nextTags.delete(tag);
                    return { ...previous, tags: nextTags };
                  });
                }}
                className='hover:text-foreground ml-0.5'
                aria-label={`Remove ${tag} filter`}
              >
                <X className='h-3 w-3' />
              </button>
            </Badge>
          ))}
          <button
            type='button'
            onClick={handleClearFilters}
            className='font-inter text-muted-foreground hover:text-foreground ml-2 text-sm underline transition-colors'
          >
            Clear all
          </button>
        </div>
      )}

      {/* Page info */}
      {!isLoading && !error && filteredCollectives.length > 0 && (
        <div className='text-muted-foreground mb-4 flex items-center justify-between'>
          <span className='font-inter text-sm'>
            Page {page}
            {isFetching && <span className='text-muted-foreground/60 ml-2'>(loading...)</span>}
          </span>
          <span className='font-inter text-sm'>
            {filteredCollectives.length} {filteredCollectives.length === 1 ? 'result' : 'results'}
            {debouncedSearchQuery && ' (search results)'}
          </span>
        </div>
      )}

      {content}

      <CollectiveFiltersModal
        isOpen={isFiltersOpen}
        onClose={() => {
          setIsFiltersOpen(false);
        }}
        onApply={(next) => {
          setFilters(next);
          setIsFiltersOpen(false);
        }}
        currentFilters={filters}
        availableTags={availableTags}
      />
    </>
  );
}
