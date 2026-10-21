import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SecuritySettingsTab } from '@/components/settings/security-settings-tab';

const { mockUseAuth, mockChangePassword, mockRefreshUser } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockChangePassword: vi.fn(),
  mockRefreshUser: vi.fn()
}));

vi.mock('@/context/auth-context', () => ({
  useAuth: (): unknown => mockUseAuth()
}));

vi.mock('@/lib/sdk-client', () => ({
  changePasswordAPI: (...callArguments: unknown[]): unknown => mockChangePassword(...callArguments)
}));

function authWith(hasPassword?: boolean) {
  mockUseAuth.mockReturnValue({
    user: {
      id: '1',
      username: 'u',
      email: 'u@example.com',
      updated_at: '2026-10-01T00:00:00Z',
      has_password: hasPassword
    },
    refreshUser: mockRefreshUser
  });
}

describe('SecuritySettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChangePassword.mockImplementation(() => Promise.resolve());
    mockRefreshUser.mockImplementation(() => Promise.resolve());
  });

  it('asks a password account for its current password', () => {
    authWith(true);
    render(<SecuritySettingsTab />);

    expect(screen.getByLabelText('Current Password')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Change Password' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change password/i })).toBeDisabled();
  });

  it('treats a missing flag as a password account', () => {
    authWith();
    render(<SecuritySettingsTab />);

    expect(screen.getByLabelText('Current Password')).toBeInTheDocument();
  });

  it('lets a Google-only account set a first password without a current one', async () => {
    authWith(false);
    const user = userEvent.setup();
    render(<SecuritySettingsTab />);

    expect(screen.queryByLabelText('Current Password')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Set a Password' })).toBeInTheDocument();
    expect(screen.getByText(/You sign in with Google/)).toBeInTheDocument();

    await user.type(screen.getByLabelText('New Password'), 'newpass123');
    await user.type(screen.getByLabelText('Confirm New Password'), 'newpass123');
    const submit = screen.getByRole('button', { name: /set password/i });
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith({
        current_password: '',
        new_password: 'newpass123'
      });
    });
    expect(mockRefreshUser).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Password set/)).toBeInTheDocument();
  });

  it('shows the server message when setting a password fails', async () => {
    authWith(false);
    mockChangePassword.mockRejectedValue(
      new Error('New password must be at least 8 characters long')
    );
    const user = userEvent.setup();
    render(<SecuritySettingsTab />);

    await user.type(screen.getByLabelText('New Password'), 'abcdefg1');
    await user.type(screen.getByLabelText('Confirm New Password'), 'abcdefg1');
    await user.click(screen.getByRole('button', { name: /set password/i }));

    expect(
      await screen.findByText('New password must be at least 8 characters long')
    ).toBeInTheDocument();
    expect(mockRefreshUser).not.toHaveBeenCalled();
  });
});
