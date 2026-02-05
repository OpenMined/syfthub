import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type OnboardingStep =
  | 'model-selector'
  | 'add-sources'
  | 'select-sources'
  | 'query-input'
  | 'sources-section'
  | 'balance';

const STEP_SEQUENCE: OnboardingStep[] = [
  'model-selector',
  'add-sources',
  'select-sources',
  'query-input',
  'sources-section',
  'balance'
];

interface OnboardingState {
  currentStep: OnboardingStep | null;
  hasCompletedOnboarding: boolean;
  startOnboarding: () => void;
  dismissStep: () => void;
  showSourcesStep: () => void;
  completeOnboarding: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set, get) => ({
      currentStep: null,
      hasCompletedOnboarding: false,

      startOnboarding: () => {
        if (!get().hasCompletedOnboarding) {
          set({ currentStep: 'model-selector' });
        }
      },

      dismissStep: () => {
        const { currentStep } = get();
        if (!currentStep) return;

        const currentIndex = STEP_SEQUENCE.indexOf(currentStep);

        // After 'query-input', pause and wait for first query
        if (currentStep === 'query-input') {
          set({ currentStep: null });
          return;
        }

        // After 'balance', complete onboarding
        if (currentStep === 'balance') {
          set({ currentStep: null, hasCompletedOnboarding: true });
          return;
        }

        // Advance to next step in sequence
        const nextStep = STEP_SEQUENCE[currentIndex + 1];
        if (nextStep) {
          set({ currentStep: nextStep });
        }
      },

      showSourcesStep: () => {
        if (!get().hasCompletedOnboarding) {
          set({ currentStep: 'sources-section' });
        }
      },

      completeOnboarding: () => {
        set({ currentStep: null, hasCompletedOnboarding: true });
      }
    }),
    {
      name: 'syfthub-onboarding',
      partialize: (state) => ({
        hasCompletedOnboarding: state.hasCompletedOnboarding,
        currentStep: state.currentStep
      })
    }
  )
);
