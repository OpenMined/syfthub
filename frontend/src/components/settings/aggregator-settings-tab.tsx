/**
 * Aggregator Settings Tab
 *
 * Allows users to manage multiple aggregator configurations.
 * Users can add, edit, delete, and set default aggregators.
 */

import React, { useCallback, useEffect, useState } from 'react';

import type { UserAggregator, UserAggregatorUpdate } from '@/lib/types';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Edit2 from 'lucide-react/dist/esm/icons/edit-2';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import MoreVertical from 'lucide-react/dist/esm/icons/more-vertical';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Server from 'lucide-react/dist/esm/icons/server';
import Star from 'lucide-react/dist/esm/icons/star';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import X from 'lucide-react/dist/esm/icons/x';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useUserAggregatorsStore } from '@/stores/user-aggregators-store';

// =============================================================================
// Types
// =============================================================================

interface AggregatorFormData {
  name: string;
  url: string;
  is_default: boolean;
}

interface AggregatorCardProps {
  readonly aggregator: UserAggregator;
  readonly onEdit: (aggregator: UserAggregator) => void;
  readonly onDelete: (id: number) => void;
  readonly onSetDefault: (id: number) => void;
  readonly isProcessing: boolean;
}

interface AggregatorFormProps {
  readonly initialData?: Partial<AggregatorFormData>;
  readonly onSubmit: (data: AggregatorFormData) => void;
  readonly onCancel: () => void;
  readonly isSubmitting: boolean;
  readonly submitLabel: string;
}

// =============================================================================
// Validation
// =============================================================================

function validateUrl(url: string): string | null {
  if (!url.trim()) return 'URL is required';
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return 'URL must use http:// or https://';
    }
    return null;
  } catch {
    return 'Please enter a valid URL (e.g., https://aggregator.example.com)';
  }
}

function validateName(name: string): string | null {
  if (!name.trim()) return 'Name is required';
  if (name.length > 100) return 'Name must be 100 characters or less';
  return null;
}

// =============================================================================
// Components
// =============================================================================

