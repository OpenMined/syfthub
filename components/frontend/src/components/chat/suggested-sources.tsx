/**
 * SuggestedSources Component
 *
 * Displays semantically-searched data source suggestions as subtle, placeholder-like
 * clickable chips. Uses muted colors with dashed borders to feel like gentle hints
 * rather than loud calls-to-action. Animates entry/exit with framer-motion.
 */
import { memo } from 'react';

import type { SearchableChatSource } from '@/lib/search-service';

import { AnimatePresence, motion } from 'framer-motion';
import Database from 'lucide-react/dist/esm/icons/database';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Sparkles from 'lucide-react/dist/esm/icons/sparkles';

// =============================================================================
// Types
// =============================================================================

export interface SuggestedSourcesProps {
  /** Suggested data sources from semantic search */
  suggestions: SearchableChatSource[];
  /** Callback when user clicks to add a suggestion to context */
  onAdd: (source: SearchableChatSource) => void;
  /** Whether a search is currently in progress */
  isSearching?: boolean;
}

// =============================================================================
// Component
// =============================================================================

export const SuggestedSources = memo(function SuggestedSources({
  suggestions,
  onAdd,
  isSearching = false
}: Readonly<SuggestedSourcesProps>) {
  // Hide entirely when nothing to show
  if (suggestions.length === 0 && !isSearching) return null;

  return (
    <div className='mb-2' role='region' aria-label='Suggested data sources'>
      {/* Label */}
      <div className='mb-1.5 flex items-center gap-1.5'>
        <Sparkles className='text-muted-foreground h-3 w-3' aria-hidden='true' />
        <span className='font-inter text-muted-foreground text-[11px] font-medium tracking-wide uppercase'>
          Suggested sources
        </span>
        {isSearching && (
          <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' aria-hidden='true' />
        )}
      </div>

      {/* Suggestion chips */}
      <div className='flex flex-wrap items-center gap-2'>
        <AnimatePresence mode='popLayout'>
          {suggestions.map((source) => (
            <motion.button
              key={source.id}
              type='button'
              onClick={() => {
                onAdd(source);
              }}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.15 }}
              className='font-inter text-muted-foreground hover:text-foreground border-border/50 hover:border-border hover:bg-muted/50 inline-flex items-center gap-1.5 rounded-full border border-dashed bg-transparent px-3 py-1 text-xs font-normal transition-colors'
              aria-label={`Add ${source.name} to context`}
            >
              <Database className='h-3 w-3 opacity-50' aria-hidden='true' />
              <span className='max-w-[160px] truncate'>{source.name}</span>
              <Plus className='h-3 w-3 opacity-40' aria-hidden='true' />
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
});
