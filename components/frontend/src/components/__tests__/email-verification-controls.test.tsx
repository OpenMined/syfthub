import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EmailVerificationControls } from '@/components/auth/email-verification-controls';

const { mockUpdateUser } = vi.hoisted(() => ({ mockUpdateUser: vi.fn() }));
vi.mock('@/context/auth-context', () => ({
  useAuth: (): unknown => ({ updateUser: mockUpdateUser })
}));

const { mockVerify, mockResend } = vi.hoisted(() => ({
  mockVerify: vi.fn(),
  mockResend: vi.fn()
}));
vi.mock('@/lib/sdk-client', () => ({
  verifyEmailAPI: (code: string): unknown => mockVerify(code),
  resendEmailVerificationAPI: (): unknown => mockResend()
}));

function setup() {
  render(<EmailVerificationControls email='alice@example.com' />);
}

describe('EmailVerificationControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockResend.mockResolvedValue(null);
    mockVerify.mockResolvedValue({ email: 'alice@example.com', is_email_verified: true });
  });

  it('offers to send a code, with no input until one is asked for', () => {
    setup();

    expect(screen.getByRole('button', { name: 'Verify now' })).toBeEnabled();
    expect(screen.queryByLabelText(/verification code/i)).not.toBeInTheDocument();
  });

  it('sends a code, reveals the input, and blocks resending briefly', async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByRole('button', { name: 'Verify now' }));

    await waitFor(() => {
      expect(mockResend).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByLabelText(/verification code/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Resend in \d+s/ })).toBeDisabled();
    });
  });

  it('keeps Verify disabled until six digits are entered', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('button', { name: 'Verify now' }));

    const input = await screen.findByLabelText(/verification code/i);
    const verify = screen.getByRole('button', { name: 'Verify' });
    expect(verify).toBeDisabled();

    await user.type(input, '123456');
    expect(verify).toBeEnabled();
  });

  it('strips non-digits from the code', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('button', { name: 'Verify now' }));

    const input = await screen.findByLabelText(/verification code/i);
    await user.type(input, '12ab34cd56');

    expect(input).toHaveValue('123456');
  });

  it('folds a confirmed address into the session', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole('button', { name: 'Verify now' }));
    await user.type(await screen.findByLabelText(/verification code/i), '123456');

    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(mockVerify).toHaveBeenCalledWith('123456');
    });
    // Both surfaces render off the session, so updating it makes them vanish.
    expect(mockUpdateUser).toHaveBeenCalled();
  });

  it('reports a rejected code and clears the field, without touching the session', async () => {
    const user = userEvent.setup();
    mockVerify.mockRejectedValue(new Error('Invalid or expired verification code'));
    setup();
    await user.click(screen.getByRole('button', { name: 'Verify now' }));
    await user.type(await screen.findByLabelText(/verification code/i), '000000');

    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid or expired verification code')).toBeInTheDocument();
    });
    expect(mockUpdateUser).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/verification code/i)).toHaveValue('');
  });

  it('reports a failure to send', async () => {
    const user = userEvent.setup();
    mockResend.mockRejectedValue(new Error('Too many codes requested'));
    setup();

    await user.click(screen.getByRole('button', { name: 'Verify now' }));

    await waitFor(() => {
      expect(screen.getByText('Too many codes requested')).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/verification code/i)).not.toBeInTheDocument();
  });
});
