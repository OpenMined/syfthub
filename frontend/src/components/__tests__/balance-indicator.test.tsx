import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BalanceIndicator } from '@/components/balance/balance-indicator';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

// Mock accounting context
const { mockUseAccountingContext } = vi.hoisted(() => ({
  mockUseAccountingContext: vi.fn()
}));

vi.mock('@/context/accounting-context', () => ({
  useAccountingContext: (): unknown => mockUseAccountingContext()
}));

// Mock settings modal context
const { mockOpenSettings } = vi.hoisted(() => ({
  mockOpenSettings: vi.fn()
}));

vi.mock('@/context/settings-modal-context', () => ({
  useSettingsModal: () => ({ openSettings: mockOpenSettings })
}));

// Mock accounting API hooks
const { mockUseAccountingUser, mockUseTransactions } = vi.hoisted(() => ({
  mockUseAccountingUser: vi.fn(),
  mockUseTransactions: vi.fn()
}));

vi.mock('@/hooks/use-accounting-api', () => ({
  useAccountingUser: (): unknown => mockUseAccountingUser(),
  useTransactions: (...parameters: unknown[]): unknown => mockUseTransactions(...parameters)
}));

describe('BalanceIndicator', () => {
  let mockRefetch: ReturnType<typeof vi.fn>;
  let mockRefetchTransactions: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockRefetch = vi.fn().mockResolvedValue(null);
    mockRefetchTransactions = vi.fn().mockResolvedValue(null);

    // Default: configured, loaded, healthy balance
    mockUseAccountingContext.mockReturnValue({
      isConfigured: true,
      isLoading: false,
      credentials: { email: 'test@example.com', password: 'pass' },
      fetchCredentials: vi.fn(),
      updateCredentials: vi.fn()
    });

    mockUseAccountingUser.mockReturnValue({
      user: { email: 'test@example.com', balance: 500 },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    mockUseTransactions.mockReturnValue({
      transactions: [],
      isLoading: false,
      error: null,
      refetch: mockRefetchTransactions
    });
  });

  it('returns null when credentials are loading', () => {
    mockUseAccountingContext.mockReturnValue({
      isConfigured: false,
      isLoading: true
    });

    const { container } = render(<BalanceIndicator />);
    expect(container.innerHTML).toBe('');
  });

  it('shows "Set up billing" when not configured', () => {
    mockUseAccountingContext.mockReturnValue({
      isConfigured: false,
      isLoading: false
    });

    render(<BalanceIndicator />);
    expect(screen.getByText('Set up billing')).toBeInTheDocument();
  });

  it('opens payment settings when "Set up billing" is clicked', async () => {
    mockUseAccountingContext.mockReturnValue({
      isConfigured: false,
      isLoading: false
    });

    const user = userEvent.setup();
    render(<BalanceIndicator />);

    await user.click(screen.getByText('Set up billing'));
    expect(mockOpenSettings).toHaveBeenCalledWith('payment');
  });

  it('shows compact balance for healthy balance', () => {
    render(<BalanceIndicator />);
    // 500 is below 1000, so it shows formatted with 2 decimals
    expect(screen.getByText('500.00')).toBeInTheDocument();
  });

  it('shows balance with K suffix for large numbers', () => {
    mockUseAccountingUser.mockReturnValue({
      user: { email: 'test@example.com', balance: 15_000 },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<BalanceIndicator />);
    expect(screen.getByText('15.0K')).toBeInTheDocument();
  });

  it('shows "Error" text when there is an error', () => {
    mockUseAccountingUser.mockReturnValue({
      user: null,
      isLoading: false,
      error: 'Network error',
      refetch: mockRefetch
    });

    render(<BalanceIndicator />);
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('disables pill button while loading', () => {
    mockUseAccountingUser.mockReturnValue({
      user: null,
      isLoading: true,
      error: null,
      refetch: mockRefetch
    });

    render(<BalanceIndicator />);
    const button = screen.getByRole('button', { name: /account balance/i });
    expect(button).toBeDisabled();
  });

  it('opens dropdown on click and shows full balance', async () => {
    const user = userEvent.setup();
    render(<BalanceIndicator />);

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(screen.getByText('Available Credits')).toBeInTheDocument();
    expect(screen.getByText('credits')).toBeInTheDocument();
  });

  it('shows "No recent transactions" when list is empty', async () => {
    const user = userEvent.setup();
    render(<BalanceIndicator />);

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(screen.getByText('No recent transactions')).toBeInTheDocument();
  });

  it('calls refetch when refresh button is clicked', async () => {
    const user = userEvent.setup();
    render(<BalanceIndicator />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: /account balance/i }));

    // Click refresh
    await user.click(screen.getByRole('button', { name: /refresh balance/i }));

    expect(mockRefetch).toHaveBeenCalled();
    expect(mockRefetchTransactions).toHaveBeenCalled();
  });

  it('opens payment settings from dropdown', async () => {
    const user = userEvent.setup();
    render(<BalanceIndicator />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: /account balance/i }));

    // Click Settings button in footer
    await user.click(screen.getByText('Settings'));

    expect(mockOpenSettings).toHaveBeenCalledWith('payment');
  });

  it('shows low balance warning when balance is below 100', async () => {
    mockUseAccountingUser.mockReturnValue({
      user: { email: 'test@example.com', balance: 50 },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const user = userEvent.setup();
    render(<BalanceIndicator />);

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(
      screen.getByText('Your balance is running low. Consider adding more credits.')
    ).toBeInTheDocument();
  });

  it('shows empty balance warning when balance is zero', async () => {
    mockUseAccountingUser.mockReturnValue({
      user: { email: 'test@example.com', balance: 0 },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const user = userEvent.setup();
    render(<BalanceIndicator />);

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(
      screen.getByText('Your balance is empty. Add credits to continue using services.')
    ).toBeInTheDocument();
  });

  it('shows error message in dropdown when error exists', async () => {
    mockUseAccountingUser.mockReturnValue({
      user: null,
      isLoading: false,
      error: 'Failed to fetch',
      refetch: mockRefetch
    });

    render(<BalanceIndicator />);

    // Open dropdown
    fireEvent.click(screen.getByRole('button', { name: /account balance/i }));

    expect(screen.getByText('Failed to load balance')).toBeInTheDocument();
  });

  it('closes dropdown on Escape key', async () => {
    const user = userEvent.setup();
    render(<BalanceIndicator />);

    // Open dropdown
    await user.click(screen.getByRole('button', { name: /account balance/i }));
    expect(screen.getByText('Available Credits')).toBeInTheDocument();

    // Press Escape
    await user.keyboard('{Escape}');

    expect(screen.queryByText('Available Credits')).not.toBeInTheDocument();
  });

  it('closes dropdown on click outside', async () => {
    render(<BalanceIndicator />);

    // Open dropdown
    fireEvent.click(screen.getByRole('button', { name: /account balance/i }));
    expect(screen.getByText('Available Credits')).toBeInTheDocument();

    // Click outside
    fireEvent.mouseDown(document.body);

    await waitFor(() => {
      expect(screen.queryByText('Available Credits')).not.toBeInTheDocument();
    });
  });
});
