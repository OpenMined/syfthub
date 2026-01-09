import React, { useEffect, useState } from 'react';

import type {
  EndpointResponse,
  EndpointType,
  EndpointUpdate,
  EndpointVisibility
} from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  Building,
  Check,
  Download,
  Edit3,
  Globe,
  Lock,
  Save,
  Star,
  Trash2,
  X
} from 'lucide-react';

import { useAuth } from '@/context/auth-context';
import { deleteEndpointByPath, getUserEndpoints, updateEndpointByPath } from '@/lib/endpoint-utils';

import { ParticipateView } from './participate-view';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

// Helper functions moved outside component for consistent-function-scoping
function getVisibilityColor(visibility: EndpointVisibility) {
  switch (visibility) {
    case 'public': {
      return 'bg-green-100 text-green-800 border-green-200';
    }
    case 'private': {
      return 'bg-red-100 text-red-800 border-red-200';
    }
    case 'internal': {
      return 'bg-blue-100 text-blue-800 border-blue-200';
    }
    default: {
      return 'bg-[#f1f0f4] text-[#272532] border-[#ecebef]';
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
      return 'bg-[#f1f0f4] text-[#272532] border-[#ecebef]';
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

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

export function EndpointManagement() {
  const { user } = useAuth();
  const [endpoints, setEndpoints] = useState<EndpointResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showParticipate, setShowParticipate] = useState(false);

  // Edit endpoint form state
  const [editData, setEditData] = useState<Partial<EndpointUpdate>>({});

  // Load user's endpoints
  useEffect(() => {
    const loadEndpoints = async () => {
      if (!user) return;

      try {
        setIsLoading(true);
        const userEndpoints = await getUserEndpoints({ limit: 50 }, user.username);
        setEndpoints(userEndpoints);
      } catch (error_) {
        setError(error_ instanceof Error ? error_.message : 'Failed to load endpoints');
      } finally {
        setIsLoading(false);
      }
    };

    void loadEndpoints();
  }, [user]);

  const handleEditEndpoint = async (id: number) => {
    try {
      setError(null);
      setSuccess(null);
      setIsLoading(true);

      // Find the endpoint to get its slug
      const endpoint = endpoints.find((ep) => ep.id === id);
      if (!endpoint || !user?.username) {
        throw new Error('Endpoint not found');
      }

      const path = `${user.username}/${endpoint.slug}`;
      const updatedEndpoint = await updateEndpointByPath(path, editData);

      setEndpoints((previous) => previous.map((ds) => (ds.id === id ? updatedEndpoint : ds)));

      setSuccess('Endpoint updated successfully!');
      setEditingId(null);
      setEditData({});

      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to update endpoint');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteEndpoint = async (id: number) => {
    if (
      !globalThis.confirm(
        'Are you sure you want to delete this endpoint? This action cannot be undone.'
      )
    ) {
      return;
    }

    try {
      setError(null);
      setIsLoading(true);

      // Find the endpoint to get its slug
      const endpoint = endpoints.find((ep) => ep.id === id);
      if (!endpoint || !user?.username) {
        throw new Error('Endpoint not found');
      }

      const path = `${user.username}/${endpoint.slug}`;
      await deleteEndpointByPath(path);
      setEndpoints((previous) => previous.filter((ds) => ds.id !== id));
      setSuccess('Endpoint deleted successfully!');

      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to delete endpoint');
    } finally {
      setIsLoading(false);
    }
  };

  const getVisibilityIcon = (visibility: EndpointVisibility) => {
    switch (visibility) {
      case 'public': {
        return <Globe className='h-4 w-4' />;
      }
      case 'private': {
        return <Lock className='h-4 w-4' />;
      }
      case 'internal': {
        return <Building className='h-4 w-4' />;
      }
      default: {
        return <Globe className='h-4 w-4' />;
      }
    }
  };

  if (!user) {
    return (
      <div className='flex min-h-screen items-center justify-center bg-[#fcfcfd]'>
        <div className='text-center'>
          <AlertCircle className='mx-auto mb-4 h-12 w-12 text-red-500' />
          <h2 className='font-rubik mb-2 text-xl font-medium text-[#272532]'>Access Denied</h2>
          <p className='font-inter text-[#5e5a72]'>You need to be logged in to manage endpoints.</p>
        </div>
      </div>
    );
  }

  // Show loading state
  if (isLoading && endpoints.length === 0) {
    return (
      <div className='flex min-h-screen items-center justify-center bg-[#fcfcfd]'>
        <div className='flex items-center gap-3 text-[#5e5a72]'>
          <div className='h-6 w-6 animate-spin rounded-full border-2 border-[#ecebef] border-t-[#6976ae]'></div>
          <span className='font-inter'>Loading endpoints...</span>
        </div>
      </div>
    );
  }

  // Show onboarding view when user has no endpoints
  if (endpoints.length === 0 && !isLoading) {
    return <ParticipateView title='Get Started with Endpoints' />;
  }

  // Show participate view when requested
  if (showParticipate) {
    return (
      <ParticipateView
        title='Install SDK'
        onBack={() => {
          setShowParticipate(false);
        }}
      />
    );
  }

  // Show endpoint management grid when user has endpoints
  return (
    <div className='mx-auto flex min-h-screen max-w-[1600px] flex-col'>
      {/* Sticky Header */}
      <div className='sticky top-0 z-30 flex w-full items-center justify-between border-b border-[#ecebef] bg-[#fcfcfd]/95 px-6 py-4 backdrop-blur-sm'>
        <h2 className='font-rubik text-xl font-medium text-[#272532]'>My Endpoints</h2>
        <Button
          onClick={() => {
            setShowParticipate(true);
          }}
          className='flex items-center gap-2'
        >
          <Download className='h-4 w-4' />
          Install SDK
        </Button>
      </div>

      {/* Main Content */}
      <main className='w-full min-w-0 flex-1'>
        <div className='mx-auto max-w-5xl space-y-8 px-6 py-8'>
          {/* Page Title */}
          <div className='max-w-3xl space-y-4'>
            <h2 className='font-rubik text-3xl font-medium text-[#272532]'>
              Manage Your Endpoints
            </h2>
            <p className='font-inter text-lg leading-relaxed text-[#5e5a72]'>
              Create and manage your data sources and models.
            </p>
          </div>

          {/* Success/Error Messages */}
          <AnimatePresence>
            {success && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className='flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 p-4'
              >
                <Check className='h-5 w-5 text-green-600' />
                <span className='font-inter text-green-800'>{success}</span>
              </motion.div>
            )}

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className='flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-4'
              >
                <AlertCircle className='h-5 w-5 text-red-600' />
                <span className='font-inter text-red-800'>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Endpoints Grid */}
          <div className='grid gap-8 md:grid-cols-2 lg:grid-cols-3'>
            {endpoints.map((endpoint) => (
              <div
                key={endpoint.id}
                className='rounded-xl border border-[#ecebef] bg-white shadow-sm transition-shadow hover:shadow-md'
              >
                <div className='p-6'>
                  <div className='mb-4 flex items-start justify-between'>
                    <div>
                      <h3 className='font-rubik mb-1 text-lg font-medium text-[#272532]'>
                        {endpoint.name}
                      </h3>
                      <p className='font-inter line-clamp-2 text-sm text-[#5e5a72]'>
                        {endpoint.description || 'No description provided'}
                      </p>
                    </div>
                    <div className='flex items-center gap-1'>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => {
                          setEditingId(endpoint.id);
                          setEditData({
                            name: endpoint.name,
                            description: endpoint.description,
                            visibility: endpoint.visibility,
                            version: endpoint.version,
                            readme: endpoint.readme
                          });
                        }}
                      >
                        <Edit3 className='h-4 w-4' />
                      </Button>
                      <Button
                        variant='ghost'
                        size='sm'
                        onClick={() => handleDeleteEndpoint(endpoint.id)}
                        className='text-red-600 hover:bg-red-50 hover:text-red-700'
                      >
                        <Trash2 className='h-4 w-4' />
                      </Button>
                    </div>
                  </div>

                  <div className='mb-4 flex flex-wrap gap-2'>
                    <Badge className={`border ${getTypeStyles(endpoint.type)}`}>
                      {getTypeLabel(endpoint.type)}
                    </Badge>
                    <Badge className={getVisibilityColor(endpoint.visibility)}>
                      <div className='flex items-center gap-1'>
                        {getVisibilityIcon(endpoint.visibility)}
                        <span className='capitalize'>{endpoint.visibility}</span>
                      </div>
                    </Badge>
                    <Badge variant='outline'>v{endpoint.version}</Badge>
                    {endpoint.stars_count > 0 && (
                      <Badge variant='outline' className='border-yellow-200 text-yellow-600'>
                        <Star className='mr-1 h-3 w-3' />
                        {endpoint.stars_count}
                      </Badge>
                    )}
                  </div>

                  <div className='font-inter text-xs text-[#5e5a72]'>
                    <p>Created: {formatDate(endpoint.created_at)}</p>
                    <p>Updated: {formatDate(endpoint.updated_at)}</p>
                  </div>
                </div>

                {/* Edit Form */}
                {editingId === endpoint.id && (
                  <div className='space-y-3 border-t border-[#ecebef] bg-[#f7f6f9] p-4'>
                    <div>
                      <Label htmlFor={`edit-name-${String(endpoint.id)}`}>Name</Label>
                      <Input
                        id={`edit-name-${String(endpoint.id)}`}
                        value={editData.name ?? ''}
                        onChange={(e) => {
                          setEditData({ ...editData, name: e.target.value });
                        }}
                        size='sm'
                      />
                    </div>
                    <div>
                      <Label htmlFor={`edit-description-${String(endpoint.id)}`}>Description</Label>
                      <Input
                        id={`edit-description-${String(endpoint.id)}`}
                        value={editData.description ?? ''}
                        onChange={(e) => {
                          setEditData({ ...editData, description: e.target.value });
                        }}
                        size='sm'
                      />
                    </div>
                    <div className='flex gap-2'>
                      <Button
                        size='sm'
                        onClick={() => handleEditEndpoint(endpoint.id)}
                        disabled={isLoading}
                        className='flex-1'
                      >
                        <Save className='mr-1 h-3 w-3' />
                        Save
                      </Button>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={() => {
                          setEditingId(null);
                          setEditData({});
                        }}
                        className='flex-1'
                      >
                        <X className='mr-1 h-3 w-3' />
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
