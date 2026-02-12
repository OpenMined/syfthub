import { memo, useCallback, useEffect, useMemo, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Filter from 'lucide-react/dist/esm/icons/filter';
import Tag from 'lucide-react/dist/esm/icons/tag';
import User from 'lucide-react/dist/esm/icons/user';
import X from 'lucide-react/dist/esm/icons/x';

import { Badge } from './ui/badge';
import { Modal } from './ui/modal';

// ============================================================================
// Types
// ============================================================================

export interface BrowseFilters {
  tags: Set<string>;
  owners: Set<string>;
}

export interface BrowseFiltersModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: BrowseFilters) => void;
  currentFilters: BrowseFilters;
  availableTags: string[];
  availableOwners: string[];
}

// ============================================================================
// Helper to extract unique tags and owners from endpoints
// ============================================================================

export function extractUniqueTags(endpoints: ChatSource[]): string[] {
  const tagSet = new Set<string>();
  for (const endpoint of endpoints) {
    for (const tag of endpoint.tags) {
      tagSet.add(tag);
    }
  }
  return [...tagSet].toSorted((a, b) => a.localeCompare(b));
}

export function extractUniqueOwners(endpoints: ChatSource[]): string[] {
  const ownerSet = new Set<string>();
  for (const endpoint of endpoints) {
    if (endpoint.owner_username) {
      ownerSet.add(endpoint.owner_username);
    }
  }
  return [...ownerSet].toSorted((a, b) => a.localeCompare(b));
}

// ============================================================================
// Default filters
// ============================================================================

export function createDefaultFilters(): BrowseFilters {
  return {
    tags: new Set<string>(),
    owners: new Set<string>()
  };
}

export function hasActiveFilters(filters: BrowseFilters): boolean {
  return filters.tags.size > 0 || filters.owners.size > 0;
}

// ============================================================================
// Selectable Item Component (reused for tags and owners)
// ============================================================================

interface SelectableItemProps {
  label: string;
  isSelected: boolean;
  onToggle: () => void;
}

const SelectableItem = memo(function SelectableItem({
  label,
  isSelected,
  onToggle
}: Readonly<SelectableItemProps>) {
  return (
    <button
      type='button'
      onClick={onToggle}
      className={`font-inter flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all ${
        isSelected
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground'
      }`}
    >
      <div
        className={`flex h-4 w-4 items-center justify-center rounded border transition-colors ${
          isSelected ? 'border-primary bg-primary' : 'border-input bg-background'
        }`}
      >
        {isSelected && <Check className='h-2.5 w-2.5 text-white' />}
      </div>
      {label}
    </button>
  );
});

// ============================================================================
// Main Component
// ============================================================================

