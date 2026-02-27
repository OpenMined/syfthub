import { memo, useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';

// =============================================================================
// Types
// =============================================================================

export interface DocumentSource {
  slug: string;
  content: string;
}

export type SourcesData = Record<string, DocumentSource>;

// =============================================================================
// Sub-components
// =============================================================================

interface SourceItemProps {
  title: string;
  source: DocumentSource;
  index: number;
}

const SourceItem = memo(function SourceItem({ title, source, index }: Readonly<SourceItemProps>) {
  const truncatedContent =
    source.content.length > 500 ? `${source.content.slice(0, 500).trim()}…` : source.content;

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: index * 0.03 }}
          className='group hover:bg-accent flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 transition-colors'
        >
          <span className='shrink-0 text-xs font-medium text-green-600'>
            {source.slug}
          </span>
          <span className='text-muted-foreground text-xs'>:</span>
          <span className='text-muted-foreground group-hover:text-foreground truncate text-xs'>
            {title}
          </span>
        </motion.div>
      </HoverCardTrigger>
      <HoverCardContent side='right' align='start' className='w-[360px] p-0'>
        <div className='border-border border-b px-4 py-2.5'>
          <div className='flex items-center gap-2'>
            <FileText className='text-muted-foreground h-3.5 w-3.5' />
            <span className='text-muted-foreground text-xs font-medium'>Document Preview</span>
          </div>
        </div>
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

export function SourcesSection({ sources }: Readonly<SourcesSectionProps>) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((previous) => !previous);
  }, []);

  const sourceEntries = Object.entries(sources);
  const documentCount = sourceEntries.length;

  if (documentCount === 0) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className='border-border bg-card rounded-xl border'
    >
      <button
        onClick={toggleExpanded}
        className='hover:bg-muted flex w-full items-center justify-between px-4 py-2.5 transition-colors'
      >
        <div className='flex items-center gap-2'>
          <FileText className='text-muted-foreground h-4 w-4' />
          <span className='text-muted-foreground text-sm font-medium'>Sources</span>
          <span className='bg-secondary/10 text-secondary rounded-full px-2 py-0.5 text-xs font-medium'>
            {documentCount} {documentCount === 1 ? 'document' : 'documents'}
          </span>
        </div>

        {isExpanded ? (
          <ChevronUp className='text-muted-foreground h-4 w-4' />
        ) : (
          <ChevronDown className='text-muted-foreground h-4 w-4' />
        )}
      </button>

      <AnimatePresence>
        {isExpanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className='overflow-hidden'
          >
            <div className='border-border border-t px-4 py-3'>
              <div className='space-y-0.5'>
                {sourceEntries.map(([title, source], index) => (
                  <SourceItem
                    key={`${source.slug}-${title}`}
                    title={title}
                    source={source}
                    index={index}
                  />
                ))}
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
}
