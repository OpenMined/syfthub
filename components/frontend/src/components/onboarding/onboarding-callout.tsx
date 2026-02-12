import { useEffect } from 'react';

import type { OnboardingStep } from '@/stores/onboarding-store';

import { AnimatePresence, motion } from 'framer-motion';

import { cn } from '@/lib/utils';
import { useOnboardingStore } from '@/stores/onboarding-store';

const TOTAL_STEPS = 6;

const STEP_INDEX: Record<OnboardingStep, number> = {
  'model-selector': 1,
  'add-sources': 2,
  'select-sources': 3,
  'query-input': 4,
  'sources-section': 5,
  balance: 6
};

const STEP_MESSAGES: Record<OnboardingStep, string> = {
  'model-selector':
    'Choose an AI model to power your queries. Each has different capabilities and costs.',
  'add-sources':
    'Click here to select data sources. This grounds your answer in specific datasets.',
  'select-sources': 'Select one or more data sources to include as context for your query.',
  'query-input':
    'Type your question here. Your query will use the selected model and data sources.',
  'sources-section':
    'Expand this to see which documents were used. Hover over items for a preview.',
  balance: 'Your credit balance lives here.'
};

interface OnboardingCalloutProps {
  step: OnboardingStep;
  position?: 'top' | 'bottom' | 'left' | 'right';
  children: React.ReactNode;
}

export function OnboardingCallout({
  step,
  position = 'bottom',
  children
}: Readonly<OnboardingCalloutProps>) {
  const currentStep = useOnboardingStore((s) => s.currentStep);
  const dismissStep = useOnboardingStore((s) => s.dismissStep);
  const isActive = currentStep === step;

  // Auto-hide the balance step after 5 seconds
  useEffect(() => {
    if (isActive && step === 'balance') {
      const timer = setTimeout(() => {
        dismissStep();
      }, 5000);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [isActive, step, dismissStep]);

  const stepNumber = STEP_INDEX[step];
  const message = STEP_MESSAGES[step];

  // Animation direction based on position
  const getInitial = () => {
    switch (position) {
      case 'top': {
        return { opacity: 0, y: 8 };
      }
      case 'bottom': {
        return { opacity: 0, y: -8 };
      }
      case 'left': {
        return { opacity: 0, x: 8 };
      }
      case 'right': {
        return { opacity: 0, x: -8 };
      }
    }
  };

  // Arrow styles based on position
  const arrowClasses = cn(
    'bg-primary absolute h-2.5 w-2.5 rotate-45',
    position === 'top' && 'bottom-[-5px] left-1/2 -translate-x-1/2',
    position === 'bottom' && 'top-[-5px] left-1/2 -translate-x-1/2',
    position === 'left' && 'right-[-5px] top-1/2 -translate-y-1/2',
    position === 'right' && 'left-[-5px] top-1/2 -translate-y-1/2'
  );

  // Tooltip positioning classes
  const tooltipClasses = cn(
    'absolute z-50 w-72',
    position === 'top' && 'bottom-full left-1/2 mb-3 -translate-x-1/2',
    position === 'bottom' && 'top-full left-1/2 mt-3 -translate-x-1/2',
    position === 'left' && 'right-full top-1/2 mr-3 -translate-y-1/2',
    position === 'right' && 'left-full top-1/2 ml-3 -translate-y-1/2'
  );

  return (
    <div className='relative'>
      {children}
      <AnimatePresence>
        {isActive ? (
          <motion.div
            initial={getInitial()}
            animate={{ opacity: 1, x: 0, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className={tooltipClasses}
            role='tooltip'
          >
            <div className='bg-primary text-primary-foreground rounded-lg px-4 py-3 shadow-lg'>
              <div className={arrowClasses} />
              <p className='font-inter text-sm leading-relaxed'>{message}</p>
              <div className='mt-2 flex items-center justify-between'>
                <span className='font-inter text-primary-foreground/70 text-xs'>
                  {stepNumber} of {TOTAL_STEPS}
                </span>
                <button
                  type='button'
                  onClick={dismissStep}
                  className='font-inter bg-primary-foreground/20 hover:bg-primary-foreground/30 rounded px-2.5 py-1 text-xs font-medium transition-colors'
                >
                  Got it
                </button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
