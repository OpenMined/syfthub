/**
 * MentionPopover Components
 *
 * Popovers for @mention autocomplete - owner selection and endpoint selection.
 */
import { forwardRef, useEffect, useRef } from 'react';

import type { OwnerInfo } from '@/lib/mention-utils';
import type { ChatSource } from '@/lib/types';

import Database from 'lucide-react/dist/esm/icons/database';
import Star from 'lucide-react/dist/esm/icons/star';
import User from 'lucide-react/dist/esm/icons/user';

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

interface MentionPopoverBaseProps {
  /** Whether the popover is visible */
  isOpen: boolean;
  /** Index of highlighted item */
  highlightedIndex: number;
  /** CSS class for positioning */
  className?: string;
}

interface OwnerPopoverProps extends MentionPopoverBaseProps {
  /** List of owners to display */
  owners: OwnerInfo[];
  /** Callback when owner is selected */
  onSelect: (owner: string) => void;
}

interface EndpointPopoverProps extends MentionPopoverBaseProps {
  /** List of endpoints to display */
  endpoints: ChatSource[];
  /** Callback when endpoint is selected */
  onSelect: (endpoint: ChatSource) => void;
}

// =============================================================================
// Owner Popover
// =============================================================================

export const OwnerPopover = forwardRef<HTMLDivElement, OwnerPopoverProps>(
  ({ isOpen, owners, highlightedIndex, onSelect, className }, ref) => {
    const listReference = useRef<HTMLUListElement>(null);

    // Scroll highlighted item into view
    useEffect(() => {
      if (!listReference.current) return;
      const highlightedItem = listReference.current.children[highlightedIndex] as
        | HTMLElement
        | undefined;
      highlightedItem?.scrollIntoView({ block: 'nearest' });
    }, [highlightedIndex]);

    if (!isOpen || owners.length === 0) return null;

    return (
      <div
        ref={ref}
        className={cn(
          'bg-popover text-popover-foreground absolute z-50 w-64 rounded-lg border p-1 shadow-lg',
          className
        )}
        role='listbox'
        aria-label='Select data source owner'
      >
        <div className='text-muted-foreground px-2 py-1.5 text-xs font-medium'>Select owner</div>
        <ul ref={listReference} className='max-h-48 overflow-y-auto'>
          {owners.map((owner, index) => (
            <li
              key={owner.username}
              role='option'
              aria-selected={index === highlightedIndex}
              className={cn(
                'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                index === highlightedIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-accent/50'
              )}
              onClick={() => {
                onSelect(owner.username);
              }}
              onMouseEnter={() => {
                // Could update highlighted index on hover if desired
              }}
            >
              <HoverCard openDelay={300} closeDelay={100}>
                <HoverCardTrigger asChild>
                  <div className='flex flex-1 items-center gap-2'>
                    <div className='bg-muted flex h-6 w-6 items-center justify-center rounded-full'>
                      <User className='h-3.5 w-3.5' />
                    </div>
                    <span className='font-medium'>{owner.username}</span>
                    <span className='text-muted-foreground text-xs'>
                      {owner.endpointCount} endpoint{owner.endpointCount === 1 ? '' : 's'}
                    </span>
                  </div>
                </HoverCardTrigger>
                <HoverCardContent side='right' align='start' className='w-56'>
                  <div className='flex flex-col gap-1'>
                    <div className='flex items-center gap-2'>
                      <User className='text-muted-foreground h-4 w-4' />
                      <span className='font-semibold'>{owner.username}</span>
                    </div>
                    <p className='text-muted-foreground text-xs'>
                      {owner.endpointCount} data source{owner.endpointCount === 1 ? '' : 's'}{' '}
                      available
                    </p>
                  </div>
                </HoverCardContent>
              </HoverCard>
            </li>
          ))}
        </ul>
        <div className='text-muted-foreground border-t px-2 py-1.5 text-xs'>
          <kbd className='bg-muted rounded px-1 font-mono text-xs'>Tab</kbd> to select
        </div>
      </div>
    );
  }
);

OwnerPopover.displayName = 'OwnerPopover';