export const BrowseFiltersModal = memo(function BrowseFiltersModal({
  isOpen,
  onClose,
  onApply,
  currentFilters,
  availableTags,
  availableOwners
}: Readonly<BrowseFiltersModalProps>) {
  // Local state for filters - only applied on confirm
  const [localTags, setLocalTags] = useState<Set<string>>(new Set(currentFilters.tags));
  const [localOwners, setLocalOwners] = useState<Set<string>>(new Set(currentFilters.owners));

  // Sync local state when modal opens
  useEffect(() => {
    if (isOpen) {
      setLocalTags(new Set(currentFilters.tags));
      setLocalOwners(new Set(currentFilters.owners));
    }
  }, [isOpen, currentFilters]);

  const toggleTag = useCallback((tag: string) => {
    setLocalTags((previous) => {
      const next = new Set(previous);
      if (next.has(tag)) {
        next.delete(tag);
      } else {
        next.add(tag);
      }
      return next;
    });
  }, []);

  const toggleOwner = useCallback((owner: string) => {
    setLocalOwners((previous) => {
      const next = new Set(previous);
      if (next.has(owner)) {
        next.delete(owner);
      } else {
        next.add(owner);
      }
      return next;
    });
  }, []);

  const handleApply = useCallback(() => {
    onApply({
      tags: localTags,
      owners: localOwners
    });
  }, [localTags, localOwners, onApply]);

  const handleClear = useCallback(() => {
    setLocalTags(new Set());
    setLocalOwners(new Set());
  }, []);

  const hasFilters = localTags.size > 0 || localOwners.size > 0;

  // Sort tags - selected first, then alphabetically
  const sortedTags = useMemo(() => {
    return [...availableTags].toSorted((a, b) => {
      const aSelected = localTags.has(a) ? 0 : 1;
      const bSelected = localTags.has(b) ? 0 : 1;
      if (aSelected !== bSelected) return aSelected - bSelected;
      return a.localeCompare(b);
    });
  }, [availableTags, localTags]);

  // Sort owners - selected first, then alphabetically
  const sortedOwners = useMemo(() => {
    return [...availableOwners].toSorted((a, b) => {
      const aSelected = localOwners.has(a) ? 0 : 1;
      const bSelected = localOwners.has(b) ? 0 : 1;
      if (aSelected !== bSelected) return aSelected - bSelected;
      return a.localeCompare(b);
    });
  }, [availableOwners, localOwners]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} size='lg' showCloseButton={false}>
      {/* Header */}
      <div className='flex items-center gap-3 pb-4'>
        <div className='bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-lg'>
          <Filter className='h-5 w-5' />
        </div>
        <div>
          <h3 className='font-inter text-foreground text-base font-medium'>Filter Results</h3>
          <p className='font-inter text-muted-foreground text-xs'>
            Narrow down results by tags and owners
          </p>
        </div>
      </div>

      {/* Tags Section */}
      <div className='mb-6'>
        <div className='mb-3 flex items-center gap-2'>
          <Tag className='text-muted-foreground h-4 w-4' />
          <span className='font-inter text-foreground text-sm font-medium'>Tags</span>
          {localTags.size > 0 && (
            <Badge variant='secondary' className='font-inter text-xs'>
              {localTags.size} selected
            </Badge>
          )}
        </div>

        {sortedTags.length > 0 ? (
          <div className='flex max-h-36 flex-wrap gap-2 overflow-y-auto pr-1'>
            {sortedTags.map((tag) => (
              <SelectableItem
                key={tag}
                label={tag}
                isSelected={localTags.has(tag)}
                onToggle={() => {
                  toggleTag(tag);
                }}
              />
            ))}
          </div>
        ) : (
          <p className='font-inter text-muted-foreground text-sm'>No tags available</p>
        )}
      </div>

      {/* Owners Section */}
      <div className='mb-6'>
        <div className='mb-3 flex items-center gap-2'>
          <User className='text-muted-foreground h-4 w-4' />
          <span className='font-inter text-foreground text-sm font-medium'>Owners</span>
          {localOwners.size > 0 && (
            <Badge variant='secondary' className='font-inter text-xs'>
              {localOwners.size} selected
            </Badge>
          )}
        </div>

        {sortedOwners.length > 0 ? (
          <div className='flex max-h-36 flex-wrap gap-2 overflow-y-auto pr-1'>
            {sortedOwners.map((owner) => (
              <SelectableItem
                key={owner}
                label={`@${owner}`}
                isSelected={localOwners.has(owner)}
                onToggle={() => {
                  toggleOwner(owner);
                }}
              />
            ))}
          </div>
        ) : (
          <p className='font-inter text-muted-foreground text-sm'>No owners available</p>
        )}
      </div>

      {/* Active Filters Preview */}
      {hasFilters && (
        <div className='border-border mb-4 rounded-lg border bg-gray-50 p-3 dark:bg-gray-900/50'>
          <div className='mb-2 flex items-center justify-between'>
            <span className='font-inter text-muted-foreground text-xs font-medium uppercase'>
              Active Filters
            </span>
            <button
              type='button'
              onClick={handleClear}
              className='font-inter text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs transition-colors'
            >
              <X className='h-3 w-3' />
              Clear all
            </button>
          </div>
          <div className='flex flex-wrap gap-2'>
            {[...localTags].map((tag) => (
              <Badge key={tag} variant='secondary' className='font-inter gap-1 text-xs'>
                {tag}
                <button
                  type='button'
                  onClick={() => {
                    toggleTag(tag);
                  }}
                  className='hover:text-foreground ml-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            ))}
            {[...localOwners].map((owner) => (
              <Badge key={owner} variant='secondary' className='font-inter gap-1 text-xs'>
                @{owner}
                <button
                  type='button'
                  onClick={() => {
                    toggleOwner(owner);
                  }}
                  className='hover:text-foreground ml-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className='flex items-center justify-between pt-2'>
        <button
          type='button'
          onClick={handleClear}
          disabled={!hasFilters}
          className='font-inter text-muted-foreground hover:text-foreground rounded-lg px-4 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50'
        >
          Clear Filters
        </button>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            onClick={onClose}
            className='font-inter text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg px-4 py-2 text-sm transition-colors'
          >
            Cancel
          </button>
          <button
            type='button'
            onClick={handleApply}
            className='font-inter bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg px-4 py-2 text-sm font-medium transition-colors'
          >
            Apply Filters
          </button>
        </div>
      </div>
    </Modal>
  );
});
