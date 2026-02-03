import { useCallback, useMemo, useState } from 'react';

import type { ChatSource, EndpointType } from '@/lib/types';

import Building from 'lucide-react/dist/esm/icons/building';
import Calendar from 'lucide-react/dist/esm/icons/calendar';
import Check from 'lucide-react/dist/esm/icons/check';
import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right';
import Database from 'lucide-react/dist/esm/icons/database';
import Filter from 'lucide-react/dist/esm/icons/filter';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Package from 'lucide-react/dist/esm/icons/package';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Search from 'lucide-react/dist/esm/icons/search';
import Sparkles from 'lucide-react/dist/esm/icons/sparkles';
import Star from 'lucide-react/dist/esm/icons/star';
import { Link } from 'react-router-dom';

import { usePublicEndpoints } from '@/hooks/use-endpoint-queries';
import { isDataSourceEndpoint, isModelEndpoint } from '@/lib/endpoint-utils';
import { useContextSelectionStore } from '@/stores/context-selection-store';

import { Badge } from './ui/badge';
import { LoadingSpinner } from './ui/loading-spinner';
import { PageHeader } from './ui/page-header';

// ============================================================================
// Helper functions
// ============================================================================

function getStatusColor(status: 'active' | 'warning' | 'inactive') {
  switch (status) {
    case 'active': {
      return 'bg-green-500';
    }
    case 'warning': {
      return 'bg-yellow-500';
    }
    case 'inactive': {
      return 'bg-red-500';
    }
    default: {
      return 'bg-muted-foreground';
    }
  }
}

function getTypeStyles(type: EndpointType) {
  switch (type) {
    case 'model': {
      return 'bg-purple-100 text-purple-800 border-purple-200 hover:bg-purple-200';
    }
    case 'data_source': {
      return 'bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-200';
    }
    case 'model_data_source': {
      return 'bg-blue-100 text-blue-800 border-blue-200 hover:bg-blue-200';
    }
    default: {
      return 'bg-muted text-muted-foreground border-border';
    }
  }
}

function getTypeLabel(type: EndpointType) {
  switch (type) {
    case 'model': {
      return 'Model';
    }
    case 'data_source': {
      return 'Data Source';
    }
    case 'model_data_source': {
      return 'Model + Data Source';
    }
    default: {
      return type;
    }
  }
}

// ============================================================================
// Tab types
// ============================================================================

type BrowseTab = 'data_sources' | 'models';

// ============================================================================
// Main Component
// ============================================================================

interface BrowseViewProperties {
  initialQuery?: string;
  onAuthRequired?: () => void;
}

