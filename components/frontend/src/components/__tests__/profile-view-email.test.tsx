import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProfileView } from '@/components/profile-view';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock('@/context/auth-context', () => ({ useAuth: (): unknown => mockUseAuth() }));

const { mockAvailable } = vi.hoisted(() => ({ mockAvailable: vi.fn() }));
vi.mock('@/hooks/use-auth-config', () => ({
  useEmailVerificationAvailable: (): unknown => mockAvailable()
}));

vi.mock('@/lib/sdk-client', () => ({
  updateUserProfileAPI: vi.fn(),
  changePasswordAPI: vi.fn(),
  verifyEmailAPI: vi.fn(),
  resendEmailVerificationAPI: vi.fn()
}));

const baseUser = {
  id: '1',
  username: 'maguser',
  email: 'maguser@openmined.org',
  name: 'Mag User',
  full_name: 'Mag User',
  role: 'user',
  is_active: true,
  created_at: '2026-07-21T00:00:00Z',
  updated_at: '2026-07-21T00:00:00Z'
};

function setup(overrides: Record<string, unknown> = {}) {
  mockUseAuth.mockReturnValue({
    user: { ...baseUser, ...overrides },
    updateUser: vi.fn(),
    refreshUser: vi.fn()
  });
  render(<ProfileView />);
}

describe('ProfileView email verification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAvailable.mockReturnValue(true);
  });

  it('offers a way to verify when the address is unverified', () => {
    // The banner is dismissible, so this must always be reachable — otherwise
    // dismissing it leaves no route to verify at all.
    setup({ is_email_verified: false });

    expect(screen.getByText(/not verified/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify now' })).toBeInTheDocument();
  });

  it('shows a tick and no control once verified', () => {
    setup({ is_email_verified: true });

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Verify now' })).not.toBeInTheDocument();
  });

  it('says nothing about verification when the server cannot send email', () => {
    // Addresses cannot be proven in that deployment, so "not verified" would be a
    // permanent complaint about something the reader cannot fix.
    mockAvailable.mockReturnValue(false);
    setup({ is_email_verified: false });

    expect(screen.queryByText(/not verified/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Verify now' })).not.toBeInTheDocument();
    expect(screen.getByText('Email address')).toBeInTheDocument();
  });
});
