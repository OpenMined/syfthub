import { memo, useCallback, useEffect, useMemo, useState } from 'react';

import type { Collective } from '@/lib/collectives-api';

import Check from 'lucide-react/dist/esm/icons/check';
import Filter from 'lucide-react/dist/esm/icons/filter';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Tag from 'lucide-react/dist/esm/icons/tag';
import X from 'lucide-react/dist/esm/icons/x';

import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';

// ============================================================================
// Types
// ============================================================================

/**
 * Client-side filters for the Collectives browse tab. Mirrors `BrowseFilters`:
 * applied over the current page, so search stays the server-side dimension.
 */
export interface CollectiveFilters {
  /** Show only platform-verified collectives. */
  verified: boolean;
  /** Show only collectives that auto-approve join requests. */
  open: boolean;
  tags: Set<string>;
}

export function createDefaultCollectiveFilters(): CollectiveFilters {
  return { verified: false, open: false, tags: new Set<string>() };
}

export function hasActiveCollectiveFilters(filters: CollectiveFilters): boolean {
  return filters.verified || filters.open || filters.tags.size > 0;
}

/** Number of distinct filter dimensions in use — drives the button badge. */
export function collectiveFilterCount(filters: CollectiveFilters): number {
  return (filters.verified ? 1 : 0) + (filters.open ? 1 : 0) + filters.tags.size;
}

/** Unique, alphabetically sorted tags across the given collectives. */
export function extractCollectiveTags(collectives: Collective[]): string[] {
  const tagSet = new Set<string>();
  for (const collective of collectives) {
    for (const tag of collective.tags) tagSet.add(tag);
  }
  return [...tagSet].toSorted((a, b) => a.localeCompare(b));
}

// ============================================================================
// Selectable item — shared look with BrowseFiltersModal
// ============================================================================

interface SelectableItemProps {
  label: string;
  isSelected: boolean;
  onToggle: () => void;
  icon?: React.ReactNode;
}

const SelectableItem = memo(function SelectableItem({
  label,
  isSelected,
  onToggle,
  icon
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
      {icon}
      {label}
    </button>
  );
});

// ============================================================================
// Main component
// ============================================================================

export interface CollectiveFiltersModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: CollectiveFilters) => void;
  currentFilters: CollectiveFilters;
  availableTags: string[];
}

export const CollectiveFiltersModal = memo(function CollectiveFiltersModal({
  isOpen,
  onClose,
  onApply,
  currentFilters,
  availableTags
}: Readonly<CollectiveFiltersModalProps>) {
  // Local state — only committed to the parent on Apply.
  const [verified, setVerified] = useState(currentFilters.verified);
  const [open, setOpen] = useState(currentFilters.open);
  const [localTags, setLocalTags] = useState<Set<string>>(new Set(currentFilters.tags));

  useEffect(() => {
    if (isOpen) {
      setVerified(currentFilters.verified);
      setOpen(currentFilters.open);
      setLocalTags(new Set(currentFilters.tags));
    }
  }, [isOpen, currentFilters]);

  const toggleTag = useCallback((tag: string) => {
    setLocalTags((previous) => {
      const next = new Set(previous);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }, []);

  const handleApply = useCallback(() => {
    onApply({ verified, open, tags: localTags });
  }, [verified, open, localTags, onApply]);

  const handleClear = useCallback(() => {
    setVerified(false);
    setOpen(false);
    setLocalTags(new Set());
  }, []);

  const hasFilters = verified || open || localTags.size > 0;

  // Selected tags first, then alphabetical.
  const sortedTags = useMemo(
    () =>
      [...availableTags].toSorted((a, b) => {
        const aSelected = localTags.has(a) ? 0 : 1;
        const bSelected = localTags.has(b) ? 0 : 1;
        if (aSelected !== bSelected) return aSelected - bSelected;
        return a.localeCompare(b);
      }),
    [availableTags, localTags]
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} size='lg' showCloseButton={false}>
      {/* Header */}
      <div className='flex items-center gap-3 pb-4'>
        <div className='bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-lg'>
          <Filter className='h-5 w-5' />
        </div>
        <div>
          <h3 className='font-inter text-foreground text-base font-medium'>Filter Collectives</h3>
          <p className='font-inter text-muted-foreground text-xs'>
            Narrow down results by trust, join policy and tags
          </p>
        </div>
      </div>

      {/* Trust & membership */}
      <div className='mb-6'>
        <div className='mb-3 flex items-center gap-2'>
          <ShieldCheck className='text-muted-foreground h-4 w-4' />
          <span className='font-inter text-foreground text-sm font-medium'>Trust &amp; access</span>
        </div>
        <div className='flex flex-wrap gap-2'>
          <SelectableItem
            label='Verified only'
            isSelected={verified}
            onToggle={() => {
              setVerified((v) => !v);
            }}
          />
          <SelectableItem
            label='Open to join'
            isSelected={open}
            onToggle={() => {
              setOpen((v) => !v);
            }}
          />
        </div>
      </div>

      {/* Tags */}
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

      {/* Active filters preview */}
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
            {verified && (
              <Badge variant='secondary' className='font-inter gap-1 text-xs'>
                Verified
                <button
                  type='button'
                  onClick={() => {
                    setVerified(false);
                  }}
                  className='hover:text-foreground ml-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            )}
            {open && (
              <Badge variant='secondary' className='font-inter gap-1 text-xs'>
                Open to join
                <button
                  type='button'
                  onClick={() => {
                    setOpen(false);
                  }}
                  className='hover:text-foreground ml-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            )}
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
