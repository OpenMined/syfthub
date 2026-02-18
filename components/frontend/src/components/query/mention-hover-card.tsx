/**
 * MentionHoverCard Components
 *
 * Displays @owner/slug mentions as styled badges with hover cards
 * showing owner and endpoint information.
 */
import type { ChatSource } from '@/lib/types';

import Database from 'lucide-react/dist/esm/icons/database';
import Star from 'lucide-react/dist/esm/icons/star';
import User from 'lucide-react/dist/esm/icons/user';
import X from 'lucide-react/dist/esm/icons/x';

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

interface MentionBadgeProps {
  /** The source this mention refers to */
  source: ChatSource;
  /** Callback to remove this mention */
  onRemove?: () => void;
  /** Additional CSS classes */
  className?: string;
}

interface OwnerHoverCardProps {
  /** Owner username */
  username: string;
  /** Number of endpoints (optional) */
  endpointCount?: number;
  /** Children to wrap */
  children: React.ReactNode;
}

interface EndpointHoverCardProps {
  /** The endpoint to show info for */
  endpoint: ChatSource;
  /** Children to wrap */
  children: React.ReactNode;
}

// =============================================================================
// Owner HoverCard
// =============================================================================

export function OwnerHoverCard({
  username,
  endpointCount,
  children
}: Readonly<OwnerHoverCardProps>) {
  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent side='top' align='start' className='w-48'>
        <div className='flex items-center gap-2'>
          <div className='bg-muted flex h-8 w-8 items-center justify-center rounded-full'>
            <User className='h-4 w-4' />
          </div>
          <div className='flex flex-col'>
            <span className='font-semibold'>{username}</span>
            {endpointCount !== undefined && (
              <span className='text-muted-foreground text-xs'>
                {endpointCount} data source{endpointCount === 1 ? '' : 's'}
              </span>
            )}
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

// =============================================================================
// Endpoint HoverCard
// =============================================================================

export function EndpointHoverCard({ endpoint, children }: Readonly<EndpointHoverCardProps>) {
  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent side='top' align='start' className='w-72'>
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
      </HoverCardContent>
    </HoverCard>
  );
}

// =============================================================================
// Mention Badge
// =============================================================================

/**
 * Displays a completed @owner/slug mention as an interactive badge.
 * Hovering over the owner part shows owner info.
 * Hovering over the slug part shows endpoint info.
 */
export function MentionBadge({ source, onRemove, className }: Readonly<MentionBadgeProps>) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-sm dark:border-green-800 dark:bg-green-950/30',
        className
      )}
    >
      <span className='text-muted-foreground'>@</span>
      <OwnerHoverCard username={source.owner_username ?? ''}>
        <span className='cursor-pointer font-medium text-green-700 hover:underline dark:text-green-300'>
          {source.owner_username}
        </span>
      </OwnerHoverCard>
      <span className='text-muted-foreground'>/</span>
      <EndpointHoverCard endpoint={source}>
        <span className='cursor-pointer font-medium text-green-700 hover:underline dark:text-green-300'>
          {source.slug}
        </span>
      </EndpointHoverCard>
      {onRemove && (
        <button
          type='button'
          onClick={onRemove}
          className='text-muted-foreground hover:text-foreground ml-1 rounded-full p-0.5 transition-colors'
          aria-label={`Remove ${source.owner_username ?? 'unknown'}/${source.slug}`}
        >
          <X className='h-3 w-3' />
        </button>
      )}
    </span>
  );
}

// =============================================================================
// Mentioned Sources Display
// =============================================================================

interface MentionedSourcesProps {
  /** List of mentioned sources */
  sources: ChatSource[];
  /** Callback to remove a source */
  onRemove?: (source: ChatSource) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Displays a list of mentioned sources as badges.
 */
export function MentionedSources({
  sources,
  onRemove,
  className
}: Readonly<MentionedSourcesProps>) {
  if (sources.length === 0) return null;

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {sources.map((source) => (
        <MentionBadge
          key={source.id}
          source={source}
          onRemove={
            onRemove
              ? () => {
                  onRemove(source);
                }
              : undefined
          }
        />
      ))}
    </div>
  );
}