// =============================================================================
// Endpoint Popover
// =============================================================================

export const EndpointPopover = forwardRef<HTMLDivElement, EndpointPopoverProps>(
  ({ isOpen, endpoints, highlightedIndex, onSelect, className }, ref) => {
    const listReference = useRef<HTMLUListElement>(null);

    // Scroll highlighted item into view
    useEffect(() => {
      if (!listReference.current) return;
      const highlightedItem = listReference.current.children[highlightedIndex] as
        | HTMLElement
        | undefined;
      highlightedItem?.scrollIntoView({ block: 'nearest' });
    }, [highlightedIndex]);

    if (!isOpen || endpoints.length === 0) return null;

    return (
      <div
        ref={ref}
        className={cn(
          'bg-popover text-popover-foreground absolute z-50 w-72 rounded-lg border p-1 shadow-lg',
          className
        )}
        role='listbox'
        aria-label='Select data source'
      >
        <div className='text-muted-foreground px-2 py-1.5 text-xs font-medium'>
          Select data source
        </div>
        <ul ref={listReference} className='max-h-64 overflow-y-auto'>
          {endpoints.map((endpoint, index) => (
            <li
              key={endpoint.id}
              role='option'
              aria-selected={index === highlightedIndex}
              className={cn(
                'flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 transition-colors',
                index === highlightedIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-accent/50'
              )}
              onClick={() => {
                onSelect(endpoint);
              }}
            >
              <HoverCard openDelay={300} closeDelay={100}>
                <HoverCardTrigger asChild>
                  <div className='flex flex-1 items-center gap-2'>
                    <div className='flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-green-100 dark:bg-green-900/30'>
                      <Database className='h-4 w-4 text-green-700 dark:text-green-300' />
                    </div>
                    <div className='flex min-w-0 flex-col'>
                      <span className='truncate text-sm font-medium'>{endpoint.slug}</span>
                      <span className='text-muted-foreground truncate text-xs'>
                        {endpoint.name}
                      </span>
                    </div>
                  </div>
                </HoverCardTrigger>
                <HoverCardContent side='right' align='start' className='w-72'>
                  <EndpointHoverContent endpoint={endpoint} />
                </HoverCardContent>
              </HoverCard>
            </li>
          ))}
        </ul>
        <div className='text-muted-foreground border-t px-2 py-1.5 text-xs'>
          <kbd className='bg-muted rounded px-1 font-mono text-xs'>Tab</kbd> to select
        </div>
      </div>
    );
  }
);

EndpointPopover.displayName = 'EndpointPopover';

// =============================================================================
// Endpoint Hover Content
// =============================================================================

interface EndpointHoverContentProps {
  endpoint: ChatSource;
}

function EndpointHoverContent({ endpoint }: Readonly<EndpointHoverContentProps>) {
  return (
    <div className='flex flex-col gap-2'>
      {/* Header */}
      <div className='flex items-start gap-2'>
        <div className='flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-green-100 dark:bg-green-900/30'>
          <Database className='h-4 w-4 text-green-700 dark:text-green-300' />
        </div>
        <div className='min-w-0 flex-1'>
          <p className='truncate font-semibold'>{endpoint.name}</p>
          <p className='text-muted-foreground text-xs'>
            {endpoint.owner_username}/{endpoint.slug}
          </p>
        </div>
      </div>

      {/* Description */}
      {endpoint.description && (
        <p className='text-muted-foreground line-clamp-2 text-xs'>{endpoint.description}</p>
      )}

      {/* Stats */}
      <div className='flex items-center gap-3 text-xs'>
        <div className='flex items-center gap-1'>
          <Star className='h-3 w-3' />
          <span>{endpoint.stars_count}</span>
        </div>
        <span className='text-muted-foreground'>v{endpoint.version}</span>
        {endpoint.tags.length > 0 && (
          <div className='flex flex-wrap gap-1'>
            {endpoint.tags.slice(0, 2).map((tag) => (
              <span key={tag} className='bg-muted rounded px-1.5 py-0.5 text-xs'>
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
