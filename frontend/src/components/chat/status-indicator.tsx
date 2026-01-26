import { memo, useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import ChevronUp from 'lucide-react/dist/esm/icons/chevron-up';
import Clock from 'lucide-react/dist/esm/icons/clock';
import FileText from 'lucide-react/dist/esm/icons/file-text';
import Pencil from 'lucide-react/dist/esm/icons/pencil';
import Search from 'lucide-react/dist/esm/icons/search';
import Sparkles from 'lucide-react/dist/esm/icons/sparkles';
import X from 'lucide-react/dist/esm/icons/x';

// =============================================================================
// Types
// =============================================================================

/**
 * Status of an individual source during retrieval
 */
export interface SourceProgressInfo {
  path: string;
  displayName: string;
  status: 'pending' | 'success' | 'error' | 'timeout';
  documents: number;
}

/**
 * Progress tracking for retrieval phase
 */
export interface RetrievalProgress {
  completed: number;
  total: number;
  documentsFound: number;
}

/**
 * Overall processing status for the chat request
 */
export interface ProcessingStatus {
  phase: 'retrieving' | 'generating' | 'streaming' | 'error';
  message: string;
  retrieval?: RetrievalProgress;
  completedSources: SourceProgressInfo[];
  timing?: {
    retrievalMs?: number;
  };
}

// =============================================================================
// Sub-components
// =============================================================================

/**
 * Animated dots indicator (matching the original ThinkingIndicator style)
 */
const AnimatedDots = memo(function AnimatedDots() {
  return (
    <div className='flex items-center gap-1'>
      {[0, 1, 2].map((index) => (
        <motion.span
          key={index}
          className='bg-secondary inline-block h-1.5 w-1.5 rounded-full'
          animate={{
            opacity: [0.3, 1, 0.3],
            scale: [0.85, 1, 0.85]
          }}
          transition={{
            duration: 1.2,
            repeat: Infinity,
            delay: index * 0.2,
            ease: 'easeInOut'
          }}
        />
      ))}
    </div>
  );
});

/**
 * Phase icon with appropriate animation
 */
const PhaseIcon = memo(function PhaseIcon({
  phase
}: Readonly<{ phase: ProcessingStatus['phase'] }>) {
  const iconClass = 'h-4 w-4';

  switch (phase) {
    case 'retrieving': {
      return (
        <motion.div
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Search className={`${iconClass} text-secondary`} />
        </motion.div>
      );
    }
    case 'generating': {
      return (
        <motion.div
          animate={{ rotate: [0, 10, -10, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Sparkles className={`${iconClass} text-secondary`} />
        </motion.div>
      );
    }
    case 'streaming': {
      return (
        <motion.div
          animate={{ y: [0, -2, 0] }}
          transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Pencil className={`${iconClass} text-secondary`} />
        </motion.div>
      );
    }
    case 'error': {
      return <AlertCircle className={`${iconClass} text-red-500`} />;
    }
    default: {
      return <FileText className={`${iconClass} text-muted-foreground`} />;
    }
  }
});

/**
 * Status icon for a completed source
 */
const SourceStatusIcon = memo(function SourceStatusIcon({
  status
}: Readonly<{ status: SourceProgressInfo['status'] }>) {
  const iconClass = 'h-3.5 w-3.5';

  switch (status) {
    case 'success': {
      return (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 25 }}
        >
          <Check className={`${iconClass} text-green-500`} />
        </motion.div>
      );
    }
    case 'error': {
      return <X className={`${iconClass} text-red-500`} />;
    }
    case 'timeout': {
      return <Clock className={`${iconClass} text-yellow-500`} />;
    }
    case 'pending': {
      return (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        >
          <div className={`${iconClass} border-muted border-t-secondary rounded-full border-2`} />
        </motion.div>
      );
    }
    default: {
      return null;
    }
  }
});

/**
 * Row showing status of a single source
 */
const SourceStatusRow = memo(function SourceStatusRow({
  source,
  index
}: Readonly<{ source: SourceProgressInfo; index: number }>) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className='flex items-center gap-2 py-1.5'
    >
      <SourceStatusIcon status={source.status} />
      <span className='font-inter text-foreground text-xs font-medium'>{source.displayName}</span>
      {source.status === 'success' && source.documents > 0 ? (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className='font-inter text-muted-foreground text-xs'
        >
          {source.documents} {source.documents === 1 ? 'doc' : 'docs'}
        </motion.span>
      ) : null}
      {source.status === 'error' ? (
        <span className='font-inter text-xs text-red-500'>failed</span>
      ) : null}
      {source.status === 'timeout' ? (
        <span className='font-inter text-xs text-yellow-600'>timeout</span>
      ) : null}
    </motion.div>
  );
});

