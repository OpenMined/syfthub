import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Database from 'lucide-react/dist/esm/icons/database';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Search from 'lucide-react/dist/esm/icons/search';
import { Link } from 'react-router-dom';

import { OnboardingCallout } from '@/components/onboarding';
import { Modal } from '@/components/ui/modal';
import { isDataSourceEndpoint } from '@/lib/endpoint-utils';
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
  const detailHref = source.owner_username
    ? `/${source.owner_username}/${source.slug}`
    : `/browse/${source.slug}`;

  return (
    <div
      className={`group flex w-full items-start gap-3 rounded-lg border p-3 transition-all ${
        isSelected
          ? 'border-green-500 bg-green-50 dark:border-green-600 dark:bg-green-950/30'
          : 'border-border bg-card hover:border-green-300 hover:bg-green-50/50 dark:hover:border-green-700 dark:hover:bg-green-950/20'
      }`}
    >
      {/* Checkbox indicator */}
      <button
        type='button'
        onClick={onToggle}
        aria-pressed={isSelected}
        className='mt-1 shrink-0 rounded focus-visible:ring-2 focus-visible:ring-[#272532]/50 focus-visible:outline-none'
      >
        <div
          className={`flex h-5 w-5 items-center justify-center rounded border transition-colors ${
            isSelected
              ? 'border-green-500 bg-green-500 dark:border-green-600 dark:bg-green-600'
              : 'border-input bg-background'
          }`}
          aria-hidden='true'
        >
          {isSelected && <Check className='h-3 w-3 text-white' />}
        </div>
      </button>

      {/* Icon */}
      <button
        type='button'
        onClick={onToggle}
        className='flex shrink-0 items-start focus-visible:outline-none'
        tabIndex={-1}
      >
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${
            isSelected
              ? 'bg-green-500 text-white'
              : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
          }`}
        >
          <Database className='h-4 w-4' />
        </div>
      </button>

      {/* Content */}
      <button
        type='button'
        onClick={onToggle}
        className='min-w-0 flex-1 text-left focus-visible:outline-none'
        tabIndex={-1}
      >
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
      </button>

      {/* Endpoint page link */}
      <Link
        to={detailHref}
        target='_blank'
        rel='noopener noreferrer'
        className='text-muted-foreground hover:text-foreground mt-1 shrink-0 transition-colors'
        aria-label={`View ${source.name} details`}
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        <ExternalLink className='h-4 w-4' />
      </Link>
    </div>
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
  const previousOpenRef = useRef(false);
  useEffect(() => {
    if (isOpen && !previousOpenRef.current) {
      setLocalSelected(new Set(selectedSourceIds));
      setSearchQuery('');
    }
    previousOpenRef.current = isOpen;
  }, [isOpen, selectedSourceIds]);

  // Filter to data sources only (model_data_source endpoints are included)
  const dataSourceEndpoints = useMemo(
    () => availableSources.filter((s) => isDataSourceEndpoint(s.type)),
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

  // Sort selected endpoints to appear at the top
  const sortedSources = useMemo(() => {
    return filteredSources.toSorted((a, b) => {
      const aSelected = localSelected.has(a.id) ? 0 : 1;
      const bSelected = localSelected.has(b.id) ? 0 : 1;
      return aSelected - bSelected;
    });
  }, [filteredSources, localSelected]);

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

      {/* Onboarding callout for source selection */}
      <OnboardingCallout step='select-sources' position='bottom'>
        <div />
      </OnboardingCallout>

      {/* Scrollable source list */}
      <div className='max-h-72 space-y-2 overflow-y-auto pr-1'>
        {sortedSources.length > 0 ? (
          sortedSources.map((source) => (
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
