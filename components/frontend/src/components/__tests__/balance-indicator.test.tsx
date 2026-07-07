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

// CreditsPanel internally uses useWalletBalance for the MPP wallet row.
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

  it('renders an icon-only wallet trigger', () => {
    renderIndicator();
    const button = screen.getByRole('button', { name: /wallet/i });
    expect(button).toBeInTheDocument();
    // No balance text on the trigger itself.
    expect(screen.queryByText('500.00')).not.toBeInTheDocument();
  });

  it('opens the credits panel when the wallet button is clicked', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));

    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();
    expect(screen.getAllByText(/Endpoint credits/i).length).toBeGreaterThan(0);
  });

  it('opens the credits panel when not configured (set-up flow lives inside)', async () => {
    mockUseWalletContext.mockReturnValue({
      isConfigured: false,
      isLoading: false
    });

    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));
    expect(screen.getByText('Wallet settings')).toBeInTheDocument();
  });

  it('shows empty subscriptions message when no Xendit wallets are funded', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));

    expect(screen.getByText(/No endpoint subscriptions yet/i)).toBeInTheDocument();
  });

  it('opens wallet settings from dropdown footer', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));
    await user.click(screen.getByText('Wallet settings'));

    expect(mockOpenSettings).toHaveBeenCalledWith('payment');
  });

  it('opens subscriptions settings from dropdown footer', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));
    await user.click(screen.getByText('Manage all'));

    expect(mockOpenSettings).toHaveBeenCalledWith('subscriptions');
  });

  it('closes dropdown on Escape key', async () => {
    const user = userEvent.setup();
    renderIndicator();

    await user.click(screen.getByRole('button', { name: /wallet/i }));
    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByText('Tempo · pathUSD')).not.toBeInTheDocument();
  });

  it('closes dropdown on click outside', async () => {
    renderIndicator();

    fireEvent.click(screen.getByRole('button', { name: /wallet/i }));
    expect(screen.getByText('Tempo · pathUSD')).toBeInTheDocument();

    fireEvent.mouseDown(document.body);

    await waitFor(() => {
      expect(screen.queryByText('Tempo · pathUSD')).not.toBeInTheDocument();
    });
  });
});
