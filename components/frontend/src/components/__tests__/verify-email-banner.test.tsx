import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { VerifyEmailBanner } from '@/components/auth/verify-email-banner';
import { useVerifyEmailBannerStore } from '@/stores/verify-email-banner-store';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock('@/context/auth-context', () => ({ useAuth: (): unknown => mockUseAuth() }));

const { mockShouldPrompt } = vi.hoisted(() => ({ mockShouldPrompt: vi.fn() }));
vi.mock('@/hooks/use-auth-config', () => ({
  useShouldPromptEmailVerification: (): unknown => mockShouldPrompt()
}));

const { mockVerify, mockResend } = vi.hoisted(() => ({
  mockVerify: vi.fn(),
  mockResend: vi.fn()
}));
vi.mock('@/lib/sdk-client', () => ({
  verifyEmailAPI: (code: string): unknown => mockVerify(code),
  resendEmailVerificationAPI: (): unknown => mockResend()
}));

const verifiedUser = {
  id: '1',
  username: 'alice',
  email: 'alice@example.com',
  name: 'Alice',
  full_name: 'Alice',
  role: 'user',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_email_verified: true
};

function setup(overrides: Record<string, unknown> = {}) {
  const updateUser = vi.fn();
  mockUseAuth.mockReturnValue({ user: { ...verifiedUser, ...overrides }, updateUser });
  render(<VerifyEmailBanner />);
  return { updateUser };
}

describe('VerifyEmailBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockShouldPrompt.mockReturnValue(true);
    useVerifyEmailBannerStore.setState({ dismissed: false });
    mockResend.mockResolvedValue(null);
    mockVerify.mockResolvedValue({ ...verifiedUser, is_email_verified: true });
  });

  it('stays hidden when the prompt is not wanted', () => {
    // Verified, dismissed, no user, or a server that cannot send email — the
    // hook folds all four into one decision so the banner and the layout, which
    // shifts its header to make room, can never disagree.
    mockShouldPrompt.mockReturnValue(false);
    setup();
    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
  });

  it('shows when the address is unverified', () => {
    setup({ is_email_verified: false });
    expect(screen.getByTestId('verify-email-banner')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('names the address, with a space before the sentence continues', () => {
    // Regression: esbuild trimmed the JSX whitespace after </strong>, rendering
    // "openmined.orgisn't verified yet".
    setup({ is_email_verified: false });

    expect(screen.getByTestId('verify-email-banner')).toHaveTextContent(
      "alice@example.com isn't verified yet"
    );
  });

  it('stays hidden when there is no user', () => {
    mockShouldPrompt.mockReturnValue(false);
    mockUseAuth.mockReturnValue({ user: null, updateUser: vi.fn() });
    render(<VerifyEmailBanner />);
    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
  });

  it('can be dismissed, and stays dismissed for the session', async () => {
    const user = userEvent.setup();
    setup({ is_email_verified: false });

    await user.click(screen.getByRole('button', { name: 'Dismiss' }));

    // "Not now", not "never" — session-scoped so it returns next visit. The
    // store carries it, because the layout needs to know too.
    expect(useVerifyEmailBannerStore.getState().dismissed).toBe(true);
    expect(sessionStorage.getItem('syft_verify_email_dismissed')).toBe('1');
  });
});
