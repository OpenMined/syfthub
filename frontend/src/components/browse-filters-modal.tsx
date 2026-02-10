import { memo, useCallback, useEffect, useMemo, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Filter from 'lucide-react/dist/esm/icons/filter';
import Star from 'lucide-react/dist/esm/icons/star';
import Tag from 'lucide-react/dist/esm/icons/tag';
import X from 'lucide-react/dist/esm/icons/x';

import { Badge } from './ui/badge';
import { Modal } from './ui/modal';

// ============================================================================
// Types
// ============================================================================

export interface BrowseFilters {
  tags: Set<string>;
  minStars: number;
}

export interface BrowseFiltersModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: BrowseFilters) => void;
  currentFilters: BrowseFilters;
  availableTags: string[];
  maxStars: number;
}

// ============================================================================
// Helper to extract unique tags from endpoints
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

export function getMaxStars(endpoints: ChatSource[]): number {
  if (endpoints.length === 0) return 0;
  return Math.max(...endpoints.map((ep) => ep.stars_count));
}

// ============================================================================
// Default filters
// ============================================================================

export function createDefaultFilters(): BrowseFilters {
  return {
    tags: new Set<string>(),
    minStars: 0
  };
}

export function hasActiveFilters(filters: BrowseFilters): boolean {
  return filters.tags.size > 0 || filters.minStars > 0;
}

// ============================================================================
// Tag Item Component
// ============================================================================

interface TagItemProps {
  tag: string;
  isSelected: boolean;
  onToggle: () => void;
}

const TagItem = memo(function TagItem({ tag, isSelected, onToggle }: Readonly<TagItemProps>) {
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
      {tag}
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
  maxStars
}: Readonly<BrowseFiltersModalProps>) {
  // Local state for filters - only applied on confirm
  const [localTags, setLocalTags] = useState<Set<string>>(new Set(currentFilters.tags));
  const [localMinStars, setLocalMinStars] = useState(currentFilters.minStars);

  // Sync local state when modal opens
  useEffect(() => {
    if (isOpen) {
      setLocalTags(new Set(currentFilters.tags));
      setLocalMinStars(currentFilters.minStars);
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

  const handleStarsChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number.parseInt(event.target.value, 10);
    setLocalMinStars(Number.isNaN(value) ? 0 : Math.max(0, value));
  }, []);

  const handleApply = useCallback(() => {
    onApply({
      tags: localTags,
      minStars: localMinStars
    });
  }, [localTags, localMinStars, onApply]);

  const handleClear = useCallback(() => {
    setLocalTags(new Set());
    setLocalMinStars(0);
  }, []);

  const hasFilters = localTags.size > 0 || localMinStars > 0;

  // Sort tags - selected first, then alphabetically
  const sortedTags = useMemo(() => {
    return [...availableTags].toSorted((a, b) => {
      const aSelected = localTags.has(a) ? 0 : 1;
      const bSelected = localTags.has(b) ? 0 : 1;
      if (aSelected !== bSelected) return aSelected - bSelected;
      return a.localeCompare(b);
    });
  }, [availableTags, localTags]);

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
            Narrow down results by tags and popularity
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
          <div className='flex max-h-48 flex-wrap gap-2 overflow-y-auto pr-1'>
            {sortedTags.map((tag) => (
              <TagItem
                key={tag}
                tag={tag}
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

      {/* Stars Section */}
      <div className='mb-6'>
        <div className='mb-3 flex items-center gap-2'>
          <Star className='text-muted-foreground h-4 w-4' />
          <span className='font-inter text-foreground text-sm font-medium'>Minimum Stars</span>
        </div>

        <div className='flex items-center gap-4'>
          <input
            type='range'
            min={0}
            max={maxStars || 100}
            value={localMinStars}
            onChange={handleStarsChange}
            className='h-2 flex-1 cursor-pointer appearance-none rounded-lg bg-gray-200 accent-[#272532] dark:bg-gray-700'
          />
          <div className='flex items-center gap-1'>
            <input
              type='number'
              min={0}
              max={maxStars || 100}
              value={localMinStars}
              onChange={handleStarsChange}
              className='font-inter border-border bg-background focus:border-primary focus:ring-primary/20 w-16 rounded-lg border px-2 py-1.5 text-center text-sm focus:ring-2 focus:outline-none'
            />
            <Star className='text-muted-foreground h-4 w-4' />
          </div>
        </div>
        {maxStars > 0 && (
          <p className='font-inter text-muted-foreground mt-2 text-xs'>
            Max stars in current results: {maxStars}
          </p>
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
            {localMinStars > 0 && (
              <Badge variant='secondary' className='font-inter gap-1 text-xs'>
                ≥{localMinStars} stars
                <button
                  type='button'
                  onClick={() => {
                    setLocalMinStars(0);
                  }}
                  className='hover:text-foreground ml-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            )}
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
