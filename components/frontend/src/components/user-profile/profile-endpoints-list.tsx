import { useEffect, useMemo, useState } from 'react';

import type { ChatSource, EndpointType } from '@/lib/types';

import Calendar from 'lucide-react/dist/esm/icons/calendar';
import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right';
import Package from 'lucide-react/dist/esm/icons/package';
import Star from 'lucide-react/dist/esm/icons/star';
import { Link } from 'react-router-dom';

import { EndpointTypeIcon } from '@/components/endpoint-type-icon';
import { Badge } from '@/components/ui/badge';
import {
  Pagination,
  PaginationButton,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious
} from '@/components/ui/pagination';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { isDataSourceEndpoint, isModelEndpoint } from '@/lib/endpoint-utils';

type Filter = 'all' | 'model' | 'data_source' | 'agent';
type SortKey = 'updated' | 'stars' | 'name';

const PAGE_SIZE = 20;

interface ProfileEndpointsListProps {
  username: string;
  endpoints: ChatSource[];
  isOwnProfile: boolean;
}

function matchesFilter(endpoint: ChatSource, filter: Filter): boolean {
  if (filter === 'all') return true;
  if (filter === 'model') return isModelEndpoint(endpoint.type);
  if (filter === 'data_source') return isDataSourceEndpoint(endpoint.type);
  return endpoint.type === 'agent';
}

function countByType(endpoints: ChatSource[], type: EndpointType): number {
  return endpoints.filter((ep) => ep.type === type).length;
}

