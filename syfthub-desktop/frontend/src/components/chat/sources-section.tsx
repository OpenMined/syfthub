import { memo, useState } from 'react';

import { motion } from 'framer-motion';
import { FileText } from 'lucide-react';

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';

// =============================================================================
// Types
// =============================================================================

/**
 * Document source with endpoint path and content.
 * Matches the SDK's DocumentSource type.
 */
export interface DocumentSource {
  /** Endpoint path (owner/slug) where document was retrieved */
  slug: string;
  /** The actual document content */
  content: string;
}

/**
 * Sources data from the aggregator response.
 * Key is the document title, value contains the endpoint slug and content.
 */
export type SourcesData = Record<string, DocumentSource>;

// =============================================================================
// Constants
// =============================================================================

const VISIBLE_PILLS = 3;

// =============================================================================
// Sub-components
// =============================================================================

interface SourcePillProps {
  title: string;
  source: DocumentSource;
  index: number;
}

/**
 * Individual source rendered as a ghost pill with HoverCard content preview.
 */
const SourcePill = memo(function SourcePill({ title, source, index }: Readonly<SourcePillProps>) {
  const truncatedContent =
    source.content.length > 500 ? `${source.content.slice(0, 500).trim()}…` : source.content;

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <motion.button
          type='button'
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: index * 0.03 }}
          className='border-border/50 hover:border-border hover:bg-muted/50 hover:text-foreground text-muted-foreground rounded-full border px-2.5 py-0.5 text-xs transition-colors'
        >
          <span className='text-green-600/80 dark:text-green-500/80'>{source.slug}</span>
        </motion.button>
      </HoverCardTrigger>
      <HoverCardContent side='top' align='start' className='w-[360px] p-0'>
        {/* Header */}
        <div className='border-border border-b px-4 py-2.5'>
          <div className='flex items-center gap-2'>
            <FileText className='text-muted-foreground h-3.5 w-3.5' />
            <span className='text-muted-foreground text-xs font-medium'>{title}</span>
          </div>
        </div>
        {/* Content */}
        <div className='max-h-[220px] overflow-y-auto p-4'>
          <p className='text-foreground text-xs leading-relaxed whitespace-pre-wrap'>
            {truncatedContent}
          </p>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
});

// =============================================================================
// Main Component
// =============================================================================

interface SourcesSectionProps {
  sources: SourcesData;
}

/**
 * Sources displayed as ghost inline pills below the assistant message.
 *
 * Features:
 * - No card chrome -- pills sit flush below the message text
 * - Shows first 3 pills by default; overflow handled by "+N more" pill
 * - HoverCard on each pill shows document title + content preview
 */
export function SourcesSection({ sources }: Readonly<SourcesSectionProps>) {
  const [showAll, setShowAll] = useState(false);

  const sourceEntries = Object.entries(sources);
  const documentCount = sourceEntries.length;

  if (documentCount === 0) return null;

  const visibleEntries = showAll ? sourceEntries : sourceEntries.slice(0, VISIBLE_PILLS);
  const overflowCount = documentCount - VISIBLE_PILLS;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className='flex flex-wrap items-center gap-1.5'
    >
      {visibleEntries.map(([title, source], index) => (
        <SourcePill key={`${source.slug}-${title}`} title={title} source={source} index={index} />
      ))}

      {/* Overflow: expand */}
      {!showAll && overflowCount > 0 && (
        <motion.button
          type='button'
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: VISIBLE_PILLS * 0.03 }}
          onClick={() => {
            setShowAll(true);
          }}
          className='border-border/40 text-muted-foreground/60 hover:border-border/60 hover:text-muted-foreground rounded-full border border-dashed px-2.5 py-0.5 text-xs transition-colors'
        >
          +{overflowCount} more
        </motion.button>
      )}

      {/* Overflow: collapse */}
      {showAll && documentCount > VISIBLE_PILLS && (
        <motion.button
          type='button'
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          onClick={() => {
            setShowAll(false);
          }}
          className='border-border/40 text-muted-foreground/60 hover:border-border/60 hover:text-muted-foreground rounded-full border border-dashed px-2.5 py-0.5 text-xs transition-colors'
        >
          collapse
        </motion.button>
      )}
    </motion.div>
  );
}
