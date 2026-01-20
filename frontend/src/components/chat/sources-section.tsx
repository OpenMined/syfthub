import { memo, useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import ChevronUp from 'lucide-react/dist/esm/icons/chevron-up';
import FileText from 'lucide-react/dist/esm/icons/file-text';

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
// Sub-components
// =============================================================================

interface HoverCardProps {
  content: string;
  isVisible: boolean;
  position: { x: number; y: number };
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

/**
 * Custom hover card that displays document content preview.
 * Uses Framer Motion for smooth animations.
 * Supports mouse interaction for scrolling content.
 */
const HoverCard = memo(function HoverCard({
  content,
  isVisible,
  position,
  onMouseEnter,
  onMouseLeave
}: Readonly<HoverCardProps>) {
  // Truncate content for preview
  const truncatedContent = content.length > 500 ? `${content.slice(0, 500).trim()}...` : content;

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.96 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className='fixed z-50 max-h-[280px] w-[360px] overflow-hidden rounded-xl border border-[#ecebef] bg-white shadow-xl'
          style={{
            left: position.x,
            top: position.y
          }}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        >
          {/* Header */}
          <div className='border-b border-[#ecebef] bg-[#fcfcfd] px-4 py-2.5'>
            <div className='flex items-center gap-2'>
              <FileText className='h-3.5 w-3.5 text-[#6976ae]' />
              <span className='font-inter text-xs font-medium text-[#5e5a72]'>
                Document Preview
              </span>
            </div>
          </div>

          {/* Content */}
          <div className='max-h-[220px] overflow-y-auto p-4'>
            <p className='font-inter text-xs leading-relaxed whitespace-pre-wrap text-[#272532]'>
              {truncatedContent}
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
});

interface SourceItemProps {
  title: string;
  source: DocumentSource;
  index: number;
}

/** Delay in ms before hiding the hover card when mouse leaves */
const HOVER_HIDE_DELAY = 100;

/**
 * Individual source item with hover functionality.
 * Uses hover intent to allow smooth mouse transitions to the preview card.
 */
const SourceItem = memo(function SourceItem({ title, source, index }: Readonly<SourceItemProps>) {
  const [isItemHovered, setIsItemHovered] = useState(false);
  const [isCardHovered, setIsCardHovered] = useState(false);
  const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
  const itemReference = useRef<HTMLDivElement>(null);
  const hideTimeoutReference = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear any pending hide timeout
  const clearHideTimeout = useCallback(() => {
    if (hideTimeoutReference.current) {
      clearTimeout(hideTimeoutReference.current);
      hideTimeoutReference.current = null;
    }
  }, []);

  // Schedule hiding the card after a delay
  const scheduleHide = useCallback(() => {
    clearHideTimeout();
    hideTimeoutReference.current = setTimeout(() => {
      setIsItemHovered(false);
      setIsCardHovered(false);
    }, HOVER_HIDE_DELAY);
  }, [clearHideTimeout]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      clearHideTimeout();
    };
  }, [clearHideTimeout]);

  const handleItemMouseEnter = (event: React.MouseEvent) => {
    clearHideTimeout();

    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();

    // Position card to the right of the item, accounting for viewport bounds
    const cardWidth = 360;
    const cardHeight = 280;
    const padding = 12;

    let x = rect.right + padding;
    let y = rect.top;

    // If card would overflow right edge, position to the left instead
    if (x + cardWidth > window.innerWidth - padding) {
      x = rect.left - cardWidth - padding;
    }

    // If card would overflow bottom, adjust y position
    if (y + cardHeight > window.innerHeight - padding) {
      y = window.innerHeight - cardHeight - padding;
    }

    // Ensure y is not negative
    if (y < padding) {
      y = padding;
    }

    setHoverPosition({ x, y });
    setIsItemHovered(true);
  };

  const handleItemMouseLeave = () => {
    // Schedule hide with delay to allow moving to the card
    scheduleHide();
  };

  const handleCardMouseEnter = () => {
    // Cancel any pending hide when entering the card
    clearHideTimeout();
    setIsCardHovered(true);
  };

  const handleCardMouseLeave = () => {
    // Schedule hide when leaving the card
    scheduleHide();
  };

  // Show card if either the item or the card is hovered
  const isVisible = isItemHovered || isCardHovered;

  return (
    <>
      <motion.div
        ref={itemReference}
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.03 }}
        onMouseEnter={handleItemMouseEnter}
        onMouseLeave={handleItemMouseLeave}
        className='group flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#f1f0f4]'
      >
        {/* Endpoint slug (green) */}
        <span className='font-inter shrink-0 text-xs font-medium text-green-600'>
          {source.slug}
        </span>

        {/* Separator */}
        <span className='font-inter text-xs text-[#b4b0bf]'>:</span>

        {/* Document title */}
        <span className='font-inter truncate text-xs text-[#5e5a72] group-hover:text-[#272532]'>
          {title}
        </span>
      </motion.div>

      <HoverCard
        content={source.content}
        isVisible={isVisible}
        position={hoverPosition}
        onMouseEnter={handleCardMouseEnter}
        onMouseLeave={handleCardMouseLeave}
      />
    </>
  );
});

// =============================================================================
// Main Component
// =============================================================================

interface SourcesSectionProps {
  sources: SourcesData;
}

/**
 * Collapsible section displaying sources from the aggregator response.
 *
 * Features:
 * - Collapsed by default to keep the UI clean
 * - Grouped by endpoint slug with document titles
 * - Hover cards showing document content preview
 * - Smooth animations matching the design system
 */
export function SourcesSection({ sources }: Readonly<SourcesSectionProps>) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((previous) => !previous);
  }, []);

  // Convert sources object to array and count
  const sourceEntries = Object.entries(sources);
  const documentCount = sourceEntries.length;

  // Don't render if no sources
  if (documentCount === 0) {
    return null;
  }

  // Group sources by endpoint slug for better organization
  const groupedSources: Record<string, Array<{ title: string; content: string }>> = {};
  for (const [title, source] of sourceEntries) {
    const existingGroup = groupedSources[source.slug];
    if (existingGroup) {
      existingGroup.push({ title, content: source.content });
    } else {
      groupedSources[source.slug] = [{ title, content: source.content }];
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className='mt-3 rounded-xl border border-[#ecebef] bg-[#fcfcfd]'
    >
      {/* Header / Toggle Button */}
      <button
        onClick={toggleExpanded}
        className='flex w-full items-center justify-between px-4 py-2.5 transition-colors hover:bg-[#f7f6f9]'
      >
        <div className='flex items-center gap-2'>
          <FileText className='h-4 w-4 text-[#6976ae]' />
          <span className='font-inter text-sm font-medium text-[#5e5a72]'>Sources</span>
          <span className='font-inter rounded-full bg-[#6976ae]/10 px-2 py-0.5 text-xs font-medium text-[#6976ae]'>
            {documentCount} {documentCount === 1 ? 'document' : 'documents'}
          </span>
        </div>

        {isExpanded ? (
          <ChevronUp className='h-4 w-4 text-[#b4b0bf]' />
        ) : (
          <ChevronDown className='h-4 w-4 text-[#b4b0bf]' />
        )}
      </button>

      {/* Expandable Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className='overflow-hidden'
          >
            <div className='border-t border-[#ecebef] px-4 py-3'>
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
        )}
      </AnimatePresence>
    </motion.div>
  );
}
