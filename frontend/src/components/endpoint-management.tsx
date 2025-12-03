import React, { useEffect, useState } from 'react';

import type {
  EndpointCreate,
  EndpointResponse,
  EndpointUpdate,
  EndpointVisibility
} from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  Building,
  Check,
  Edit3,
  Globe,
  Lock,
  Plus,
  Save,
  Star,
  Trash2,
  X
} from 'lucide-react';

import { useAuth } from '@/context/auth-context';
import {
  createEndpoint,
  deleteEndpoint,
  getUserEndpoints,
  updateEndpoint
} from '@/lib/endpoint-api';

import { ParticipateView } from './participate-view';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface CreateEndpointData {
  name: string;
  description: string;
  visibility: EndpointVisibility;
  version: string;
  readme: string;
}

export function EndpointManagement() {
  const { user } = useAuth();
  const [endpoints, setEndpoints] = useState<EndpointResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Create endpoint form state
  const [createData, setCreateData] = useState<CreateEndpointData>({
    name: '',
    description: '',
    visibility: 'public',
    version: '0.1.0',
    readme: ''
  });

  // Edit endpoint form state
  const [editData, setEditData] = useState<Partial<EndpointUpdate>>({});

  // Load user's endpoints
  useEffect(() => {
    const loadEndpoints = async () => {
      if (!user) return;

      try {
        setIsLoading(true);
        const userEndpoints = await getUserEndpoints({ limit: 50 });
        setEndpoints(userEndpoints);
      } catch (error_) {
        setError(error_ instanceof Error ? error_.message : 'Failed to load endpoints');
      } finally {
        setIsLoading(false);
      }
    };

    loadEndpoints();
  }, [user]);

  const handleCreateEndpoint = async () => {
    try {
      setError(null);
      setSuccess(null);
      setIsLoading(true);

      if (!createData.name.trim()) {
        setError('Endpoint name is required');
        return;
      }

      const newEndpoint = await createEndpoint({
        name: createData.name,
        description: createData.description,
        visibility: createData.visibility,
        version: createData.version,
        readme: createData.readme,
        policies: [],
        connect: [],
        contributors: []
      });

      setEndpoints((previous) => [newEndpoint, ...previous]);
      setSuccess('Endpoint created successfully!');
      setIsCreating(false);
      setCreateData({
        name: '',
        description: '',
        visibility: 'public',
        version: '0.1.0',
        readme: ''
      });

      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to create endpoint');
    } finally {
      setIsLoading(false);
    }
  };

  const handleEditEndpoint = async (id: number) => {
    try {
      setError(null);
      setSuccess(null);
      setIsLoading(true);

      const updatedEndpoint = await updateEndpoint(id, editData);

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

      await deleteEndpoint(id);
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

  const getVisibilityColor = (visibility: EndpointVisibility) => {
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
        return 'bg-gray-100 text-gray-800 border-gray-200';
      }
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  if (!user) {
    return (
      <div className='flex min-h-screen items-center justify-center'>
        <div className='text-center'>
          <AlertCircle className='mx-auto mb-4 h-12 w-12 text-red-500' />
          <h2 className='mb-2 text-xl font-semibold text-gray-900'>Access Denied</h2>
          <p className='text-gray-600'>You need to be logged in to manage endpoints.</p>
        </div>
      </div>
    );
  }

  // Show loading state
  if (isLoading && endpoints.length === 0 && !isCreating) {
    return (
      <div className='flex min-h-screen items-center justify-center bg-gray-50'>
        <div className='flex items-center gap-3 text-gray-600'>
          <div className='h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600'></div>
          <span>Loading endpoints...</span>
        </div>
      </div>
    );
  }

  // Show onboarding view when user has no endpoints
  if (endpoints.length === 0 && !isLoading) {
    return (
      <>
        <ParticipateView
          title='Get Started with Endpoints'
          onCreateEndpoint={() => {
            setIsCreating(true);
          }}
        />
        {/* Create Endpoint Modal - needs to be available even in empty state */}
        <AnimatePresence>
          {isCreating && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => {
                  setIsCreating(false);
                }}
                className='fixed inset-0 z-50 bg-black/20 backdrop-blur-sm'
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className='fixed inset-0 z-50 flex items-center justify-center p-4'
              >
                <div className='w-full max-w-2xl rounded-lg border border-gray-200 bg-white shadow-xl'>
                  <div className='border-b border-gray-200 px-6 py-4'>
                    <h2 className='text-lg font-semibold text-gray-900'>Create New Endpoint</h2>
                  </div>

                  <div className='space-y-4 p-6'>
                    <div>
                      <Label htmlFor='create-name'>Name</Label>
                      <Input
                        id='create-name'
                        value={createData.name}
                        onChange={(e) => {
                          setCreateData({ ...createData, name: e.target.value });
                        }}
                        placeholder='My awesome dataset'
                        required
                      />
                    </div>

                    <div>
                      <Label htmlFor='create-description'>Description</Label>
                      <Input
                        id='create-description'
                        value={createData.description}
                        onChange={(e) => {
                          setCreateData({ ...createData, description: e.target.value });
                        }}
                        placeholder='Brief description of your endpoint'
                      />
                    </div>

                    <div className='grid grid-cols-2 gap-4'>
                      <div>
                        <Label htmlFor='create-visibility'>Visibility</Label>
                        <Select
                          value={createData.visibility}
                          onValueChange={(value: EndpointVisibility) => {
                            setCreateData({ ...createData, visibility: value });
                          }}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value='public'>Public</SelectItem>
                            <SelectItem value='internal'>Internal</SelectItem>
                            <SelectItem value='private'>Private</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor='create-version'>Version</Label>
                        <Input
                          id='create-version'
                          value={createData.version}
                          onChange={(e) => {
                            setCreateData({ ...createData, version: e.target.value });
                          }}
                          placeholder='0.1.0'
                        />
                      </div>
                    </div>

                    <div>
                      <Label htmlFor='create-readme'>README (Optional)</Label>
                      <textarea
                        id='create-readme'
                        value={createData.readme}
                        onChange={(e) => {
                          setCreateData({ ...createData, readme: e.target.value });
                        }}
                        placeholder='Markdown documentation for your endpoint...'
                        className='w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none'
                        rows={4}
                      />
                    </div>
                  </div>

                  <div className='flex justify-end gap-2 border-t border-gray-200 px-6 py-4'>
                    <Button
                      variant='outline'
                      onClick={() => {
                        setIsCreating(false);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button onClick={handleCreateEndpoint} disabled={!createData.name.trim()}>
                      Create Endpoint
                    </Button>
                  </div>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </>
    );
  }

  // Show endpoint management grid when user has endpoints
  return (
    <div className='min-h-screen bg-gray-50 py-8'>
      <div className='mx-auto max-w-6xl px-6'>
        {/* Header */}
        <div className='mb-8 flex items-center justify-between'>
          <div>
            <h1 className='text-3xl font-bold text-gray-900'>My Endpoints</h1>
            <p className='mt-2 text-gray-600'>Create and manage your data sources.</p>
          </div>
          <Button
            onClick={() => {
              setIsCreating(true);
            }}
            className='flex items-center gap-2'
          >
            <Plus className='h-4 w-4' />
            Create Endpoint
          </Button>
        </div>

        {/* Success/Error Messages */}
        <AnimatePresence>
          {success && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-4'
            >
              <Check className='h-5 w-5 text-green-600' />
              <span className='text-green-800'>{success}</span>
            </motion.div>
          )}

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4'
            >
              <AlertCircle className='h-5 w-5 text-red-600' />
              <span className='text-red-800'>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Create Endpoint Modal */}
        <AnimatePresence>
          {isCreating && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => {
                  setIsCreating(false);
                }}
                className='fixed inset-0 z-50 bg-black/20 backdrop-blur-sm'
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className='fixed inset-0 z-50 flex items-center justify-center p-4'
              >
                <div className='w-full max-w-2xl rounded-lg border border-gray-200 bg-white shadow-xl'>
                  <div className='border-b border-gray-200 px-6 py-4'>
                    <h2 className='text-lg font-semibold text-gray-900'>Create New Endpoint</h2>
                  </div>

                  <div className='space-y-4 p-6'>
                    <div>
                      <Label htmlFor='create-name'>Name</Label>
                      <Input
                        id='create-name'
                        value={createData.name}
                        onChange={(e) => {
                          setCreateData({ ...createData, name: e.target.value });
                        }}
                        placeholder='My awesome dataset'
                        required
                      />
                    </div>

                    <div>
                      <Label htmlFor='create-description'>Description</Label>
                      <Input
                        id='create-description'
                        value={createData.description}
                        onChange={(e) => {
                          setCreateData({ ...createData, description: e.target.value });
                        }}
                        placeholder='Brief description of your endpoint'
                      />
                    </div>

                    <div className='grid grid-cols-2 gap-4'>
                      <div>
                        <Label htmlFor='create-visibility'>Visibility</Label>
                        <Select
                          value={createData.visibility}
                          onValueChange={(value: EndpointVisibility) => {
                            setCreateData({ ...createData, visibility: value });
                          }}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value='public'>Public</SelectItem>
                            <SelectItem value='internal'>Internal</SelectItem>
                            <SelectItem value='private'>Private</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor='create-version'>Version</Label>
                        <Input
                          id='create-version'
                          value={createData.version}
                          onChange={(e) => {
                            setCreateData({ ...createData, version: e.target.value });
                          }}
                          placeholder='0.1.0'
                        />
                      </div>
                    </div>

                    <div>
                      <Label htmlFor='create-readme'>README (Optional)</Label>
                      <textarea
                        id='create-readme'
                        value={createData.readme}
                        onChange={(e) => {
                          setCreateData({ ...createData, readme: e.target.value });
                        }}
                        placeholder='Markdown documentation for your endpoint...'
                        className='w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none'
                        rows={4}
                      />
                    </div>
                  </div>

                  <div className='flex justify-end gap-2 border-t border-gray-200 px-6 py-4'>
                    <Button
                      variant='outline'
                      onClick={() => {
                        setIsCreating(false);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleCreateEndpoint}
                      disabled={isLoading || !createData.name.trim()}
                    >
                      {isLoading ? 'Creating...' : 'Create Endpoint'}
                    </Button>
                  </div>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>

        {/* Endpoints Grid */}
        <div className='grid gap-6 md:grid-cols-2 lg:grid-cols-3'>
          {endpoints.map((endpoint) => (
            <div
              key={endpoint.id}
              className='rounded-lg border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md'
            >
              <div className='p-6'>
                <div className='mb-4 flex items-start justify-between'>
                  <div>
                    <h3 className='mb-1 text-lg font-semibold text-gray-900'>{endpoint.name}</h3>
                    <p className='line-clamp-2 text-sm text-gray-600'>
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

                <div className='text-xs text-gray-500'>
                  <p>Created: {formatDate(endpoint.created_at)}</p>
                  <p>Updated: {formatDate(endpoint.updated_at)}</p>
                </div>
              </div>

              {/* Edit Form */}
              {editingId === endpoint.id && (
                <div className='space-y-3 border-t border-gray-200 bg-gray-50 p-4'>
                  <div>
                    <Label htmlFor={`edit-name-${endpoint.id}`}>Name</Label>
                    <Input
                      id={`edit-name-${endpoint.id}`}
                      value={editData.name || ''}
                      onChange={(e) => {
                        setEditData({ ...editData, name: e.target.value });
                      }}
                      size='sm'
                    />
                  </div>
                  <div>
                    <Label htmlFor={`edit-description-${endpoint.id}`}>Description</Label>
                    <Input
                      id={`edit-description-${endpoint.id}`}
                      value={editData.description || ''}
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
    </div>
  );
}
