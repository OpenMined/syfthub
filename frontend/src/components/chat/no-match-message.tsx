/**
 * NoMatchMessage - AI assistant response for no relevant search results
 *
 * Displays a helpful message when semantic search doesn't find
 * highly relevant data sources for the user's query.
 */

import type { ChatSource } from '@/lib/types';

import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Compass from 'lucide-react/dist/esm/icons/compass';
import Lightbulb from 'lucide-react/dist/esm/icons/lightbulb';
import Plus from 'lucide-react/dist/esm/icons/plus';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';

import { Badge } from '@/components/ui/badge';

interface NoMatchMessageProps {
  /** The original search query */
  query: string;
  /** Loosely related sources (relevance 0.3-0.5) to show as secondary options */
  looseMatches?: ChatSource[];
  /** Callback when user selects a loose match */
  onSelectLooseMatch?: (source: ChatSource) => void;
  /** Callback when user wants to browse catalog */
  onBrowseCatalog?: () => void;
  /** Callback when user wants to add custom source */
  onAddCustomSource?: () => void;
  /** Callback when user wants to refine query */
  onRefineQuery?: () => void;
}

interface SuggestionAction {
  icon: React.ReactNode;
  label: string;
  description: string;
  onClick?: () => void;
}

/**
 * Action button for suggested actions.
 */
function ActionButton({
  icon,
  label,
  description,
  onClick
}: Readonly<SuggestionAction & { onClick?: () => void }>) {
  return (
    <button
      type='button'
      onClick={onClick}
      className='border-border bg-card hover:bg-accent group flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors'
    >
      <div className='bg-muted group-hover:bg-primary/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors'>
        {icon}
      </div>
      <div className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block text-sm font-medium'>{label}</span>
        <span className='font-inter text-muted-foreground text-xs'>{description}</span>
      </div>
    </button>
  );
}

/**
 * Compact source card for loose matches.
 */
function LooseMatchCard({
  source,
  onSelect
}: Readonly<{ source: ChatSource; onSelect: () => void }>) {
  const relevanceScore = (source as ChatSource & { relevance_score?: number }).relevance_score;

  return (
    <button
      type='button'
      onClick={onSelect}
      className='border-border bg-card hover:border-primary/50 hover:bg-accent/50 flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors'
    >
      <div className='bg-muted flex h-8 w-8 shrink-0 items-center justify-center rounded-lg'>
        <span className='font-inter text-muted-foreground text-xs font-medium'>
          {source.name.slice(0, 2).toUpperCase()}
        </span>
      </div>
      <div className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block truncate text-sm font-medium'>
          {source.name}
        </span>
        <span className='font-inter text-muted-foreground block truncate text-xs'>
          {source.description.slice(0, 60)}
          {source.description.length > 60 ? '...' : ''}
        </span>
      </div>
      {relevanceScore !== undefined && (
        <Badge variant='secondary' className='font-inter h-5 shrink-0 px-2 text-[10px] font-normal'>
          {Math.round(relevanceScore * 100)}% match
        </Badge>
      )}
    </button>
  );
}

/**
 * Main component for displaying "no match" message.
 */
export function NoMatchMessage({
  query,
  looseMatches = [],
  onSelectLooseMatch,
  onBrowseCatalog,
  onAddCustomSource,
  onRefineQuery
}: Readonly<NoMatchMessageProps>) {
  const hasLooseMatches = looseMatches.length > 0;
  const truncatedQuery = query.length > 50 ? `${query.slice(0, 50)}...` : query;

  const actions: SuggestionAction[] = [
    ...(onBrowseCatalog
      ? [
          {
            icon: <Compass className='text-muted-foreground h-4 w-4' />,
            label: 'Browse catalog',
            description: 'Explore all available data sources',
            onClick: onBrowseCatalog
          }
        ]
      : []),
    ...(onAddCustomSource
      ? [
          {
            icon: <Plus className='text-muted-foreground h-4 w-4' />,
            label: 'Add custom source',
            description: 'Enter an endpoint path directly',
            onClick: onAddCustomSource
          }
        ]
      : []),
    ...(onRefineQuery
      ? [
          {
            icon: <RefreshCw className='text-muted-foreground h-4 w-4' />,
            label: 'Refine your query',
            description: 'Try different keywords or be more specific',
            onClick: onRefineQuery
          }
        ]
      : [])
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className='my-4 w-full max-w-3xl'
    >
      {/* Main message card */}
      <div className='border-border bg-muted/30 overflow-hidden rounded-xl border'>
        {/* Header */}
        <div className='border-border flex items-start gap-3 border-b px-4 py-3'>
          <div className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-900/30'>
            <AlertCircle className='h-4 w-4 text-amber-600 dark:text-amber-400' />
          </div>
          <div className='min-w-0 flex-1'>
            <h3 className='font-inter text-foreground text-sm font-medium'>
              No closely matching sources found
            </h3>
            <p className='font-inter text-muted-foreground mt-0.5 text-xs'>
              Your query &ldquo;{truncatedQuery}&rdquo; didn&apos;t match any data sources with high
              confidence.
            </p>
          </div>
        </div>

        {/* Suggestions */}
        <div className='p-4'>
          <div className='mb-3 flex items-center gap-2'>
            <Lightbulb className='text-muted-foreground h-3.5 w-3.5' />
            <span className='font-inter text-muted-foreground text-xs font-medium'>
              Here&apos;s what you can do:
            </span>
          </div>

          <div className='grid gap-2'>
            {actions.map((action) => (
              <ActionButton
                key={action.label}
                icon={action.icon}
                label={action.label}
                description={action.description}
                onClick={action.onClick}
              />
            ))}
          </div>
        </div>

        {/* Loose matches section (if available) */}
        {hasLooseMatches ? (
          <div className='border-border border-t px-4 py-3'>
            <div className='mb-3'>
              <span className='font-inter text-muted-foreground text-xs font-medium'>
                Loosely related sources ({looseMatches.length}):
              </span>
            </div>
            <div className='grid gap-2'>
              {looseMatches.slice(0, 3).map((source) => (
                <LooseMatchCard
                  key={source.id}
                  source={source}
                  onSelect={() => onSelectLooseMatch?.(source)}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

/**
 * Simplified message variant for inline display.
 */
export function NoMatchMessageInline({
  query,
  onRefineQuery
}: Readonly<{ query: string; onRefineQuery?: () => void }>) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className='font-inter text-muted-foreground flex items-center gap-2 py-2 text-sm'
    >
      <AlertCircle className='h-4 w-4 text-amber-500' />
      <span>
        No matches found for &ldquo;{query.slice(0, 30)}
        {query.length > 30 ? '...' : ''}&rdquo;
      </span>
      {onRefineQuery ? (
        <button type='button' onClick={onRefineQuery} className='text-primary hover:underline'>
          Try again
        </button>
      ) : null}
    </motion.div>
  );
}
