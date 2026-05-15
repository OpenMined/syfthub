import { motion } from 'framer-motion';

import { OpenMinedIcon } from '@/components/ui/openmined-icon';

/**
 * Trailing "assistant is composing" indicator shown while the agent is
 * running but has not yet emitted the next token.
 *
 * Anchored to the assistant avatar at the same position as a real message
 * row, so the reply streams in without a layout jump. The avatar carries a
 * soft breathing halo and the label uses a slow shimmer sweep — calm,
 * deliberate motion rather than a blinking dot.
 *
 * Wrap the render site in <AnimatePresence> so the exit transition fires.
 */
export function ThinkingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className='flex max-w-3xl items-start gap-3'
      role='status'
      aria-label='Assistant is thinking'
    >
      <div className='relative mt-0.5 h-8 w-8 shrink-0'>
        <span
          aria-hidden='true'
          className='bg-primary/35 motion-safe:animate-[thinking-halo_2.4s_ease-in-out_infinite] absolute -inset-0.5 rounded-full blur-[5px]'
        />
        <div className='bg-muted relative flex h-8 w-8 items-center justify-center rounded-full'>
          <OpenMinedIcon className='h-5 w-5' />
        </div>
      </div>
      <div className='flex h-8 items-center'>
        <span className='thinking-shimmer font-inter text-sm font-medium'>Thinking…</span>
      </div>
    </motion.div>
  );
}
