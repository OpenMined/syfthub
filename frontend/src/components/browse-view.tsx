import { useMemo, useState } from 'react';

import type { ChatSource, EndpointType } from '@/lib/types';

import {
  Building,
  Calendar,
  ChevronRight,
  Filter,
  Globe,
  Lock,
  Package,
  Search,
  Star
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { useAPI } from '@/hooks/use-api';
import { getPublicEndpoints } from '@/lib/endpoint-utils';

import { Badge } from './ui/badge';
import { LoadingSpinner } from './ui/loading-spinner';
import { PageHeader } from './ui/page-header';

// Helper functions moved outside component for consistent-function-scoping
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
      return 'bg-gray-500';
    }
  }
}

function getTypeStyles(type: EndpointType) {
  switch (type) {
    case 'model': {
      return 'bg-purple-100 text-purple-800 border-purple-200';
    }
    case 'data_source': {
      return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    }
    default: {
      return 'bg-gray-100 text-gray-800 border-gray-200';
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
    default: {
      return type;
    }
  }
}

interface BrowseViewProperties {
  initialQuery?: string;
  onAuthRequired?: () => void;
}

export function BrowseView({
  initialQuery = '',
  onAuthRequired: _onAuthRequired
}: Readonly<BrowseViewProperties>) {
  const [searchQuery, setSearchQuery] = useState(initialQuery);

  // Fetch endpoints using useAPI hook
  const {
    data: endpoints,
    isLoading,
    error
  } = useAPI(() => getPublicEndpoints({ limit: 50 }), { immediate: true });

  // Filter endpoints based on search query using useMemo for performance
  const filteredEndpoints = useMemo(() => {
    if (!endpoints) return [];
    if (!searchQuery.trim()) return endpoints;

    const query = searchQuery.toLowerCase();
    return endpoints.filter(
      (ds) =>
        ds.name.toLowerCase().includes(query) ||
        ds.description.toLowerCase().includes(query) ||
        ds.tags.some((tag) => tag.toLowerCase().includes(query))
    );
  }, [endpoints, searchQuery]);

  const getVisibilityIcon = (endpoint: ChatSource) => {
    // Since we're showing public endpoints, they're all public
    // But we can infer from the name/tag for demonstration
    if (endpoint.name.toLowerCase().includes('private')) {
      return <Lock className='h-3 w-3' />;
    } else if (endpoint.name.toLowerCase().includes('internal')) {
      return <Building className='h-3 w-3' />;
    }
    return <Globe className='h-3 w-3' />;
  };

  return (
    <div className='bg-syft-background min-h-screen'>
      <PageHeader title='Browse' path='~/browse' />

      {/* Main Content */}
      <div className='mx-auto max-w-6xl px-6 py-8'>
        {/* Header */}
        <div className='mb-8'>
          <h1 className='font-rubik text-syft-primary mb-2 text-3xl font-semibold'>
            Browse Data Sources & Models
          </h1>
          <p className='font-inter text-syft-muted'>
            Discover and explore trusted data sources and models from the community
          </p>
        </div>

        {/* Search and Filter Bar */}
        <div className='mb-8 flex gap-4'>
          <div className='relative flex-1'>
            <label htmlFor='endpoint-search' className='sr-only'>
              Search endpoints
            </label>
            <Search
              className='text-syft-placeholder absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2'
              aria-hidden='true'
            />
            <input
              id='endpoint-search'
              type='search'
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder='Search data sources…'
              className='font-inter border-syft-border focus:border-syft-primary focus:ring-syft-primary/10 w-full rounded-xl border py-3 pr-4 pl-11 transition-all focus:ring-2 focus:outline-none'
            />
          </div>
          <button
            type='button'
            className='font-inter border-syft-border text-syft-muted hover:bg-syft-surface flex items-center gap-2 rounded-xl border px-4 py-3 transition-colors'
          >
            <Filter className='h-5 w-5' aria-hidden='true' />
            Filter
          </button>
        </div>

        {/* Content */}
        {isLoading && (
          <div className='py-16 text-center'>
            <LoadingSpinner size='lg' message='Loading endpoints...' className='justify-center' />
          </div>
        )}
        {!isLoading && error && (
          <div className='py-16 text-center'>
            <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-50'>
              <Search className='h-8 w-8 text-red-500' />
            </div>
            <h3 className='font-inter mb-2 text-lg font-medium text-gray-900'>
              Error Loading Endpoints
            </h3>
            <p className='font-inter text-syft-muted'>{error.message}</p>
          </div>
        )}
        {!isLoading && !error && filteredEndpoints.length === 0 && (
          <div className='py-16 text-center'>
            <div className='bg-syft-surface mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full'>
              <Search className='text-syft-muted h-8 w-8' />
            </div>
            <h3 className='font-inter text-syft-primary mb-2 text-lg font-medium'>
              No Results Found
            </h3>
            <p className='font-inter text-syft-muted'>
              {searchQuery ? `No endpoints match "${searchQuery}"` : 'No endpoints available'}
            </p>
          </div>
        )}
        {!isLoading && !error && filteredEndpoints.length > 0 && (
          <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
            {filteredEndpoints.map((endpoint) => {
              const href = endpoint.owner_username
                ? `/${endpoint.owner_username}/${endpoint.slug}`
                : `/browse/${endpoint.slug}`;
              return (
                <Link
                  key={endpoint.id}
                  to={href}
                  className='group border-syft-border hover:border-syft-secondary block rounded-xl border bg-white p-5 transition-all hover:shadow-md'
                >
                  {/* Header */}
                  <div className='mb-3 flex items-start justify-between'>
                    <div className='min-w-0 flex-1'>
                      <h3 className='font-inter text-syft-primary group-hover:text-syft-secondary mb-1 truncate text-base font-semibold'>
                        {endpoint.name}
                      </h3>
                      {endpoint.owner_username && (
                        <p className='font-inter text-syft-placeholder truncate text-xs'>
                          by @{endpoint.owner_username}
                        </p>
                      )}
                      <p className='font-inter text-syft-muted line-clamp-2 text-sm'>
                        {endpoint.description}
                      </p>
                    </div>
                    <ChevronRight
                      className='text-syft-placeholder group-hover:text-syft-secondary ml-2 h-5 w-5 shrink-0 transition-transform group-hover:translate-x-1'
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
                      <div className={`h-2 w-2 rounded-full ${getStatusColor(endpoint.status)}`} />
                      <span className='font-inter text-syft-muted text-xs capitalize'>
                        {endpoint.status}
                      </span>
                    </div>
                  </div>

                  {/* Footer Info */}
                  <div className='border-syft-surface flex items-center justify-between border-t pt-3'>
                    <div className='text-syft-placeholder flex items-center gap-3 text-xs'>
                      <div className='flex items-center gap-1'>
                        {getVisibilityIcon(endpoint)}
                        <span>Public</span>
                      </div>
                      <div className='flex items-center gap-1'>
                        <Package className='h-3 w-3' aria-hidden='true' />
                        <span>v{endpoint.version}</span>
                      </div>
                    </div>
                    <div className='text-syft-placeholder flex items-center gap-3 text-xs'>
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
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
