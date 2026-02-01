import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SettingsModal } from '@/components/settings/settings-modal';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

// Mock settings modal context with controllable return values
const { mockUseSettingsModal } = vi.hoisted(() => ({
  mockUseSettingsModal: vi.fn()
}));

vi.mock('@/context/settings-modal-context', () => ({
  useSettingsModal: (): unknown => mockUseSettingsModal()
}));

// Mock all tab sub-components as simple stubs
vi.mock('@/components/settings/profile-settings-tab', () => ({
  ProfileSettingsTab: () => <div data-testid='profile-tab'>Profile Content</div>
}));

vi.mock('@/components/settings/security-settings-tab', () => ({
  SecuritySettingsTab: () => <div data-testid='security-tab'>Security Content</div>
}));

vi.mock('@/components/settings/payment-settings-tab', () => ({
  PaymentSettingsTab: () => <div data-testid='payment-tab'>Payment Content</div>
}));

vi.mock('@/components/settings/aggregator-settings-tab', () => ({
  AggregatorSettingsTab: () => <div data-testid='aggregator-tab'>Aggregator Content</div>
}));

vi.mock('@/components/settings/danger-zone-tab', () => ({
  DangerZoneTab: () => <div data-testid='danger-tab'>Danger Zone Content</div>
}));

describe('SettingsModal', () => {
  let mockCloseSettings: ReturnType<typeof vi.fn>;
  let mockSetActiveTab: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockCloseSettings = vi.fn();
    mockSetActiveTab = vi.fn();
    // Reset body overflow
    document.body.style.overflow = 'unset';

    mockUseSettingsModal.mockReturnValue({
      isOpen: true,
      closeSettings: mockCloseSettings,
      activeTab: 'profile',
      setActiveTab: mockSetActiveTab
    });
  });

  it('renders when open', () => {
    render(<SettingsModal />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    mockUseSettingsModal.mockReturnValue({
      isOpen: false,
      closeSettings: mockCloseSettings,
      activeTab: 'profile',
      setActiveTab: mockSetActiveTab
    });

    render(<SettingsModal />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows all 5 tab buttons', () => {
    render(<SettingsModal />);

    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Payment')).toBeInTheDocument();
    expect(screen.getByText('Aggregator')).toBeInTheDocument();
    expect(screen.getByText('Danger Zone')).toBeInTheDocument();
  });

  it('shows profile tab content by default', () => {
    render(<SettingsModal />);
    expect(screen.getByTestId('profile-tab')).toBeInTheDocument();
    expect(screen.getByText('Profile Content')).toBeInTheDocument();
  });

  it('switches tab content when tab is clicked', async () => {
    mockUseSettingsModal.mockReturnValue({
      isOpen: true,
      closeSettings: mockCloseSettings,
      activeTab: 'security',
      setActiveTab: mockSetActiveTab
    });

    render(<SettingsModal />);
    expect(screen.getByTestId('security-tab')).toBeInTheDocument();
    expect(screen.getByText('Security Content')).toBeInTheDocument();
  });

  it('calls setActiveTab when a tab button is clicked', async () => {
    const user = userEvent.setup();
    render(<SettingsModal />);

    await user.click(screen.getByText('Security'));
    expect(mockSetActiveTab).toHaveBeenCalledWith('security');
  });

  it('calls closeSettings when close button is clicked', async () => {
    const user = userEvent.setup();
    render(<SettingsModal />);

    await user.click(screen.getByRole('button', { name: /close settings/i }));
    expect(mockCloseSettings).toHaveBeenCalled();
  });

  it('calls closeSettings on Escape key', async () => {
    render(<SettingsModal />);

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => {
      expect(mockCloseSettings).toHaveBeenCalled();
    });
  });

  it('calls closeSettings when clicking the overlay', async () => {
    const user = userEvent.setup();
    render(<SettingsModal />);

    // The overlay is the motion.div backdrop - click the outer fixed div
    const backdrop = screen.getByRole('dialog').parentElement;
    expect(backdrop).not.toBeNull();
    // The backdrop's sibling div has the click handler
    const overlay = backdrop?.querySelector('.absolute.inset-0');
    if (overlay) {
      await user.click(overlay);
    }

    expect(mockCloseSettings).toHaveBeenCalled();
  });

  it('sets body overflow to hidden when open', () => {
    render(<SettingsModal />);
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('restores body overflow when closed', () => {
    const { rerender } = render(<SettingsModal />);
    expect(document.body.style.overflow).toBe('hidden');

    mockUseSettingsModal.mockReturnValue({
      isOpen: false,
      closeSettings: mockCloseSettings,
      activeTab: 'profile',
      setActiveTab: mockSetActiveTab
    });

    rerender(<SettingsModal />);
    expect(document.body.style.overflow).toBe('unset');
  });

  it('renders correct tab for each active tab value', () => {
    const tabCases: Array<{ tab: string; testId: string; content: string }> = [
      { tab: 'payment', testId: 'payment-tab', content: 'Payment Content' },
      { tab: 'aggregator', testId: 'aggregator-tab', content: 'Aggregator Content' },
      { tab: 'danger-zone', testId: 'danger-tab', content: 'Danger Zone Content' }
    ];

    for (const { tab, testId, content } of tabCases) {
      mockUseSettingsModal.mockReturnValue({
        isOpen: true,
        closeSettings: mockCloseSettings,
        activeTab: tab,
        setActiveTab: mockSetActiveTab
      });

      const { unmount } = render(<SettingsModal />);
      expect(screen.getByTestId(testId)).toBeInTheDocument();
      expect(screen.getByText(content)).toBeInTheDocument();
      unmount();
    }
  });
});
