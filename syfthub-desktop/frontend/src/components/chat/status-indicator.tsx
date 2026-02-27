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

import { Loader } from '@/components/prompt-kit/loader';

// =============================================================================
// Types (re-exported so ChatView can import from a single place)
// =============================================================================

export interface SourceProgressInfo {
  path: string;
  displayName: string;
  status: 'pending' | 'success' | 'error' | 'timeout';
  documents: number;
}

export interface RetrievalProgress {
  completed: number;
  total: number;
  documentsFound: number;
}

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
      <span className='text-foreground text-xs font-medium'>{source.displayName}</span>
      {source.status === 'success' && source.documents > 0 ? (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className='text-muted-foreground text-xs'
        >
          {source.documents} {source.documents === 1 ? 'doc' : 'docs'}
        </motion.span>
      ) : null}
      {source.status === 'error' ? (
        <span className='text-xs text-red-500'>failed</span>
      ) : null}
      {source.status === 'timeout' ? (
        <span className='text-xs text-yellow-600'>timeout</span>
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

export function StatusIndicator({ status }: Readonly<StatusIndicatorProps>) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails = status.completedSources.length > 0;
  const isError = status.phase === 'error';

  const pendingCount =
    status.phase === 'retrieving' && status.retrieval
      ? status.retrieval.total - status.retrieval.completed
      : 0;

  const toggleExpanded = useCallback(() => {
    setIsExpanded((previous) => !previous);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
    >
      <div className='flex items-center gap-2.5 py-1'>
        <PhaseIcon phase={status.phase} />

        <AnimatePresence mode='wait'>
          <motion.span
            key={status.message}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className={`text-[13px] ${isError ? 'text-red-600' : 'text-muted-foreground'}`}
          >
            {status.message}
          </motion.span>
        </AnimatePresence>

        {status.retrieval && status.phase === 'retrieving' ? (
          <span className='text-muted-foreground/60 text-xs tabular-nums'>
            {status.retrieval.completed}/{status.retrieval.total}
          </span>
        ) : null}

        {isError ? null : <Loader variant='typing' size='sm' className='ml-0.5' />}
      </div>

      {status.retrieval && status.retrieval.documentsFound > 0 && status.phase !== 'error' ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className='mt-0.5 flex items-center gap-1.5 pl-[26px]'
        >
          <FileText className='text-muted-foreground/60 h-3 w-3' />
          <span className='text-muted-foreground/70 text-xs'>
            {status.retrieval.documentsFound}{' '}
            {status.retrieval.documentsFound === 1 ? 'document' : 'documents'} found
          </span>
        </motion.div>
      ) : null}

      {hasDetails ? (
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          onClick={toggleExpanded}
          className='text-muted-foreground hover:text-foreground mt-1.5 flex items-center gap-1 pl-[26px] text-xs transition-colors'
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

      <AnimatePresence>
        {isExpanded && hasDetails ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className='overflow-hidden'
          >
            <div className='border-border/60 bg-muted/40 mt-2 rounded-lg border px-4 py-3'>
              <div className='space-y-0.5'>
                {status.completedSources.map((source, index) => (
                  <SourceStatusRow key={source.path} source={source} index={index} />
                ))}

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
                    <span className='text-xs'>
                      {pendingCount} more {pendingCount === 1 ? 'source' : 'sources'} searching…
                    </span>
                  </motion.div>
                ) : null}

                {status.timing?.retrievalMs && status.phase !== 'retrieving' ? (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className='border-border/40 text-muted-foreground mt-2 flex items-center gap-1.5 border-t pt-2'
                  >
                    <Clock className='h-3 w-3' />
                    <span className='text-xs'>
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
