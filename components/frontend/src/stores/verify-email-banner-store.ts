import { create } from 'zustand';

const DISMISS_KEY = 'syft_verify_email_dismissed';

interface VerifyEmailBannerState {
  dismissed: boolean;
  dismiss: () => void;
}

/**
 * Whether the "verify your email" prompt has been dismissed this session.
 *
 * In a store rather than component state because two places need it: the banner
 * itself, and the layout, which shifts its floating header down to make room so
 * the two do not overlap.
 *
 * Session-scoped on purpose — dismissing means "not now", not "never", so the
 * prompt returns next visit while the address is still unverified.
 */
export const useVerifyEmailBannerStore = create<VerifyEmailBannerState>((set) => ({
  dismissed: sessionStorage.getItem(DISMISS_KEY) === '1',
  dismiss: () => {
    sessionStorage.setItem(DISMISS_KEY, '1');
    set({ dismissed: true });
  }
}));
