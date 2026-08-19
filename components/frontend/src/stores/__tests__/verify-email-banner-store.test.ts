import { beforeEach, describe, expect, it } from 'vitest';

import { useVerifyEmailBannerStore } from '@/stores/verify-email-banner-store';

const DISMISS_KEY = 'syft_verify_email_dismissed';

describe('useVerifyEmailBannerStore', () => {
  beforeEach(() => {
    sessionStorage.clear();
    useVerifyEmailBannerStore.setState({ dismissed: false });
  });

  it('starts undismissed', () => {
    expect(useVerifyEmailBannerStore.getState().dismissed).toBe(false);
  });

  it('dismiss() persists so a reload does not re-nag mid-session', () => {
    useVerifyEmailBannerStore.getState().dismiss();

    expect(useVerifyEmailBannerStore.getState().dismissed).toBe(true);
    expect(sessionStorage.getItem(DISMISS_KEY)).toBe('1');
  });

  it('reset() clears both the state and the stored flag', () => {
    // Called on logout. sessionStorage outlives an app-level logout, so without
    // this a dismissal would follow the next sign-in — and could hide the prompt
    // from a *different* user signing in on the same tab.
    useVerifyEmailBannerStore.getState().dismiss();

    useVerifyEmailBannerStore.getState().reset();

    expect(useVerifyEmailBannerStore.getState().dismissed).toBe(false);
    expect(sessionStorage.getItem(DISMISS_KEY)).toBeNull();
  });
});
