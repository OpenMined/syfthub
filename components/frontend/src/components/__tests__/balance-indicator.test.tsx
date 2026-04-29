import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BalanceIndicator } from '@/components/balance/balance-indicator';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

// Mock wallet context
const { mockUseWalletContext } = vi.hoisted(() => ({
  mockUseWalletContext: vi.fn()
}));

vi.mock('@/context/wallet-context', () => ({
  useWalletContext: (): unknown => mockUseWalletContext()
}));

// Mock settings modal store
const { mockOpenSettings } = vi.hoisted(() => ({
  mockOpenSettings: vi.fn()
}));

vi.mock('@/stores/settings-modal-store', () => ({
  useSettingsModalStore: () => ({ openSettings: mockOpenSettings })
}));

// Mock wallet balance hook
const { mockUseWalletBalance } = vi.hoisted(() => ({
  mockUseWalletBalance: vi.fn()
}));

vi.mock('@/hooks/use-wallet-api', async () => {
  const actual =
    await vi.importActual<typeof import('@/hooks/use-wallet-api')>('@/hooks/use-wallet-api');
  return {
    ...actual,
    useWalletBalance: (): unknown => mockUseWalletBalance()
  };
});

// Mock xendit subscriptions hooks so the credits panel renders without
// pulling in auth-context / TanStack Query.
const { mockUseXenditSubscriptions, mockUseSubscriptionBalance } = vi.hoisted(() => ({
  mockUseXenditSubscriptions: vi.fn(),
  mockUseSubscriptionBalance: vi.fn()
}));

vi.mock('@/hooks/use-xendit-subscriptions', () => ({
  useXenditSubscriptions: (): unknown => mockUseXenditSubscriptions(),
  useSubscriptionBalance: (): unknown => mockUseSubscriptionBalance()
}));

function renderIndicator() {
  return render(
    <MemoryRouter>
      <BalanceIndicator />
    </MemoryRouter>
  );
}

describe('BalanceIndicator', () => {
  let mockRefetch: ReturnType<typeof vi.fn>;
  let mockRefetchSubscriptions: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockRefetch = vi.fn().mockResolvedValue(null);
    mockRefetchSubscriptions = vi.fn().mockResolvedValue(null);

    // Default: configured, loaded, healthy balance
    mockUseWalletContext.mockReturnValue({
      isConfigured: true,
      isLoading: false,
      wallet: { address: '0x1234567890abcdef1234567890abcdef12345678', exists: true },
      fetchWallet: vi.fn(),
      clearError: vi.fn()
    });

    mockUseWalletBalance.mockReturnValue({
      balance: {
        balance: 500,
        currency: 'credits',
        recent_transactions: [],
        wallet_configured: true
      },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    // Default: no funded Xendit subscriptions.
    mockUseXenditSubscriptions.mockReturnValue({
      data: [],
      isLoading: false,
      isFetching: false,
      refetch: mockRefetchSubscriptions
    });
    mockUseSubscriptionBalance.mockReturnValue({
      balance: null,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn()
    });
  });

  it('returns null when wallet info is loading', () => {
    mockUseWalletContext.mockReturnValue({
      isConfigured: false,
      isLoading: true
    });

    const { container } = renderIndicator();
    expect(container.innerHTML).toBe('');
  });

  it('shows "Set up wallet" pill when not configured', () => {
    mockUseWalletContext.mockReturnValue({
      isConfigured: false,
      isLoading: false
    });

    renderIndicator();
    expect(screen.getByText('Set up wallet')).toBeInTheDocument();
  });

  it('opens dropdown when "Set up wallet" pill is clicked', async () => {
    mockUseWalletContext.mockReturnValue({
      isConfigured: false,
      isLoading: false
    });

    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByText('Set up wallet'));
    // Pill toggles dropdown; the actual settings link lives inside the panel.
    expect(screen.getByText('Wallet settings')).toBeInTheDocument();
  });

  it('shows compact balance for healthy balance', () => {
    renderIndicator();
    expect(screen.getByText('500.00')).toBeInTheDocument();
  });

  it('shows balance with K suffix for large numbers', () => {
    mockUseWalletBalance.mockReturnValue({
      balance: {
        balance: 15_000,
        currency: 'credits',
        recent_transactions: [],
        wallet_configured: true
      },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    renderIndicator();
    expect(screen.getByText('15.0K')).toBeInTheDocument();
  });

  it('shows "Error" text on the pill when there is an error', () => {
    mockUseWalletBalance.mockReturnValue({
      balance: null,
      isLoading: false,
      error: 'Network error',
      refetch: mockRefetch
    });

    renderIndicator();
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('opens dropdown on click and renders the credits panel', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();
    // "Endpoint subscriptions" appears both as a section header and inside
    // the empty-state copy, so just confirm at least one rendered.
    expect(screen.getAllByText(/Endpoint subscriptions/i).length).toBeGreaterThan(0);
  });

  it('shows empty subscriptions message when no Xendit wallets are funded', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /account balance/i }));

    expect(screen.getByText(/No endpoint subscriptions yet/i)).toBeInTheDocument();
  });

  it('opens wallet settings from dropdown footer', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /account balance/i }));
    await user.click(screen.getByText('Wallet settings'));

    expect(mockOpenSettings).toHaveBeenCalledWith('payment');
  });

  it('opens subscriptions settings from dropdown footer', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /account balance/i }));
    await user.click(screen.getByText('Manage all'));

    expect(mockOpenSettings).toHaveBeenCalledWith('subscriptions');
  });

  it('closes dropdown on Escape key', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /account balance/i }));
    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByText('Tempo · pathUSD')).not.toBeInTheDocument();
  });

  it('closes dropdown on click outside', async () => {
    renderIndicator();

    fireEvent.click(screen.getByRole('button', { name: /account balance/i }));
    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();

    fireEvent.mouseDown(document.body);

    await waitFor(() => {
      expect(screen.queryByText('Tempo · pathUSD')).not.toBeInTheDocument();
    });
  });
});
