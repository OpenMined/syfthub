/**
 * NoMatchMessage - AI assistant response for no relevant search results
 *
 * Displays a clean AI assistant-style message when semantic search doesn't find
 * any data sources with similarity score >= 0.5 for the user's query.
 */

import { motion } from 'framer-motion';
import Compass from 'lucide-react/dist/esm/icons/compass';
import MessageSquare from 'lucide-react/dist/esm/icons/message-square';
import Plus from 'lucide-react/dist/esm/icons/plus';

interface NoMatchMessageProps {
  /** The original search query */
  query: string;
  /** Callback when user wants to browse catalog */
  onBrowseCatalog?: () => void;
  /** Callback when user wants to add custom source */
  onAddCustomSource?: () => void;
}

/**
 * Main component for displaying "no match" message as an AI assistant response.
 */
export function NoMatchMessage({
  query,
  onBrowseCatalog,
  onAddCustomSource
}: Readonly<NoMatchMessageProps>) {
  const truncatedQuery = query.length > 60 ? `${query.slice(0, 60)}...` : query;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className='my-4 w-full max-w-3xl'
    >
      {/* AI Assistant style message card */}
      <div className='border-border bg-muted/30 overflow-hidden rounded-xl border'>
        {/* Message header with assistant icon */}
        <div className='flex items-start gap-3 px-4 py-4'>
          <div className='bg-primary/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg'>
            <MessageSquare className='text-primary h-4 w-4' />
          </div>
          <div className='min-w-0 flex-1'>
            <p className='font-inter text-foreground text-sm leading-relaxed'>
              I couldn&apos;t find any relevant data sources for your query about &ldquo;
              {truncatedQuery}&rdquo;.
            </p>
            <p className='font-inter text-muted-foreground mt-2 text-sm'>
              You can browse our catalog to discover available endpoints, or add a custom source
              directly.
            </p>
          </div>
        </div>

        {/* Action buttons */}
        {(onBrowseCatalog ?? onAddCustomSource) ? (
          <div className='border-border flex gap-2 border-t px-4 py-3'>
            {onBrowseCatalog ? (
              <button
                type='button'
                onClick={onBrowseCatalog}
                className='border-border bg-background hover:bg-accent inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors'
              >
                <Compass className='h-4 w-4' />
                Browse catalog
              </button>
            ) : null}
            {onAddCustomSource ? (
              <button
                type='button'
                onClick={onAddCustomSource}
                className='border-border bg-background hover:bg-accent inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors'
              >
                <Plus className='h-4 w-4' />
                Add custom source
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

/**
 * Simplified message variant for inline display.
 */
export function NoMatchMessageInline({ query }: Readonly<{ query: string }>) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className='font-inter text-muted-foreground flex items-center gap-2 py-2 text-sm'
    >
      <MessageSquare className='text-primary h-4 w-4' />
      <span>
        No relevant endpoints found for &ldquo;{query.slice(0, 30)}
        {query.length > 30 ? '...' : ''}&rdquo;
      </span>
    </motion.div>
  );
}