// =============================================================================
// Main Component
// =============================================================================

interface StatusIndicatorProps {
  status: ProcessingStatus;
}

/**
 * Interactive status indicator that shows real-time progress during chat processing.
 *
 * Features:
 * - Single status line that updates as phases change
 * - Optional expandable details showing per-source progress
 * - Smooth animations for all transitions
 */
export function StatusIndicator({ status }: Readonly<StatusIndicatorProps>) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails = status.completedSources.length > 0;
  const isError = status.phase === 'error';

  // Calculate pending sources count during retrieval
  const pendingCount =
    status.phase === 'retrieving' && status.retrieval
      ? status.retrieval.total - status.retrieval.completed
      : 0;

  const toggleExpanded = useCallback(() => {
    setIsExpanded((previous) => !previous);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className='border-border bg-muted rounded-2xl rounded-bl-none border shadow-sm'
    >
      {/* Main Status Line */}
      <div className='px-5 py-3'>
        <div className='flex items-center gap-2'>
          <PhaseIcon phase={status.phase} />

          <AnimatePresence mode='wait'>
            <motion.span
              key={status.message}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.2 }}
              className={`font-inter text-sm ${isError ? 'text-red-600' : 'text-muted-foreground'}`}
            >
              {status.message}
            </motion.span>
          </AnimatePresence>

          {/* Progress fraction */}
          {status.retrieval && status.phase === 'retrieving' ? (
            <span className='font-inter text-muted-foreground text-xs'>
              ({status.retrieval.completed}/{status.retrieval.total})
            </span>
          ) : null}

          {/* Animated dots (not shown for error state) */}
          {isError ? null : <AnimatedDots />}
        </div>

        {/* Documents found summary */}
        {status.retrieval && status.retrieval.documentsFound > 0 && status.phase !== 'error' ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className='mt-1 flex items-center gap-1.5 pl-6'
          >
            <FileText className='text-muted-foreground h-3 w-3' />
            <span className='font-inter text-muted-foreground text-xs'>
              {status.retrieval.documentsFound}{' '}
              {status.retrieval.documentsFound === 1 ? 'document' : 'documents'} found
            </span>
          </motion.div>
        ) : null}

        {/* Expand/Collapse button */}
        {hasDetails ? (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            onClick={toggleExpanded}
            className='text-secondary hover:text-foreground mt-2 flex items-center gap-1 pl-6 text-xs transition-colors'
          >
            {isExpanded ? (
              <>
                <ChevronUp className='h-3 w-3' />
                <span>Hide details</span>
              </>
            ) : (
              <>
                <ChevronDown className='h-3 w-3' />
                <span>Show details</span>
              </>
            )}
          </motion.button>
        ) : null}
      </div>

      {/* Expandable Details */}
      <AnimatePresence>
        {isExpanded && hasDetails ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className='overflow-hidden'
          >
            <div className='border-border bg-card/50 border-t px-5 py-3'>
              <div className='space-y-0.5 pl-1'>
                {status.completedSources.map((source, index) => (
                  <SourceStatusRow key={source.path} source={source} index={index} />
                ))}

                {/* Show pending sources indicator */}
                {pendingCount > 0 ? (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className='text-muted-foreground flex items-center gap-2 py-1.5'
                  >
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    >
                      <div className='border-muted border-t-secondary h-3.5 w-3.5 rounded-full border-2' />
                    </motion.div>
                    <span className='font-inter text-xs'>
                      {pendingCount} more {pendingCount === 1 ? 'source' : 'sources'} searching…
                    </span>
                  </motion.div>
                ) : null}

                {/* Timing information */}
                {status.timing?.retrievalMs && status.phase !== 'retrieving' ? (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className='border-border text-muted-foreground mt-2 flex items-center gap-1.5 border-t pt-2'
                  >
                    <Clock className='h-3 w-3' />
                    <span className='font-inter text-xs'>
                      Retrieved in {(status.timing.retrievalMs / 1000).toFixed(1)}s
                    </span>
                  </motion.div>
                ) : null}
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
}
