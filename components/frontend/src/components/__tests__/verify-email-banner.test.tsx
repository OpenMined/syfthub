import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { VerifyEmailBanner } from '@/components/auth/verify-email-banner';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock('@/context/auth-context', () => ({ useAuth: (): unknown => mockUseAuth() }));

const { mockAvailable } = vi.hoisted(() => ({ mockAvailable: vi.fn() }));
vi.mock('@/hooks/use-auth-config', () => ({
  useEmailVerificationAvailable: (): unknown => mockAvailable()
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
    mockAvailable.mockReturnValue(true);
    mockResend.mockResolvedValue(null);
    mockVerify.mockResolvedValue({ ...verifiedUser, is_email_verified: true });
  });

  it('stays hidden when the address is verified', () => {
    setup();
    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
  });

  it('shows when the address is unverified', () => {
    setup({ is_email_verified: false });
    expect(screen.getByTestId('verify-email-banner')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('stays hidden when the server cannot send email', () => {
    // No code could ever arrive, so prompting would be a dead end.
    mockAvailable.mockReturnValue(false);
    setup({ is_email_verified: false });
    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
  });

  it('stays hidden when there is no user', () => {
    mockUseAuth.mockReturnValue({ user: null, updateUser: vi.fn() });
    render(<VerifyEmailBanner />);
    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
  });

  it('can be dismissed, and stays dismissed for the session', async () => {
    const user = userEvent.setup();
    setup({ is_email_verified: false });

    await user.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(screen.queryByTestId('verify-email-banner')).not.toBeInTheDocument();
    // "Not now", not "never" — session-scoped so it returns next visit.
    expect(sessionStorage.getItem('syft_verify_email_dismissed')).toBe('1');
  });

  it('sends a code and reveals the input', async () => {
    const user = userEvent.setup();
    setup({ is_email_verified: false });

    await user.click(screen.getByRole('button', { name: 'Send me a code' }));

    await waitFor(() => {
      expect(mockResend).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Resend in \d+s/ })).toBeDisabled();
    });
  });

  it('verifies a code and hands the updated user back', async () => {
    const user = userEvent.setup();
    const { updateUser } = setup({ is_email_verified: false });
    await user.click(screen.getByRole('button', { name: 'Send me a code' }));

    await user.type(await screen.findByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(mockVerify).toHaveBeenCalledWith('123456');
    });
    expect(updateUser).toHaveBeenCalled();
  });

  it('reports a rejected code and clears the field', async () => {
    const user = userEvent.setup();
    mockVerify.mockRejectedValue(new Error('Invalid or expired verification code'));
    const { updateUser } = setup({ is_email_verified: false });
    await user.click(screen.getByRole('button', { name: 'Send me a code' }));

    await user.type(await screen.findByLabelText(/verification code/i), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid or expired verification code')).toBeInTheDocument();
    });
    expect(updateUser).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/verification code/i)).toHaveValue('');
  });

  it('strips non-digits from the code', async () => {
    const user = userEvent.setup();
    setup({ is_email_verified: false });
    await user.click(screen.getByRole('button', { name: 'Send me a code' }));

    const input = await screen.findByLabelText(/verification code/i);
    await user.type(input, '12ab34cd56');

    expect(input).toHaveValue('123456');
  });
});
