import React, { useEffect, useState } from 'react';

import type { ChatSource } from '@/lib/types';

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

import { getPublicDatasites } from '@/lib/datasite-api';

import { Badge } from './ui/badge';

interface BrowseViewProperties {
  initialQuery?: string;
  onViewDatasite?: (slug: string, owner?: string) => void;
  onAuthRequired?: () => void;
}

export function BrowseView({
  initialQuery = '',
  onViewDatasite,
  onAuthRequired: _onAuthRequired
}: Readonly<BrowseViewProperties>) {
  const [datasites, setDatasites] = useState<ChatSource[]>([]);
  const [filteredDatasites, setFilteredDatasites] = useState<ChatSource[]>([]);
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load datasites on mount
  useEffect(() => {
    const loadDatasites = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const sources = await getPublicDatasites({ limit: 50 });
        setDatasites(sources);
        setFilteredDatasites(sources);
      } catch (error_) {
        setError(error_ instanceof Error ? error_.message : 'Failed to load datasites');
      } finally {
        setIsLoading(false);
      }
    };

    loadDatasites();
  }, []);

  // Filter datasites based on search query
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredDatasites(datasites);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = datasites.filter(
        (ds) =>
          ds.name.toLowerCase().includes(query) ||
          ds.description.toLowerCase().includes(query) ||
          ds.tag.toLowerCase().includes(query)
      );
      setFilteredDatasites(filtered);
    }
  }, [searchQuery, datasites]);

  const getStatusColor = (status: 'active' | 'warning' | 'inactive') => {
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
  };

  const getVisibilityIcon = (datasite: ChatSource) => {
    // Since we're showing public datasites, they're all public
    // But we can infer from the name/tag for demonstration
    if (datasite.name.toLowerCase().includes('private')) {
      return <Lock className='h-3 w-3' />;
    } else if (datasite.name.toLowerCase().includes('internal')) {
      return <Building className='h-3 w-3' />;
    }
    return <Globe className='h-3 w-3' />;
  };

  return (
    <div className='min-h-screen bg-white p-6'>
      <div className='mx-auto max-w-6xl'>
        {/* Header */}
        <div className='mb-8'>
          <h1 className='font-rubik mb-2 text-3xl font-semibold text-[#272532]'>
            Browse Data Sources
          </h1>
          <p className='font-inter text-[#5e5a72]'>
            Discover and explore trusted data sources from the community
          </p>
        </div>

        {/* Search and Filter Bar */}
        <div className='mb-8 flex gap-4'>
          <div className='relative flex-1'>
            <Search className='absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2 text-[#b4b0bf]' />
            <input
              type='text'
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder='Search data sources...'
              className='font-inter w-full rounded-xl border border-[#ecebef] py-3 pr-4 pl-11 transition-all focus:border-[#272532] focus:ring-2 focus:ring-[#272532]/10 focus:outline-none'
            />
          </div>
          <button className='font-inter flex items-center gap-2 rounded-xl border border-[#ecebef] px-4 py-3 text-[#5e5a72] transition-colors hover:bg-[#f7f6f9]'>
            <Filter className='h-5 w-5' />
            Filter
          </button>
        </div>

        {/* Content */}
        {isLoading ? (
          <div className='py-16 text-center'>
            <div className='flex items-center justify-center gap-3 text-gray-600'>
              <div className='h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600'></div>
              <span>Loading datasites...</span>
            </div>
          </div>
        ) : error ? (
          <div className='py-16 text-center'>
            <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-50'>
              <Search className='h-8 w-8 text-red-500' />
            </div>
            <h3 className='font-inter mb-2 text-lg font-medium text-gray-900'>
              Error Loading Datasites
            </h3>
            <p className='font-inter text-[#5e5a72]'>{error}</p>
          </div>
        ) : filteredDatasites.length === 0 ? (
          <div className='py-16 text-center'>
            <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[#f1f0f4]'>
              <Search className='h-8 w-8 text-[#5e5a72]' />
            </div>
            <h3 className='font-inter mb-2 text-lg font-medium text-[#272532]'>No Results Found</h3>
            <p className='font-inter text-[#5e5a72]'>
              {searchQuery ? `No datasites match "${searchQuery}"` : 'No datasites available'}
            </p>
          </div>
        ) : (
          <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
            {filteredDatasites.map((datasite) => (
              <div
                key={datasite.id}
                onClick={() => onViewDatasite?.(datasite.slug, datasite.owner_username)}
                className='group cursor-pointer rounded-xl border border-[#ecebef] bg-white p-5 transition-all hover:border-[#6976ae] hover:shadow-md'
              >
                {/* Header */}
                <div className='mb-3 flex items-start justify-between'>
                  <div className='min-w-0 flex-1'>
                    <h3 className='font-inter mb-1 truncate text-base font-semibold text-[#272532] group-hover:text-[#6976ae]'>
                      {datasite.name}
                    </h3>
                    {datasite.owner_username && (
                      <p className='font-inter truncate text-xs text-[#b4b0bf]'>
                        by @{datasite.owner_username}
                      </p>
                    )}
                    <p className='font-inter line-clamp-2 text-sm text-[#5e5a72]'>
                      {datasite.description}
                    </p>
                  </div>
                  <ChevronRight className='ml-2 h-5 w-5 shrink-0 text-[#b4b0bf] transition-transform group-hover:translate-x-1 group-hover:text-[#6976ae]' />
                </div>

                {/* Tags and Status */}
                <div className='mb-3 flex flex-wrap items-center gap-2'>
                  <Badge variant='secondary' className='font-inter text-xs'>
                    {datasite.tag}
                  </Badge>
                  <div className='flex items-center gap-1'>
                    <div className={`h-2 w-2 rounded-full ${getStatusColor(datasite.status)}`} />
                    <span className='font-inter text-xs text-[#5e5a72] capitalize'>
                      {datasite.status}
                    </span>
                  </div>
                </div>

                {/* Footer Info */}
                <div className='flex items-center justify-between border-t border-[#f1f0f4] pt-3'>
                  <div className='flex items-center gap-3 text-xs text-[#b4b0bf]'>
                    <div className='flex items-center gap-1'>
                      {getVisibilityIcon(datasite)}
                      <span>Public</span>
                    </div>
                    <div className='flex items-center gap-1'>
                      <Package className='h-3 w-3' />
                      <span>v{datasite.version}</span>
                    </div>
                  </div>
                  <div className='flex items-center gap-3 text-xs text-[#b4b0bf]'>
                    {datasite.stars_count > 0 && (
                      <div className='flex items-center gap-1'>
                        <Star className='h-3 w-3' />
                        <span>{datasite.stars_count}</span>
                      </div>
                    )}
                    <div className='flex items-center gap-1'>
                      <Calendar className='h-3 w-3' />
                      <span>{datasite.updated}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
