import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface OnboardingState {
  isVisible: boolean;
  hasCompletedOnboarding: boolean;
  hasCompletedFirstQuery: boolean;
  startOnboarding: () => void;
  completeOnboarding: () => void;
  skipOnboarding: () => void;
  markFirstQueryComplete: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      isVisible: false,
      hasCompletedOnboarding: false,
      hasCompletedFirstQuery: false,
      startOnboarding: () => {
        set({ isVisible: true });
      },
      completeOnboarding: () => {
        set({ isVisible: false, hasCompletedOnboarding: true });
      },
      skipOnboarding: () => {
        set({ isVisible: false, hasCompletedOnboarding: true });
      },
      markFirstQueryComplete: () => {
        set({ hasCompletedFirstQuery: true });
      }
    }),
    {
      name: 'syfthub-onboarding',
      partialize: (state) => ({
        hasCompletedOnboarding: state.hasCompletedOnboarding,
        hasCompletedFirstQuery: state.hasCompletedFirstQuery
      })
    }
  )
);
