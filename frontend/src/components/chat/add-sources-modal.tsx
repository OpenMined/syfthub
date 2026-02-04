import { memo, useCallback, useMemo, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Database from 'lucide-react/dist/esm/icons/database';
import Search from 'lucide-react/dist/esm/icons/search';

import { Modal } from '@/components/ui/modal';
import { filterSourcesForAutocomplete } from '@/lib/validation';

// ============================================================================
// Sub-components
// ============================================================================

interface SourceItemProps {
  source: ChatSource;
  isSelected: boolean;
  onToggle: () => void;
}

const SourceItem = memo(function SourceItem({
  source,
  isSelected,
  onToggle
}: Readonly<SourceItemProps>) {
  return (
    <button
      type='button'
      onClick={onToggle}
      aria-pressed={isSelected}
      className={`group flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-all focus-visible:ring-2 focus-visible:ring-[#272532]/50 focus-visible:outline-none ${
        isSelected
          ? 'border-green-500 bg-green-50 dark:border-green-600 dark:bg-green-950/30'
          : 'border-border bg-card hover:border-green-300 hover:bg-green-50/50 dark:hover:border-green-700 dark:hover:bg-green-950/20'
      }`}
    >
      {/* Icon */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
          isSelected
            ? 'bg-green-500 text-white'
            : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
        }`}
      >
        <Database className='h-4 w-4' />
      </div>

      {/* Content */}
      <div className='min-w-0 flex-1'>
        <span
          className='font-inter text-foreground block truncate text-sm font-medium'
          title={source.name}
        >
          {source.name}
        </span>
        {source.full_path && (
          <span className='font-inter text-muted-foreground block truncate text-xs'>
            {source.full_path}
          </span>
        )}
        {source.description && (
          <p className='font-inter text-muted-foreground mt-1 line-clamp-2 text-xs'>
            {source.description}
          </p>
        )}
      </div>

      {/* Checkbox indicator */}
      <div
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
          isSelected
            ? 'border-green-500 bg-green-500 dark:border-green-600 dark:bg-green-600'
            : 'border-input bg-background'
        }`}
        aria-hidden='true'
      >
        {isSelected && <Check className='h-3 w-3 text-white' />}
      </div>
    </button>
  );
});

// ============================================================================
// Main Component
// ============================================================================

export interface AddSourcesModalProps {
  isOpen: boolean;
  onClose: () => void;
  availableSources: ChatSource[];
  selectedSourceIds: Set<string>;
  onConfirm: (selectedIds: Set<string>) => void;
}

export const AddSourcesModal = memo(function AddSourcesModal({
  isOpen,
  onClose,
  availableSources,
  selectedSourceIds,
  onConfirm
}: Readonly<AddSourcesModalProps>) {
  // Local selection state — only committed on confirm
  const [localSelected, setLocalSelected] = useState<Set<string>>(new Set(selectedSourceIds));
  const [searchQuery, setSearchQuery] = useState('');

  // Sync local state when modal opens with new external selections
  const previousOpenRef = useMemo(() => ({ current: false }), []);
  if (isOpen && !previousOpenRef.current) {
    // Modal just opened — reset local state to match store
    setLocalSelected(new Set(selectedSourceIds));
    setSearchQuery('');
  }
  previousOpenRef.current = isOpen;

  // Filter to data sources only (exclude models)
  const dataSourceEndpoints = useMemo(
    () => availableSources.filter((s) => s.type === 'data_source'),
    [availableSources]
  );

  // Apply search filter
  const filteredSources = useMemo(() => {
    if (!searchQuery.trim()) return dataSourceEndpoints;
    return filterSourcesForAutocomplete(
      dataSourceEndpoints,
      searchQuery,
      dataSourceEndpoints.length
    );
  }, [dataSourceEndpoints, searchQuery]);

  const toggleLocal = useCallback((id: string) => {
    setLocalSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    onConfirm(localSelected);
  }, [localSelected, onConfirm]);

  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  }, []);

  const selectedCount = localSelected.size;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size='lg' showCloseButton={false}>
      {/* Header */}
      <div className='flex items-center gap-3 pb-4'>
        <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'>
          <Database className='h-5 w-5' />
        </div>
        <div>
          <h3 className='font-inter text-foreground text-base font-medium'>
            Add Sources to Context
          </h3>
          <p className='font-inter text-muted-foreground text-xs'>
            Choose sources to ground your answer.
          </p>
        </div>
      </div>

      {/* Search input */}
      <div className='relative mb-3'>
        <Search className='text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2' />
        <input
          type='text'
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder='Search endpoints...'
          className='font-inter border-border bg-background placeholder:text-muted-foreground w-full rounded-lg border py-2 pr-4 pl-10 text-sm transition-colors focus:border-green-500 focus:ring-2 focus:ring-green-500/20 focus:outline-none'
          autoComplete='off'
        />
      </div>

      {/* Scrollable source list */}
      <div className='max-h-72 space-y-2 overflow-y-auto pr-1'>
        {filteredSources.length > 0 ? (
          filteredSources.map((source) => (
            <SourceItem
              key={source.id}
              source={source}
              isSelected={localSelected.has(source.id)}
              onToggle={() => {
                toggleLocal(source.id);
              }}
            />
          ))
        ) : (
          <div className='py-8 text-center'>
            <p className='font-inter text-muted-foreground text-sm'>
              {searchQuery.trim() ? 'No matching data sources found' : 'No data sources available'}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className='flex items-center justify-end gap-2 pt-4'>
        <button
          type='button'
          onClick={onClose}
          className='font-inter text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg px-4 py-2 text-sm transition-colors'
        >
          Cancel
        </button>
        <button
          type='button'
          onClick={handleConfirm}
          className='font-inter flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50'
        >
          {selectedCount === 0
            ? 'Confirm'
            : `Confirm ${String(selectedCount)} Source${selectedCount === 1 ? '' : 's'}`}
        </button>
      </div>
    </Modal>
  );
});
