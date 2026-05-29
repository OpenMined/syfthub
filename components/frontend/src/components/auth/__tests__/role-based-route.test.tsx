import type { User } from '@/lib/types';

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RoleBasedRoute } from '../role-based-route';

const { mockUseAuth } = vi.hoisted(() => ({
  mockUseAuth: vi.fn()
}));

vi.mock('@/context/auth-context', () => ({
  useAuth: (): unknown => mockUseAuth()
}));

function makeUser(role: User['role']): User {
  return {
    id: '1',
    username: 'jane',
    email: 'jane@example.com',
    name: 'Jane Doe',
    full_name: 'Jane Doe',
    role,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z'
  };
}

function renderGuard() {
  return render(
    <MemoryRouter>
      <RoleBasedRoute requiredRole='admin'>
        <div>secret admin content</div>
      </RoleBasedRoute>
    </MemoryRouter>
  );
}

describe('RoleBasedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a spinner while auth is initializing', () => {
    mockUseAuth.mockReturnValue({ user: null, isInitializing: true });
    renderGuard();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(screen.queryByText('secret admin content')).not.toBeInTheDocument();
  });

  it('renders children for a matching role', () => {
    mockUseAuth.mockReturnValue({ user: makeUser('admin'), isInitializing: false });
    renderGuard();
    expect(screen.getByText('secret admin content')).toBeInTheDocument();
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument();
  });

  it('renders access denied for a non-admin user', () => {
    mockUseAuth.mockReturnValue({ user: makeUser('user'), isInitializing: false });
    renderGuard();
    expect(screen.getByText('Access denied')).toBeInTheDocument();
    expect(screen.queryByText('secret admin content')).not.toBeInTheDocument();
  });

  it('renders access denied when there is no user', () => {
    mockUseAuth.mockReturnValue({ user: null, isInitializing: false });
    renderGuard();
    expect(screen.getByText('Access denied')).toBeInTheDocument();
  });
});
