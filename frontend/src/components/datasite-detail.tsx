import React, { useEffect, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import {
  ArrowLeft,
  Building,
  Calendar,
  Check,
  Copy,
  Download,
  ExternalLink,
  GitFork,
  Globe,
  Lock,
  Package,
  Share2,
  Star,
  Users
} from 'lucide-react';

import { getPublicDatasites } from '@/lib/datasite-api';

import { Badge } from './ui/badge';
import { Button } from './ui/button';

interface DatasiteDetailProperties {
  slug: string;
  owner?: string | null;
  onBack: () => void;
}

export function DatasiteDetail({ slug, owner, onBack }: Readonly<DatasiteDetailProperties>) {
  const [datasite, setDatasite] = useState<ChatSource | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const loadDatasite = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // Since we don't have a direct endpoint for getting a single public datasite by slug,
        // we'll fetch all public datasites and find the one with the matching slug and owner
        // In a real implementation, you'd want a dedicated endpoint like /api/v1/datasites/public/{owner}/{slug}
        const datasites = await getPublicDatasites({ limit: 100 });
        let foundDatasite = datasites.find((ds) => {
          // Match by slug and owner if both are provided
          if (owner && ds.owner_username) {
            return ds.slug === slug && ds.owner_username === owner;
          }
          // Fallback to slug-only match
          return ds.slug === slug;
        });

        // Set the full path for display
        if (foundDatasite) {
          foundDatasite = {
            ...foundDatasite,
            full_path: `${foundDatasite.owner_username || owner || 'anonymous'}/${slug}`
          };
        }

        if (foundDatasite) {
          setDatasite(foundDatasite);
        } else {
          setError('Datasite not found');
        }
      } catch (error_) {
        setError(error_ instanceof Error ? error_.message : 'Failed to load datasite');
      } finally {
        setIsLoading(false);
      }
    };

    loadDatasite();
  }, [slug, owner]);

  const handleCopySlug = () => {
    const fullPath = datasite?.full_path || `${datasite?.owner_username || 'anonymous'}/${slug}`;
    navigator.clipboard.writeText(fullPath);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  const getStatusBadgeColor = (status: 'active' | 'warning' | 'inactive') => {
    switch (status) {
      case 'active': {
        return 'bg-green-100 text-green-800 border-green-200';
      }
      case 'warning': {
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      }
      case 'inactive': {
        return 'bg-red-100 text-red-800 border-red-200';
      }
      default: {
        return 'bg-gray-100 text-gray-800 border-gray-200';
      }
    }
  };

  if (isLoading) {
    return (
      <div className='min-h-screen bg-gray-50 p-8'>
        <div className='flex items-center justify-center py-12'>
          <div className='flex items-center gap-3 text-gray-600'>
            <div className='h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600'></div>
            <span>Loading datasite...</span>
          </div>
        </div>
      </div>
    );
  }

  if (error || !datasite) {
    return (
      <div className='min-h-screen bg-gray-50 p-8'>
        <div className='mx-auto max-w-4xl'>
          <Button variant='ghost' onClick={onBack} className='mb-4 flex items-center gap-2'>
            <ArrowLeft className='h-4 w-4' />
            Back
          </Button>
          <div className='py-12 text-center'>
            <h2 className='mb-2 text-xl font-semibold text-gray-900'>
              {error || 'Datasite not found'}
            </h2>
            <p className='text-gray-600'>The datasite with slug "{slug}" could not be found.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className='min-h-screen bg-gray-50'>
      {/* Header */}
      <div className='border-b border-gray-200 bg-white'>
        <div className='mx-auto max-w-6xl px-6 py-4'>
          <Button
            variant='ghost'
            onClick={onBack}
            className='mb-4 flex items-center gap-2 text-gray-600 hover:text-gray-900'
          >
            <ArrowLeft className='h-4 w-4' />
            Back to datasites
          </Button>

          <div className='flex items-start justify-between'>
            <div>
              <h1 className='mb-2 text-3xl font-bold text-gray-900'>{datasite.name}</h1>
              <p className='mb-4 text-lg text-gray-600'>{datasite.description}</p>

              {/* Badges */}
              <div className='mb-4 flex flex-wrap gap-2'>
                <Badge className={getStatusBadgeColor(datasite.status)}>
                  {datasite.status === 'active' && '● Active'}
                  {datasite.status === 'warning' && '● Needs Update'}
                  {datasite.status === 'inactive' && '● Inactive'}
                </Badge>
                <Badge variant='outline'>
                  <Package className='mr-1 h-3 w-3' />v{datasite.version}
                </Badge>
                {datasite.stars_count > 0 && (
                  <Badge variant='outline' className='border-yellow-200 text-yellow-600'>
                    <Star className='mr-1 h-3 w-3' />
                    {datasite.stars_count}
                  </Badge>
                )}
                <Badge variant='outline'>
                  <Calendar className='mr-1 h-3 w-3' />
                  Updated {datasite.updated}
                </Badge>
              </div>

              {/* Full path with copy */}
              <div className='flex items-center gap-2'>
                <code className='rounded bg-gray-100 px-2 py-1 font-mono text-sm text-gray-700'>
                  {datasite.full_path || `${datasite.owner_username || 'anonymous'}/${slug}`}
                </code>
                <Button variant='ghost' size='sm' onClick={handleCopySlug} className='h-7 w-7 p-0'>
                  {copied ? (
                    <Check className='h-3.5 w-3.5 text-green-600' />
                  ) : (
                    <Copy className='h-3.5 w-3.5' />
                  )}
                </Button>
              </div>
            </div>

            {/* Action buttons */}
            <div className='flex gap-2'>
              <Button variant='outline' className='flex items-center gap-2'>
                <Star className='h-4 w-4' />
                Star
              </Button>
              <Button variant='outline' className='flex items-center gap-2'>
                <GitFork className='h-4 w-4' />
                Fork
              </Button>
              <Button className='flex items-center gap-2'>
                <Download className='h-4 w-4' />
                Use Datasite
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className='mx-auto max-w-6xl px-6 py-8'>
        <div className='grid gap-8 lg:grid-cols-3'>
          {/* Main content */}
          <div className='space-y-6 lg:col-span-2'>
            {/* README Section */}
            <div className='rounded-lg border border-gray-200 bg-white p-6'>
              <h2 className='mb-4 text-xl font-semibold text-gray-900'>Documentation</h2>
              <div className='prose prose-sm max-w-none text-gray-600'>
                <p>
                  This datasite provides access to structured data that can be used for analysis,
                  machine learning, or application development.
                </p>
                <h3 className='mt-4 mb-2 text-lg font-medium text-gray-900'>Usage</h3>
                <p>To use this datasite in your project:</p>
                <pre className='rounded bg-gray-50 p-3 text-xs'>
                  <code>{`from syfthub import Datasite\n\nds = Datasite("${datasite?.full_path || `${datasite?.owner_username || 'anonymous'}/${slug}`}")\ndata = ds.fetch()`}</code>
                </pre>
                <h3 className='mt-4 mb-2 text-lg font-medium text-gray-900'>Features</h3>
                <ul className='list-disc space-y-1 pl-5'>
                  <li>Real-time data updates</li>
                  <li>RESTful API access</li>
                  <li>Multiple export formats</li>
                  <li>Privacy-preserving queries</li>
                </ul>
              </div>
            </div>

            {/* Policies Section */}
            <div className='rounded-lg border border-gray-200 bg-white p-6'>
              <h2 className='mb-4 text-xl font-semibold text-gray-900'>Access Policies</h2>
              <div className='space-y-3'>
                <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
                  <div className='flex items-start gap-3'>
                    <Globe className='mt-0.5 h-5 w-5 text-blue-600' />
                    <div>
                      <h3 className='text-sm font-medium text-blue-900'>Public Access</h3>
                      <p className='mt-1 text-xs text-blue-700'>
                        This datasite is publicly accessible. No authentication required for read
                        operations.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className='space-y-6'>
            {/* Info Card */}
            <div className='rounded-lg border border-gray-200 bg-white p-6'>
              <h3 className='mb-4 text-sm font-semibold text-gray-900'>About</h3>
              <div className='space-y-4'>
                <div>
                  <p className='mb-1 text-xs text-gray-500'>Owner</p>
                  <div className='flex items-center gap-2'>
                    <div className='h-6 w-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600'></div>
                    <span className='text-sm font-medium text-gray-900'>
                      @{datasite.owner_username || 'anonymous'}
                    </span>
                  </div>
                </div>

                <div>
                  <p className='mb-1 text-xs text-gray-500'>Category</p>
                  <Badge variant='outline'>{datasite.tag}</Badge>
                </div>

                <div>
                  <p className='mb-1 text-xs text-gray-500'>Contributors</p>
                  <div className='flex items-center gap-1'>
                    <Users className='h-4 w-4 text-gray-400' />
                    <span className='text-sm text-gray-900'>
                      {datasite.contributors?.length || 1} contributor
                      {(datasite.contributors?.length || 1) === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className='rounded-lg border border-gray-200 bg-white p-6'>
              <h3 className='mb-4 text-sm font-semibold text-gray-900'>Quick Actions</h3>
              <div className='space-y-2'>
                <Button variant='outline' className='w-full justify-start' size='sm'>
                  <ExternalLink className='mr-2 h-4 w-4' />
                  View in Browser
                </Button>
                <Button variant='outline' className='w-full justify-start' size='sm'>
                  <Share2 className='mr-2 h-4 w-4' />
                  Share Datasite
                </Button>
                <Button variant='outline' className='w-full justify-start' size='sm'>
                  <Download className='mr-2 h-4 w-4' />
                  Export Data
                </Button>
              </div>
            </div>

            {/* Stats */}
            <div className='rounded-lg border border-gray-200 bg-white p-6'>
              <h3 className='mb-4 text-sm font-semibold text-gray-900'>Statistics</h3>
              <div className='grid grid-cols-2 gap-4'>
                <div>
                  <p className='text-2xl font-bold text-gray-900'>{datasite.stars_count}</p>
                  <p className='text-xs text-gray-500'>Stars</p>
                </div>
                <div>
                  <p className='text-2xl font-bold text-gray-900'>0</p>
                  <p className='text-xs text-gray-500'>Forks</p>
                </div>
                <div>
                  <p className='text-2xl font-bold text-gray-900'>0</p>
                  <p className='text-xs text-gray-500'>Downloads</p>
                </div>
                <div>
                  <p className='text-2xl font-bold text-gray-900'>0</p>
                  <p className='text-xs text-gray-500'>Views</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