export function BrowseView({
  initialQuery = '',
  onAuthRequired: _onAuthRequired
}: Readonly<BrowseViewProperties>) {
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [activeTab, setActiveTab] = useState<BrowseTab>('data_sources');

  // Context selection store
  const toggleSource = useContextSelectionStore((s) => s.toggleSource);
  const isSelected = useContextSelectionStore((s) => s.isSelected);
  const selectedCount = useContextSelectionStore((s) => s.count);

  // Fetch endpoints using TanStack Query
  const { data: endpoints, isLoading, error } = usePublicEndpoints(50);

  // Filter endpoints based on tab and search query
  const filteredEndpoints = useMemo(() => {
    if (!endpoints) return [];

    // First filter by tab
    let filtered = endpoints.filter((ep) => {
      if (activeTab === 'data_sources') return isDataSourceEndpoint(ep.type);
      return isModelEndpoint(ep.type);
    });

    // Then filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (ds) =>
          ds.name.toLowerCase().includes(query) ||
          ds.description.toLowerCase().includes(query) ||
          ds.tags.some((tag) => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  }, [endpoints, searchQuery, activeTab]);

  const getVisibilityIcon = (endpoint: ChatSource) => {
    if (endpoint.name.toLowerCase().includes('private')) {
      return <Lock className='h-3 w-3' />;
    } else if (endpoint.name.toLowerCase().includes('internal')) {
      return <Building className='h-3 w-3' />;
    }
    return <Globe className='h-3 w-3' />;
  };

  const handleToggleSource = useCallback(
    (endpoint: ChatSource) => {
      toggleSource(endpoint);
    },
    [toggleSource]
  );

  // Count endpoints by type for tab badges
  const typeCounts = useMemo(() => {
    if (!endpoints) return { data_sources: 0, models: 0 };
    return {
      data_sources: endpoints.filter((ep) => isDataSourceEndpoint(ep.type)).length,
      models: endpoints.filter((ep) => isModelEndpoint(ep.type)).length
    };
  }, [endpoints]);

  return (
    <div className='bg-background min-h-screen pb-24'>
      <PageHeader title='Browse' path='~/browse' />

      {/* Main Content */}
      <div className='mx-auto max-w-6xl px-6 py-8'>
        {/* Header */}
        <div className='mb-8'>
          <h1 className='font-rubik text-foreground mb-2 text-3xl font-semibold'>Browse Library</h1>
          <p className='font-inter text-muted-foreground'>
            Discover trusted data sources and AI models
          </p>
        </div>

        {/* Tabs */}
        <div className='mb-6 flex items-center gap-1'>
          <button
            type='button'
            onClick={() => {
              setActiveTab('data_sources');
            }}
            className={`font-inter flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'data_sources'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            <Database className='h-4 w-4' aria-hidden='true' />
            Data Sources
            {typeCounts.data_sources > 0 && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                  activeTab === 'data_sources'
                    ? 'bg-primary-foreground/20 text-primary-foreground'
                    : 'bg-muted-foreground/10 text-muted-foreground'
                }`}
              >
                {typeCounts.data_sources}
              </span>
            )}
          </button>
          <button
            type='button'
            onClick={() => {
              setActiveTab('models');
            }}
            className={`font-inter flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'models'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            <Sparkles className='h-4 w-4' aria-hidden='true' />
            Models
            {typeCounts.models > 0 && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                  activeTab === 'models'
                    ? 'bg-primary-foreground/20 text-primary-foreground'
                    : 'bg-muted-foreground/10 text-muted-foreground'
                }`}
              >
                {typeCounts.models}
              </span>
            )}
          </button>
        </div>

        {/* Search and Filter Bar */}
        <div className='mb-8 flex gap-4'>
          <div className='relative flex-1'>
            <label htmlFor='endpoint-search' className='sr-only'>
              Search endpoints
            </label>
            <Search
              className='text-muted-foreground absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2'
              aria-hidden='true'
            />
            <input
              id='endpoint-search'
              type='search'
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder={`Search ${activeTab === 'data_sources' ? 'data sources' : 'models'}…`}
              className='font-inter border-border focus:border-primary focus:ring-ring/10 w-full rounded-xl border py-3 pr-4 pl-11 transition-colors transition-shadow focus:ring-2 focus:outline-none'
            />
          </div>
          <button
            type='button'
            className='font-inter border-border text-muted-foreground hover:bg-muted flex items-center gap-2 rounded-xl border px-4 py-3 transition-colors'
          >
            <Filter className='h-5 w-5' aria-hidden='true' />
            Filters
          </button>
        </div>

        {/* Results count */}
        {!isLoading && !error && filteredEndpoints.length > 0 && (
          <div className='text-muted-foreground mb-4 text-right'>
            <span className='font-inter text-sm'>{filteredEndpoints.length} results</span>
          </div>
        )}

        {/* Content */}
        {isLoading ? (
          <div className='py-16 text-center'>
            <LoadingSpinner size='lg' message='Loading endpoints…' className='justify-center' />
          </div>
        ) : null}
        {!isLoading && error ? (
          <div className='py-16 text-center'>
            <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-50'>
              <Search className='h-8 w-8 text-red-500' />
            </div>
            <h3 className='font-inter text-foreground mb-2 text-lg font-medium'>
              Error Loading Endpoints
            </h3>
            <p className='font-inter text-muted-foreground'>{error.message}</p>
          </div>
        ) : null}
        {!isLoading && !error && filteredEndpoints.length === 0 ? (
          <div className='py-16 text-center'>
            <div className='bg-muted mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full'>
              <Search className='text-muted-foreground h-8 w-8' />
            </div>
            <h3 className='font-inter text-foreground mb-2 text-lg font-medium'>
              No Results Found
            </h3>
            <p className='font-inter text-muted-foreground'>
              {searchQuery
                ? `No ${activeTab === 'data_sources' ? 'data sources' : 'models'} match "${searchQuery}"`
                : `No ${activeTab === 'data_sources' ? 'data sources' : 'models'} available`}
            </p>
          </div>
        ) : null}
        {!isLoading && !error && filteredEndpoints.length > 0 ? (
          <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
            {filteredEndpoints.map((endpoint) => {
              const canAddToContext = isDataSourceEndpoint(endpoint.type);
              const selected = canAddToContext && isSelected(endpoint.id);
              const detailHref = endpoint.owner_username
                ? `/${endpoint.owner_username}/${endpoint.slug}`
                : `/browse/${endpoint.slug}`;

              return (
                <div
                  key={endpoint.id}
                  className={`group relative rounded-xl border p-5 transition-all ${
                    selected
                      ? 'border-primary bg-primary/5 border-dashed shadow-sm'
                      : 'border-border bg-card hover:shadow-md'
                  }`}
                >
                  {/* Add to Context / Selected toggle button (data sources only) */}
                  {canAddToContext && (
                    <button
                      type='button'
                      onClick={() => {
                        handleToggleSource(endpoint);
                      }}
                      aria-pressed={selected}
                      aria-label={
                        selected
                          ? `Remove ${endpoint.name} from context`
                          : `Add ${endpoint.name} to context`
                      }
                      className={`absolute top-3 right-3 z-10 flex h-7 w-7 items-center justify-center rounded-full border transition-all ${
                        selected
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-card text-muted-foreground hover:border-primary hover:text-primary'
                      }`}
                    >
                      {selected ? <Check className='h-4 w-4' /> : <Plus className='h-4 w-4' />}
                    </button>
                  )}

                  {/* Card content is a Link for navigation */}
                  <Link to={detailHref} className='block'>
                    {/* Header */}
                    <div className='mb-3 flex items-start justify-between'>
                      <div className='min-w-0 flex-1 pr-8'>
                        <h3 className='font-inter text-foreground group-hover:text-primary truncate text-base font-semibold'>
                          {endpoint.name}
                        </h3>
                        {endpoint.owner_username && (
                          <p className='font-inter text-muted-foreground mt-0.5 truncate text-xs'>
                            by @{endpoint.owner_username}
                          </p>
                        )}
                        <p className='font-inter text-muted-foreground mt-1.5 line-clamp-2 text-sm'>
                          {endpoint.description}
                        </p>
                      </div>
                      <ChevronRight
                        className='text-muted-foreground mt-1 h-5 w-5 shrink-0 transition-transform group-hover:translate-x-0.5'
                        aria-hidden='true'
                      />
                    </div>

                    {/* Tags and Status */}
                    <div className='mb-3 flex flex-wrap items-center gap-2'>
                      <Badge
                        variant='outline'
                        className={`font-inter border text-xs ${getTypeStyles(endpoint.type)}`}
                      >
                        {getTypeLabel(endpoint.type)}
                      </Badge>
                      {endpoint.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} variant='secondary' className='font-inter text-xs'>
                          {tag}
                        </Badge>
                      ))}
                      {endpoint.tags.length > 3 && (
                        <Badge variant='secondary' className='font-inter text-xs'>
                          +{endpoint.tags.length - 3}
                        </Badge>
                      )}
                      <div className='flex items-center gap-1'>
                        <div
                          className={`h-2 w-2 rounded-full ${getStatusColor(endpoint.status)}`}
                        />
                        <span className='text-muted-foreground font-inter text-xs capitalize'>
                          {endpoint.status}
                        </span>
                      </div>
                    </div>

                    {/* Footer Info */}
                    <div className='border-muted flex items-center justify-between border-t pt-3'>
                      <div className='text-muted-foreground flex items-center gap-3 text-xs'>
                        <div className='flex items-center gap-1'>
                          {getVisibilityIcon(endpoint)}
                          <span>Public</span>
                        </div>
                        <div className='flex items-center gap-1'>
                          <Package className='h-3 w-3' aria-hidden='true' />
                          <span>v{endpoint.version}</span>
                        </div>
                      </div>
                      <div className='text-muted-foreground flex items-center gap-3 text-xs'>
                        {endpoint.stars_count > 0 && (
                          <div className='flex items-center gap-1'>
                            <Star className='h-3 w-3' aria-hidden='true' />
                            <span>{endpoint.stars_count}</span>
                          </div>
                        )}
                        <div className='flex items-center gap-1'>
                          <Calendar className='h-3 w-3' aria-hidden='true' />
                          <span>{endpoint.updated}</span>
                        </div>
                      </div>
                    </div>
                  </Link>
                </div>
              );
            })}
          </div>
        ) : null}

        {/* Bottom spacer when context bar is visible */}
        {selectedCount() > 0 && <div className='h-16' />}
      </div>
    </div>
  );
}
