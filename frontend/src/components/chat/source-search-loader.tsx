/**
 * SourceSearchLoader - Loading skeleton for semantic search
 *
 * Displays minimalistic animated skeleton cards while searching
 * for relevant data sources using RAG semantic search.
 */

import { motion } from 'framer-motion';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';

interface SourceSearchLoaderProps {
  /** Number of skeleton cards to display (default: 3) */
  skeletonCount?: number;
  /** Optional message to display (default: "Finding relevant sources...") */
  message?: string;
}

/**
 * Individual skeleton card that mimics the SourceSelector card layout.
 */
function SkeletonCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className='border-border bg-card relative flex w-full items-start gap-4 rounded-xl border p-4'
    >
      <div className='min-w-0 flex-1'>
        {/* Header skeleton */}
        <div className='mb-1 flex flex-wrap items-center gap-2'>
          {/* Title */}
          <div className='from-muted via-muted/70 to-muted h-5 w-32 animate-pulse rounded-md bg-gradient-to-r bg-[length:200%_100%]' />
          {/* Tags */}
          <div className='bg-muted h-5 w-14 animate-pulse rounded-md' />
          <div className='bg-muted h-5 w-16 animate-pulse rounded-md' />
        </div>

        {/* Description skeleton */}
        <div className='mb-2 flex items-start gap-2'>
          <div className='bg-muted mt-1.5 h-2 w-2 shrink-0 animate-pulse rounded-full' />
          <div className='flex-1 space-y-1.5'>
            <div className='bg-muted h-4 w-full animate-pulse rounded' />
            <div className='bg-muted h-4 w-3/4 animate-pulse rounded' />
          </div>
        </div>

        {/* Footer skeleton */}
        <div className='flex items-center gap-1.5'>
          <div className='bg-muted h-3.5 w-3.5 animate-pulse rounded-full' />
          <div className='bg-muted h-3 w-24 animate-pulse rounded' />
        </div>
      </div>

      {/* Checkbox skeleton */}
      <div className='border-input bg-card mt-1 h-6 w-6 animate-pulse rounded border' />
    </motion.div>
  );
}

/**
 * Compact inline loader for use in search inputs.
 */
export function InlineSearchLoader() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className='flex items-center gap-2 px-2 py-1'
    >
      <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' />
      <span className='font-inter text-muted-foreground text-xs'>Searching...</span>
    </motion.div>
  );
}

/**
 * Main search loader component with message and skeleton cards.
 */
export function SourceSearchLoader({
  skeletonCount = 3,
  message = 'Finding relevant sources...'
}: Readonly<SourceSearchLoaderProps>) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className='my-4 w-full max-w-3xl space-y-3'
    >
      {/* Search status message */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className='border-border bg-muted mb-4 flex items-center gap-3 rounded-xl border px-4 py-3'
      >
        <div className='relative'>
          <Search className='text-muted-foreground h-4 w-4' />
          <motion.div
            className='bg-primary/20 absolute -inset-1 rounded-full'
            animate={{
              scale: [1, 1.5, 1],
              opacity: [0.5, 0, 0.5]
            }}
            transition={{
              duration: 1.5,
              repeat: Number.POSITIVE_INFINITY,
              ease: 'easeInOut'
            }}
          />
        </div>
        <span className='font-inter text-muted-foreground text-sm'>{message}</span>
        <Loader2 className='text-muted-foreground ml-auto h-4 w-4 animate-spin' />
      </motion.div>

      {/* Skeleton cards */}
      <div className='space-y-3'>
        {Array.from({ length: skeletonCount }).map((_, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + index * 0.08 }}
          >
            <SkeletonCard />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/**
 * Minimal loader variant with just the message (no skeletons).
 */
export function MinimalSearchLoader({ message = 'Searching...' }: Readonly<{ message?: string }>) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className='flex items-center gap-2 py-2'
    >
      <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />
      <span className='font-inter text-muted-foreground text-sm'>{message}</span>
    </motion.div>
  );
}
