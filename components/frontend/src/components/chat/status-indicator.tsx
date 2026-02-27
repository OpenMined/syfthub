import { memo } from 'react';

import type { PipelineStep, ProcessingStatus, SourceProgressInfo } from '@/hooks/use-chat-workflow';

import { motion } from 'framer-motion';
import Check from 'lucide-react/dist/esm/icons/check';
import Clock from 'lucide-react/dist/esm/icons/clock';
import FileText from 'lucide-react/dist/esm/icons/file-text';
import Layers from 'lucide-react/dist/esm/icons/layers';
import Search from 'lucide-react/dist/esm/icons/search';
import Sparkles from 'lucide-react/dist/esm/icons/sparkles';
import X from 'lucide-react/dist/esm/icons/x';

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtItem,
  ChainOfThoughtStep,
  ChainOfThoughtTrigger
} from '@/components/prompt-kit/chain-of-thought';
import { Loader } from '@/components/prompt-kit/loader';

// =============================================================================
// Step icon helpers
// =============================================================================

const stepIcons: Record<string, React.ReactNode> = {
  retrieval: <Search className='h-3.5 w-3.5' />,
  reranking: <Layers className='h-3.5 w-3.5' />,
  generation: <Sparkles className='h-3.5 w-3.5' />
};

function StepStatusIcon({ step }: Readonly<{ step: PipelineStep }>) {
  if (step.status === 'complete') {
    return (
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 500, damping: 25 }}
      >
        <Check className='h-3.5 w-3.5 text-green-500' />
      </motion.div>
    );
  }
  if (step.status === 'active') {
    return <Loader variant='circular' size='sm' />;
  }
  return (
    <span className='text-muted-foreground/40'>
      {stepIcons[step.id] ?? <FileText className='h-3.5 w-3.5' />}
    </span>
  );
}

// =============================================================================
// Source status sub-components (reused in retrieval step content)
// =============================================================================

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
      className='flex items-center gap-2 py-1'
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
 * Chain-of-thought status indicator showing real-time pipeline progress.
 *
 * Renders each pipeline phase (retrieval → reranking → generation) as a
 * collapsible step. Steps complete as SSE events arrive, providing clear
 * progressive feedback to the user.
 */
export function StatusIndicator({ status }: Readonly<StatusIndicatorProps>) {
  const isError = status.phase === 'error';

  if (isError) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        className='flex items-center gap-2 py-1 text-sm text-red-600'
      >
        <X className='h-4 w-4' />
        <span>{status.message}</span>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
    >
      <ChainOfThought>
        {status.steps.map((step) => {
          const isRetrievalWithSources =
            step.id === 'retrieval' && status.completedSources.length > 0;

          const triggerLabel = step.description
            ? `${step.label} — ${step.description}`
            : step.label;

          let stepClassName: string;
          if (step.status === 'active') {
            stepClassName = 'text-foreground';
          } else if (step.status === 'complete') {
            stepClassName = 'text-muted-foreground';
          } else {
            stepClassName = 'text-muted-foreground/50';
          }

          return (
            <ChainOfThoughtStep
              key={step.id}
              defaultOpen={step.status === 'active' && isRetrievalWithSources}
            >
              <ChainOfThoughtTrigger
                leftIcon={<StepStatusIcon step={step} />}
                swapIconOnHover={isRetrievalWithSources}
                className={stepClassName}
              >
                <span className='font-inter text-[13px]'>
                  {triggerLabel}
                  {step.status === 'active' && step.id !== 'retrieval' ? (
                    <Loader variant='typing' size='sm' className='ml-1.5 inline-flex' />
                  ) : null}
                </span>
              </ChainOfThoughtTrigger>

              {isRetrievalWithSources ? (
                <ChainOfThoughtContent>
                  {status.completedSources.map((source, index) => (
                    <ChainOfThoughtItem key={source.path}>
                      <SourceStatusRow source={source} index={index} />
                    </ChainOfThoughtItem>
                  ))}
                  {status.retrieval && status.retrieval.total > status.retrieval.completed ? (
                    <ChainOfThoughtItem>
                      <span className='font-inter text-muted-foreground text-xs'>
                        {status.retrieval.total - status.retrieval.completed} more{' '}
                        {status.retrieval.total - status.retrieval.completed === 1
                          ? 'source'
                          : 'sources'}{' '}
                        searching…
                      </span>
                    </ChainOfThoughtItem>
                  ) : null}
                  {status.timing?.retrievalMs && step.status === 'complete' ? (
                    <ChainOfThoughtItem>
                      <span className='font-inter text-muted-foreground/60 flex items-center gap-1 text-xs'>
                        <Clock className='h-3 w-3' />
                        Retrieved in {(status.timing.retrievalMs / 1000).toFixed(1)}s
                      </span>
                    </ChainOfThoughtItem>
                  ) : null}
                </ChainOfThoughtContent>
              ) : null}
            </ChainOfThoughtStep>
          );
        })}
      </ChainOfThought>
    </motion.div>
  );
}