export function ProfileEndpointsList({
  username,
  endpoints,
  isOwnProfile
}: Readonly<ProfileEndpointsListProps>) {
  const [filter, setFilter] = useState<Filter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('updated');
  const [page, setPage] = useState(1);

  // Reset to first page when filter or sort changes — otherwise users can land
  // on a page that no longer exists for the new filter.
  useEffect(() => {
    setPage(1);
  }, [filter, sortKey]);

  const counts = useMemo(
    () => ({
      all: endpoints.length,
      model: countByType(endpoints, 'model'),
      data_source: countByType(endpoints, 'data_source'),
      model_data_source: countByType(endpoints, 'model_data_source'),
      agent: countByType(endpoints, 'agent')
    }),
    [endpoints]
  );

  const filtered = useMemo(() => {
    const matched = endpoints.filter((ep) => matchesFilter(ep, filter));
    if (sortKey === 'stars') return matched.toSorted((a, b) => b.stars_count - a.stars_count);
    if (sortKey === 'name') return matched.toSorted((a, b) => a.name.localeCompare(b.name));
    const withTs = matched.map((ep) => [Date.parse(ep.updated_at), ep] as const);
    withTs.sort((a, b) => b[0] - a[0]);
    return withTs.map(([, ep]) => ep);
  }, [endpoints, filter, sortKey]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, filtered.length);
  const paginated = filtered.slice(pageStart, pageEnd);

  // Hide tabs that have zero endpoints (avoid noisy filter strip).
  const allTabs: { value: Filter; label: string; count: number }[] = [
    { value: 'all', label: 'All', count: counts.all },
    { value: 'model', label: 'Models', count: counts.model + counts.model_data_source },
    {
      value: 'data_source',
      label: 'Data Sources',
      count: counts.data_source + counts.model_data_source
    },
    { value: 'agent', label: 'Agents', count: counts.agent }
  ];
  const tabConfig = allTabs.filter((tab) => tab.value === 'all' || tab.count > 0);

  const getEmptyMessage = (): string => {
    if (endpoints.length > 0) return 'No endpoints match the current filter.';
    if (isOwnProfile) return "You haven't published any endpoints yet.";
    return `@${username} hasn't published any endpoints yet.`;
  };

  return (
    <section aria-labelledby='profile-endpoints-heading' className='space-y-4'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <h2
          id='profile-endpoints-heading'
          className='font-rubik text-foreground text-xl font-medium'
        >
          Endpoints
          <span className='text-muted-foreground ml-2 text-sm font-normal'>{endpoints.length}</span>
        </h2>

        <div className='flex flex-wrap items-center gap-3'>
          <Tabs
            value={filter}
            onValueChange={(value) => {
              setFilter(value as Filter);
            }}
          >
            <TabsList className='gap-1 bg-transparent'>
              {tabConfig.map((tab) => (
                <TabsTrigger
                  key={tab.value}
                  value={tab.value}
                  className='font-inter data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:bg-muted data-[state=inactive]:hover:text-foreground flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs data-[state=active]:shadow-none'
                >
                  {tab.label}
                  <span className='text-[10px] tabular-nums opacity-70'>{tab.count}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <label className='flex items-center gap-2 text-xs'>
            <span className='font-inter text-muted-foreground'>Sort</span>
            <select
              value={sortKey}
              onChange={(e) => {
                setSortKey(e.target.value as SortKey);
              }}
              className='font-inter border-border bg-background text-foreground focus:ring-ring/30 rounded-md border px-2 py-1.5 text-xs focus:ring-2 focus:outline-none'
              aria-label='Sort endpoints'
            >
              <option value='updated'>Recently updated</option>
              <option value='stars'>Most stars</option>
              <option value='name'>Name (A–Z)</option>
            </select>
          </label>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className='border-border bg-card rounded-xl border p-10 text-center'>
          <p className='font-inter text-muted-foreground text-sm'>{getEmptyMessage()}</p>
        </div>
      ) : (
        <ul
          className='border-border bg-card divide-border divide-y rounded-xl border'
          aria-label={`Public endpoints for @${username}`}
        >
          {paginated.map((endpoint) => (
            <li key={endpoint.id}>
              <Link
                to={`/${username}/${endpoint.slug}`}
                className='group flex items-start gap-4 p-4 transition-colors hover:bg-[var(--accent)]'
              >
                <div className='mt-1'>
                  <EndpointTypeIcon type={endpoint.type} />
                </div>

                <div className='min-w-0 flex-1'>
                  <div className='flex flex-wrap items-baseline gap-x-2 gap-y-1'>
                    <h3 className='font-inter text-foreground group-hover:text-primary truncate text-sm font-semibold transition-colors'>
                      {endpoint.name}
                    </h3>
                    <span className='text-muted-foreground font-mono text-xs'>
                      @{username}/{endpoint.slug}
                    </span>
                  </div>

                  {endpoint.description ? (
                    <p className='font-inter text-muted-foreground mt-1 line-clamp-2 text-xs'>
                      {endpoint.description}
                    </p>
                  ) : null}

                  {endpoint.tags.length > 0 ? (
                    <div className='mt-2 flex flex-wrap gap-1'>
                      {endpoint.tags.slice(0, 4).map((tag) => (
                        <Badge
                          key={tag}
                          variant='secondary'
                          className='font-inter px-1.5 py-0 text-[10px]'
                        >
                          {tag}
                        </Badge>
                      ))}
                      {endpoint.tags.length > 4 ? (
                        <Badge variant='secondary' className='font-inter px-1.5 py-0 text-[10px]'>
                          +{endpoint.tags.length - 4}
                        </Badge>
                      ) : null}
                    </div>
                  ) : null}
                </div>

                <div className='hidden flex-shrink-0 flex-col items-end gap-1 text-xs sm:flex'>
                  <div className='text-muted-foreground flex items-center gap-3'>
                    {endpoint.stars_count > 0 ? (
                      <span className='inline-flex items-center gap-1 tabular-nums'>
                        <Star className='h-3 w-3' aria-hidden='true' />
                        {endpoint.stars_count}
                      </span>
                    ) : null}
                    <span className='inline-flex items-center gap-1'>
                      <Package className='h-3 w-3' aria-hidden='true' />v{endpoint.version}
                    </span>
                  </div>
                  <span className='text-muted-foreground inline-flex items-center gap-1'>
                    <Calendar className='h-3 w-3' aria-hidden='true' />
                    {endpoint.updated}
                  </span>
                </div>

                <ChevronRight
                  className='text-muted-foreground/60 mt-1 h-4 w-4 flex-shrink-0 transition-transform group-hover:translate-x-0.5'
                  aria-hidden='true'
                />
              </Link>
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 ? (
        <div className='flex flex-col items-center gap-3 pt-2 sm:flex-row sm:justify-between'>
          <p className='font-inter text-muted-foreground text-xs tabular-nums' aria-live='polite'>
            Showing {pageStart + 1}–{pageEnd} of {filtered.length}
          </p>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => {
                    setPage((p) => Math.max(1, p - 1));
                  }}
                  disabled={safePage === 1}
                  aria-disabled={safePage === 1}
                />
              </PaginationItem>
              <PaginationItem>
                <PaginationButton isActive disabled className='pointer-events-none'>
                  {safePage} / {totalPages}
                </PaginationButton>
              </PaginationItem>
              <PaginationItem>
                <PaginationNext
                  onClick={() => {
                    setPage((p) => Math.min(totalPages, p + 1));
                  }}
                  disabled={safePage === totalPages}
                  aria-disabled={safePage === totalPages}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      ) : null}
    </section>
  );
}
