import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LoginModal } from '@/components/auth/login-modal';

// Mock framer-motion (used by Modal component)
vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

// Mock auth context with controllable return values
const { mockUseAuth } = vi.hoisted(() => ({
  mockUseAuth: vi.fn()
}));

vi.mock('@/context/auth-context', () => ({
  useAuth: (): unknown => mockUseAuth()
}));

describe('LoginModal', () => {
  let mockLogin: ReturnType<typeof vi.fn>;
  let mockClearError: ReturnType<typeof vi.fn>;
  let onClose: () => void;
  let onSwitchToRegister: () => void;

  beforeEach(() => {
    vi.clearAllMocks();
    mockLogin = vi.fn();
    mockClearError = vi.fn();
    onClose = vi.fn();
    onSwitchToRegister = vi.fn();
    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isLoading: false,
      error: null,
      clearError: mockClearError
    });
  });

  function renderModal(overrides?: { isOpen?: boolean }) {
    return render(
      <LoginModal
        isOpen={overrides?.isOpen ?? true}
        onClose={onClose}
        onSwitchToRegister={onSwitchToRegister}
      />
    );
  }

  it('renders when open', () => {
    renderModal();
    expect(screen.getByText('Welcome back')).toBeInTheDocument();
    expect(screen.getByText('Sign in to your SyftHub account')).toBeInTheDocument();
  });

  it('is hidden when closed', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByText('Welcome back')).not.toBeInTheDocument();
  });

  it('shows validation errors on empty submit', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert');
      expect(alerts.length).toBeGreaterThanOrEqual(2);
    });
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('calls onClose on successful login', async () => {
    mockLogin.mockResolvedValue(null);
    renderModal();

    fireEvent.change(screen.getByPlaceholderText('name@company.com…'), {
      target: { value: 'test@example.com' }
    });
    fireEvent.change(screen.getByPlaceholderText('Enter your password…'), {
      target: { value: 'password123' }
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(mockLogin).toHaveBeenCalledWith({
      email: 'test@example.com',
      password: 'password123'
    });
  });

  it('displays error alert when auth error is set', () => {
    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isLoading: false,
      error: 'Invalid email or password',
      clearError: mockClearError
    });
    renderModal();

    expect(screen.getByText('Invalid email or password')).toBeInTheDocument();
  });

  it('clears error when user types', () => {
    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isLoading: false,
      error: 'Invalid email or password',
      clearError: mockClearError
    });
    renderModal();

    fireEvent.change(screen.getByPlaceholderText('name@company.com…'), {
      target: { value: 'a' }
    });

    expect(mockClearError).toHaveBeenCalled();
  });

  it('calls onSwitchToRegister when Sign up is clicked', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('button', { name: /sign up/i }));

    expect(onSwitchToRegister).toHaveBeenCalled();
  });

  it('shows loading state with button text and overlay', () => {
    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isLoading: true,
      error: null,
      clearError: mockClearError
    });
    renderModal();

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
    expect(screen.getByText('Please wait…')).toBeInTheDocument();
  });

  it('disables inputs during loading', () => {
    mockUseAuth.mockReturnValue({
      login: mockLogin,
      isLoading: true,
      error: null,
      clearError: mockClearError
    });
    renderModal();

    expect(screen.getByPlaceholderText('name@company.com…')).toBeDisabled();
    expect(screen.getByPlaceholderText('Enter your password…')).toBeDisabled();
  });

  it('clears error when modal closes', () => {
    const { rerender } = render(
      <LoginModal isOpen={true} onClose={onClose} onSwitchToRegister={onSwitchToRegister} />
    );

    rerender(
      <LoginModal isOpen={false} onClose={onClose} onSwitchToRegister={onSwitchToRegister} />
    );

    expect(mockClearError).toHaveBeenCalled();
  });

  it('does not call login when validation fails', () => {
    renderModal();

    // Set an invalid email (no @ sign) — password is still empty
    fireEvent.change(screen.getByPlaceholderText('name@company.com…'), {
      target: { value: 'invalid' }
    });

    // Submit the form directly
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- asserted by closest('form')
    const form = screen.getByPlaceholderText('name@company.com…').closest('form')!;
    fireEvent.submit(form);

    // Validation should prevent login from being called
    expect(mockLogin).not.toHaveBeenCalled();
  });
});