function AggregatorCard({
  aggregator,
  onEdit,
  onDelete,
  onSetDefault,
  isProcessing
}: AggregatorCardProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={`border-border bg-card relative rounded-lg border p-4 transition-shadow hover:shadow-md ${
        aggregator.is_default ? 'ring-primary ring-1' : ''
      }`}
    >
      {/* Default Badge */}
      {aggregator.is_default && (
        <div className='bg-primary text-primary-foreground absolute -top-2 -right-2 flex h-6 items-center gap-1 rounded-full px-2 text-xs font-medium'>
          <Star className='h-3 w-3 fill-current' />
          Default
        </div>
      )}

      <div className='flex items-start justify-between gap-4'>
        <div className='min-w-0 flex-1'>
          {/* Name */}
          <h4 className='text-foreground truncate font-medium'>{aggregator.name}</h4>

          {/* URL */}
          <p className='text-muted-foreground mt-1 truncate text-sm'>{aggregator.url}</p>

          {/* Meta info */}
          <p className='text-muted-foreground mt-2 text-xs'>
            Added {new Date(aggregator.created_at).toLocaleDateString()}
          </p>
        </div>

        {/* Actions */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant='ghost'
              size='icon'
              className='h-8 w-8 flex-shrink-0'
              disabled={isProcessing}
            >
              {isProcessing ? (
                <Loader2 className='h-4 w-4 animate-spin' />
              ) : (
                <MoreVertical className='h-4 w-4' />
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align='end'>
            {!aggregator.is_default && (
              <DropdownMenuItem
                onClick={() => {
                  onSetDefault(aggregator.id);
                }}
              >
                <Star className='mr-2 h-4 w-4' />
                Set as Default
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={() => {
                onEdit(aggregator);
              }}
            >
              <Edit2 className='mr-2 h-4 w-4' />
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                onDelete(aggregator.id);
              }}
              className='text-red-600 focus:text-red-600'
            >
              <Trash2 className='mr-2 h-4 w-4' />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </motion.div>
  );
}

function AggregatorForm({
  initialData,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel
}: AggregatorFormProps) {
  const [formData, setFormData] = useState<AggregatorFormData>({
    name: initialData?.name ?? '',
    url: initialData?.url ?? '',
    is_default: initialData?.is_default ?? false
  });
  const [errors, setErrors] = useState<{ name?: string; url?: string }>({});

  const handleChange = useCallback((field: keyof AggregatorFormData, value: string | boolean) => {
    setFormData((previous) => ({ ...previous, [field]: value }));
    // Clear error when user starts typing
    if (field === 'name' || field === 'url') {
      setErrors((previous) => ({ ...previous, [field]: undefined }));
    }
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      // Validate
      const nameError = validateName(formData.name);
      const urlError = validateUrl(formData.url);

      if (nameError || urlError) {
        setErrors({ name: nameError ?? undefined, url: urlError ?? undefined });
        return;
      }

      onSubmit(formData);
    },
    [formData, onSubmit]
  );

  return (
    <motion.form
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      onSubmit={handleSubmit}
      className='border-border bg-muted/50 space-y-4 rounded-lg border p-4'
    >
      <div className='flex items-center justify-between'>
        <h4 className='text-foreground font-medium'>
          {initialData?.name ? 'Edit Aggregator' : 'Add New Aggregator'}
        </h4>
        <Button type='button' variant='ghost' size='icon' onClick={onCancel} className='h-8 w-8'>
          <X className='h-4 w-4' />
        </Button>
      </div>

      {/* Name Field */}
      <div className='space-y-2'>
        <Label htmlFor='aggregator-name'>
          Name <span className='text-red-500'>*</span>
        </Label>
        <Input
          id='aggregator-name'
          value={formData.name}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder='e.g., Production Aggregator'
          disabled={isSubmitting}
        />
        {errors.name && <p className='text-xs text-red-500'>{errors.name}</p>}
      </div>

      {/* URL Field */}
      <div className='space-y-2'>
        <Label htmlFor='aggregator-url'>
          URL <span className='text-red-500'>*</span>
        </Label>
        <Input
          id='aggregator-url'
          type='url'
          value={formData.url}
          onChange={(e) => handleChange('url', e.target.value)}
          placeholder='https://aggregator.example.com/api/v1'
          disabled={isSubmitting}
        />
        {errors.url && <p className='text-xs text-red-500'>{errors.url}</p>}
        <p className='text-muted-foreground text-xs'>
          The base URL of your aggregator service API.
        </p>
      </div>

      {/* Default Checkbox */}
      <div className='flex items-center gap-2'>
        <input
          type='checkbox'
          id='is-default'
          checked={formData.is_default}
          onChange={(e) => handleChange('is_default', e.target.checked)}
          disabled={isSubmitting}
          className='h-4 w-4 rounded border-gray-300'
        />
        <Label htmlFor='is-default' className='text-sm font-normal'>
          Set as default aggregator
        </Label>
      </div>

      {/* Warning */}
      <div className='rounded-lg border border-amber-200 bg-amber-50 p-3'>
        <div className='flex items-start gap-2'>
          <AlertCircle className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600' />
          <p className='text-xs text-amber-800'>
            Using a custom aggregator means your chat queries will be sent to that service. Make
            sure you trust the aggregator you configure.
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className='flex items-center justify-end gap-2 pt-2'>
        <Button type='button' variant='outline' onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type='submit' disabled={isSubmitting} className='flex items-center gap-2'>
          {isSubmitting && <Loader2 className='h-4 w-4 animate-spin' />}
          {submitLabel}
        </Button>
      </div>
    </motion.form>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function AggregatorSettingsTab() {
  const {
    aggregators,
    defaultAggregatorId,
    isLoading,
    isCreating,
    isUpdating,
    isDeleting,
    error,
    fetchAggregators,
    createAggregator,
    updateAggregator,
    deleteAggregator,
    setDefaultAggregator,
    clearError
  } = useUserAggregatorsStore();

  const [isAdding, setIsAdding] = useState(false);
  const [editingAggregator, setEditingAggregator] = useState<UserAggregator | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Load aggregators on mount
  useEffect(() => {
    void fetchAggregators();
  }, [fetchAggregators]);

  // Clear success message after 3 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [successMessage]);

  const handleAdd = useCallback(
    async (data: AggregatorFormData) => {
      const result = await createAggregator({
        name: data.name,
        url: data.url,
        is_default: data.is_default
      });
      if (result) {
        setIsAdding(false);
        setSuccessMessage('Aggregator created successfully!');
      }
    },
    [createAggregator]
  );

  const handleEdit = useCallback(
    async (data: AggregatorFormData) => {
      if (!editingAggregator) return;
      const updateData: UserAggregatorUpdate = {};
      if (data.name !== editingAggregator.name) updateData.name = data.name;
      if (data.url !== editingAggregator.url) updateData.url = data.url;
      if (data.is_default !== editingAggregator.is_default) updateData.is_default = data.is_default;

      // Only update if there are changes
      if (Object.keys(updateData).length === 0) {
        setEditingAggregator(null);
        return;
      }

      const result = await updateAggregator(editingAggregator.id, updateData);
      if (result) {
        setEditingAggregator(null);
        setSuccessMessage('Aggregator updated successfully!');
      }
    },
    [editingAggregator, updateAggregator]
  );

  const handleDelete = useCallback(
    async (id: number) => {
      if (globalThis.confirm('Are you sure you want to delete this aggregator?')) {
        const success = await deleteAggregator(id);
        if (success) {
          setSuccessMessage('Aggregator deleted successfully!');
        }
      }
    },
    [deleteAggregator]
  );

  const handleSetDefault = useCallback(
    async (id: number) => {
      const result = await setDefaultAggregator(id);
      if (result) {
        setSuccessMessage('Default aggregator updated!');
      }
    },
    [setDefaultAggregator]
  );

  const handleStartEdit = useCallback((aggregator: UserAggregator) => {
    setEditingAggregator(aggregator);
    setIsAdding(false);
  }, []);

  const handleCancelForm = useCallback(() => {
    setIsAdding(false);
    setEditingAggregator(null);
  }, []);

  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-foreground text-lg font-semibold'>Aggregator Settings</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Manage your custom aggregators for chat operations. You can add multiple aggregators and
          switch between them as needed.
        </p>
      </div>

      {/* Info Banner */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
        <div className='flex items-start gap-3'>
          <Server className='mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600' />
          <div>
            <h4 className='text-sm font-medium text-blue-900'>About Aggregators</h4>
            <p className='mt-1 text-xs text-blue-700'>
              Aggregators handle RAG (Retrieval-Augmented Generation) orchestration for chat
              operations. By default, SyftHub uses its built-in aggregator. You can configure custom
              aggregators to use your own RAG services.
            </p>
          </div>
        </div>
      </div>

      {/* Success Message */}
      <AnimatePresence>
        {successMessage && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3'
          >
            <Check className='h-4 w-4 text-green-600' />
            <span className='text-sm text-green-800'>{successMessage}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error Message */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{error}</span>
            <Button
              variant='ghost'
              size='sm'
              onClick={clearError}
              className='ml-auto h-auto py-1 text-xs'
            >
              Dismiss
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading State */}
      {isLoading && (
        <div className='flex items-center justify-center py-8'>
          <Loader2 className='text-muted-foreground h-8 w-8 animate-spin' />
        </div>
      )}

      {!isLoading && (
        <>
          {/* Aggregator List */}
          <div className='space-y-4'>
            {/* Add Button */}
            {!isAdding && !editingAggregator && (
              <Button
                onClick={() => {
                  setIsAdding(true);
                }}
                variant='outline'
                className='w-full justify-center'
              >
                <Plus className='mr-2 h-4 w-4' />
                Add Aggregator
              </Button>
            )}

            {/* Add Form */}
            <AnimatePresence>
              {isAdding && (
                <AggregatorForm
                  onSubmit={handleAdd}
                  onCancel={handleCancelForm}
                  isSubmitting={isCreating}
                  submitLabel='Create Aggregator'
                />
              )}
            </AnimatePresence>

            {/* Edit Form */}
            <AnimatePresence>
              {editingAggregator && (
                <AggregatorForm
                  initialData={{
                    name: editingAggregator.name,
                    url: editingAggregator.url,
                    is_default: editingAggregator.is_default
                  }}
                  onSubmit={handleEdit}
                  onCancel={handleCancelForm}
                  isSubmitting={isUpdating}
                  submitLabel='Save Changes'
                />
              )}
            </AnimatePresence>

            {/* Aggregator Cards */}
            <div className='space-y-3'>
              <AnimatePresence mode='popLayout'>
                {aggregators.map((aggregator) => (
                  <AggregatorCard
                    key={aggregator.id}
                    aggregator={aggregator}
                    onEdit={handleStartEdit}
                    onDelete={handleDelete}
                    onSetDefault={handleSetDefault}
                    isProcessing={isUpdating || isDeleting}
                  />
                ))}
              </AnimatePresence>

              {/* Empty State */}
              {aggregators.length === 0 && !isAdding && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className='text-muted-foreground py-8 text-center'
                >
                  <Server className='mx-auto h-12 w-12 opacity-20' />
                  <p className='mt-2 text-sm'>No custom aggregators configured.</p>
                  <p className='text-xs opacity-70'>
                    Add one above or use the default SyftHub aggregator.
                  </p>
                </motion.div>
              )}
            </div>
          </div>

          {/* Default Indicator */}
          {defaultAggregatorId && aggregators.length > 0 && (
            <div className='border-border border-t pt-4'>
              <p className='text-muted-foreground text-xs'>
                <Star className='mr-1 inline h-3 w-3' />
                The default aggregator is used for all chat operations. You can change it by
                selecting &quot;Set as Default&quot; from the menu on any aggregator card.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
