import { motion } from 'framer-motion';
import Coins from 'lucide-react/dist/esm/icons/coins';
import MessageSquare from 'lucide-react/dist/esm/icons/message-square';

import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { useAccountingUser } from '@/hooks/use-accounting-api';
import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboarding-store';

import { formatBalance } from '../balance/balance-display';

export function WelcomeOverlay() {
  const { isVisible, completeOnboarding, skipOnboarding } = useOnboardingStore();
  const { user } = useAccountingUser();

  const balance = user?.balance ?? null;

  return (
    <Modal
      isOpen={isVisible}
      onClose={skipOnboarding}
      title='Welcome to SyftHub'
      description='Get started in seconds — here is everything you need to know.'
      size='xl'
    >
      <div className='space-y-6'>
        {/* Two-card layout */}
        <div className='grid grid-cols-1 gap-4 sm:grid-cols-2'>
          {/* Ask Questions Card */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.3 }}
            className={cn('rounded-xl border p-5', 'border-border bg-muted/50', 'dark:bg-muted/30')}
          >
            <div className='bg-primary/10 mb-3 flex h-10 w-10 items-center justify-center rounded-lg'>
              <MessageSquare className='text-primary h-5 w-5' aria-hidden='true' />
            </div>
            <h3 className='font-rubik text-foreground text-base font-medium'>Ask Questions</h3>
            <p className='font-inter text-muted-foreground mt-1 text-sm leading-relaxed'>
              Navigate to the chat and type any question. SyftHub queries multiple
              privacy-preserving data sources and returns a unified answer.
            </p>
          </motion.div>

          {/* Your Credits Card */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.3 }}
            className={cn('rounded-xl border p-5', 'border-border bg-muted/50', 'dark:bg-muted/30')}
          >
            <div className='mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10'>
              <Coins className='h-5 w-5 text-amber-600 dark:text-amber-400' aria-hidden='true' />
            </div>
            <h3 className='font-rubik text-foreground text-base font-medium'>Your Credits</h3>
            <p className='font-inter text-muted-foreground mt-1 text-sm leading-relaxed'>
              {balance === null ? (
                <>
                  Your credit balance appears in the top-right corner. Set up billing in Settings to
                  start querying.
                </>
              ) : (
                <>
                  You have{' '}
                  <span className='text-foreground font-semibold'>
                    {formatBalance(balance)} credits
                  </span>
                  . Each query costs a small amount — check the balance pill in the top right.
                </>
              )}
            </p>
          </motion.div>
        </div>

        {/* CTA */}
        <div className='flex items-center justify-between'>
          <button
            type='button'
            onClick={skipOnboarding}
            className='font-inter text-muted-foreground hover:text-foreground text-sm underline transition-colors'
          >
            Skip
          </button>
          <Button size='lg' className='font-inter' onClick={completeOnboarding}>
            Start Exploring
          </Button>
        </div>
      </div>
    </Modal>
  );
}
