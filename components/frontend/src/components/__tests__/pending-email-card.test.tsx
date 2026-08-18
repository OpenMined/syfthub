import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PendingEmailCard } from '@/components/settings/pending-email-card';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

const { mockVerify, mockResend, mockCancel } = vi.hoisted(() => ({
  mockVerify: vi.fn(),
  mockResend: vi.fn(),
  mockCancel: vi.fn()
}));

vi.mock('@/lib/sdk-client', () => ({
  verifyEmailChangeAPI: (code: string): unknown => mockVerify(code),
  resendEmailChangeCodeAPI: (): unknown => mockResend(),
  cancelEmailChangeAPI: (): unknown => mockCancel()
}));

const updatedUser = {
  id: '1',
  username: 'alice',
  email: 'new@example.com',
  name: 'Alice',
  full_name: 'Alice',
  role: 'user',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  pending_email: undefined
};

function renderCard(onResolved = vi.fn()) {
  render(
    <PendingEmailCard
      pendingEmail='new@example.com'
      currentEmail='alice@example.com'
      onResolved={onResolved}
    />
  );
  return { onResolved };
}

describe('PendingEmailCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerify.mockResolvedValue(updatedUser);
    mockResend.mockResolvedValue(null);
    mockCancel.mockResolvedValue(null);
  });

  it('names the pending address and reassures about the current one', () => {
    renderCard();

    expect(screen.getByText('new@example.com')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText(/stays your address/i)).toBeInTheDocument();
  });

  it('keeps Confirm disabled until a full 6-digit code is entered', async () => {
    const user = userEvent.setup();
    renderCard();

    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(/verification code/i), '123');
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(/verification code/i), '456');
    expect(confirm).toBeEnabled();
  });

  it('strips non-digits from the code input', async () => {
    const user = userEvent.setup();
    renderCard();

    const input = screen.getByLabelText(/verification code/i);
    await user.type(input, '12ab34cd56');

    expect(input).toHaveValue('123456');
  });

  it('hands the updated user back on a successful confirmation', async () => {
    const user = userEvent.setup();
    const { onResolved } = renderCard();

    await user.type(screen.getByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      expect(mockVerify).toHaveBeenCalledWith('123456');
    });
    expect(onResolved).toHaveBeenCalledWith(updatedUser);
  });

  it('shows the error and clears the code on a rejected one, without resolving', async () => {
    const user = userEvent.setup();
    mockVerify.mockRejectedValue(new Error('Invalid or expired verification code'));
    const { onResolved } = renderCard();

    await user.type(screen.getByLabelText(/verification code/i), '000000');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid or expired verification code')).toBeInTheDocument();
    });
    // The change is still pending server-side, so the card must stay put.
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/verification code/i)).toHaveValue('');
  });

  it('resends a code and then blocks resending during the cooldown', async () => {
    const user = userEvent.setup();
    renderCard();

    await user.click(screen.getByRole('button', { name: 'Resend code' }));

    await waitFor(() => {
      expect(mockResend).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Resend in \d+s/ })).toBeDisabled();
    });
  });

  it('resolves with null when the change is cancelled', async () => {
    const user = userEvent.setup();
    const { onResolved } = renderCard();

    await user.click(screen.getByRole('button', { name: 'Cancel change' }));

    await waitFor(() => {
      expect(mockCancel).toHaveBeenCalledTimes(1);
    });
    expect(onResolved).toHaveBeenCalledWith(null);
  });

  it('surfaces a failure to cancel instead of resolving', async () => {
    const user = userEvent.setup();
    mockCancel.mockRejectedValue(new Error('Could not cancel the change'));
    const { onResolved } = renderCard();

    await user.click(screen.getByRole('button', { name: 'Cancel change' }));

    await waitFor(() => {
      expect(screen.getByText('Could not cancel the change')).toBeInTheDocument();
    });
    expect(onResolved).not.toHaveBeenCalled();
  });
});
