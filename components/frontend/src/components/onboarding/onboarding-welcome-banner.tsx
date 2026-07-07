import { useEffect } from 'react';

import { AnimatePresence, motion } from 'framer-motion';

import { Button } from '@/components/ui/button';
import { useOnboardingStore } from '@/stores/onboarding-store';

interface OnboardingWelcomeBannerProps {
  isVisible: boolean;
  onDismiss: () => void;
}

export function OnboardingWelcomeBanner({
  isVisible,
  onDismiss
}: Readonly<OnboardingWelcomeBannerProps>) {
  const startOnboarding = useOnboardingStore((s) => s.startOnboarding);
  const completeOnboarding = useOnboardingStore((s) => s.completeOnboarding);

  const handleStart = () => {
    startOnboarding();
    onDismiss();
  };

  const handleSkip = () => {
    completeOnboarding();
    onDismiss();
  };

  // Dismiss (skip) on Escape key
  useEffect(() => {
    if (!isVisible) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleSkip();
      }
    };
    globalThis.addEventListener('keydown', handleKeyDown);
    return () => {
      globalThis.removeEventListener('keydown', handleKeyDown);
    };
  }, [isVisible]);

  return (
    <AnimatePresence>
      {isVisible ? (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className='fixed right-6 bottom-6 z-50 w-80'
          role='region'
          aria-label='Welcome'
          aria-live='polite'
        >
          <div className='bg-card text-card-foreground border-border rounded-xl border p-5 shadow-xl'>
            <p className='font-inter text-foreground text-sm font-semibold'>Welcome to SyftHub</p>
            <p className='font-inter text-muted-foreground mt-1 text-sm leading-relaxed'>
              Want a quick tour of the key features?
            </p>
            <div className='mt-4 flex items-center justify-end gap-2'>
              <Button type='button' variant='ghost' size='sm' onClick={handleSkip}>
                Skip
              </Button>
              <Button type='button' size='sm' onClick={handleStart}>
                Start tour
              </Button>
            </div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
