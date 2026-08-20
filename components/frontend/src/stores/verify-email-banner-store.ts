import { create } from 'zustand';

const DISMISS_KEY = 'syft_verify_email_dismissed';

interface VerifyEmailBannerState {
  dismissed: boolean;
  dismiss: () => void;
  reset: () => void;
}

/**
 * Whether the "verify your email" prompt has been dismissed.
 *
 * In a store rather than component state because two places need it: the banner
 * itself, and the layout, which shifts its floating header down to make room so
 * the two do not overlap.
 *
 * Dismissing means "not now", never "never" — the prompt must come back for as
 * long as the address is unverified. `sessionStorage` alone is not enough for
 * that: it outlives an app-level logout, so without `reset()` on the way out a
 * dismissal would follow the next sign-in, and even leak to a *different* user
 * signing in on the same tab. AuthContext calls `reset()` on logout.
 */
export const useVerifyEmailBannerStore = create<VerifyEmailBannerState>((set) => ({
  dismissed: sessionStorage.getItem(DISMISS_KEY) === '1',
  dismiss: () => {
    sessionStorage.setItem(DISMISS_KEY, '1');
    set({ dismissed: true });
  },
  reset: () => {
    sessionStorage.removeItem(DISMISS_KEY);
    set({ dismissed: false });
  }
}));
