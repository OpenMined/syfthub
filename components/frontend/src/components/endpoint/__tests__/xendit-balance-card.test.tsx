import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { XenditBalanceCard } from '../xendit-balance-card';

// Hoist the mock return value so vi.mock can reference it
const { mockUseXenditBalance } = vi.hoisted(() => ({
  mockUseXenditBalance: vi.fn()
}));

vi.mock('@/hooks/use-xendit-balance', () => ({
  useXenditBalance: (...parameters: unknown[]): unknown => mockUseXenditBalance(...parameters)
}));

describe('XenditBalanceCard', () => {
  const defaultProps = {
    spaceBaseUrl: 'https://space.example.com',
    ownerUsername: 'alice',
    balancePath: '/api/v1/balance'
  };

  let mockRefetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockRefetch = vi.fn().mockResolvedValue(null);

    // Default: loaded with balance
    mockUseXenditBalance.mockReturnValue({
      remaining: 75,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });
  });

  it('renders loading state when loading and no data', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: null,
      total: null,
      unitType: null,
      isLoading: true,
      error: null,
      refetch: mockRefetch
    });

    const { container } = render(<XenditBalanceCard {...defaultProps} />);
    // Should show spinner (Loader2 with animate-spin class)
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeTruthy();
    // Should NOT show balance text
    expect(screen.queryByText(/remaining/i)).not.toBeInTheDocument();
  });

  it('renders balance with correct numbers', () => {
    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText(/of 100/)).toBeInTheDocument();
    expect(screen.getByText('requests remaining')).toBeInTheDocument();
  });

  it('renders progress bar with correct width percentage', () => {
    const { container } = render(<XenditBalanceCard {...defaultProps} />);

    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar).toBeTruthy();
    expect(progressBar?.getAttribute('style')).toContain('width: 75%');
  });

  it('renders progress bar in teal when above 20%', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 50,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const { container } = render(<XenditBalanceCard {...defaultProps} />);

    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar?.className).toContain('bg-teal');
    expect(progressBar?.className).not.toContain('bg-red');
  });

  it('renders low balance warning when remaining is 20% or less', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 20,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText(/low balance/i)).toBeInTheDocument();
  });

  it('renders progress bar in red when low balance', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 10,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const { container } = render(<XenditBalanceCard {...defaultProps} />);

    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar?.className).toContain('bg-red');
  });

  it('does NOT show low balance warning when above 20%', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 21,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.queryByText(/low balance/i)).not.toBeInTheDocument();
  });

  it('uses unitType from hook (not hardcoded "requests")', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 50,
      total: 100,
      unitType: 'tokens',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('tokens remaining')).toBeInTheDocument();
    expect(screen.queryByText('requests remaining')).not.toBeInTheDocument();
  });

  it('falls back to "requests" when unitType is null', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 50,
      total: 100,
      unitType: null,
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('requests remaining')).toBeInTheDocument();
  });

  it('renders error state', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: null,
      total: null,
      unitType: null,
      isLoading: false,
      error: 'Failed to fetch balance (500)',
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('Failed to fetch balance (500)')).toBeInTheDocument();
    // Should not show balance or loading
    expect(screen.queryByText(/remaining/i)).not.toBeInTheDocument();
  });

  it('renders "no balance data" when no data and not loading', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: null,
      total: null,
      unitType: null,
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('No balance data available')).toBeInTheDocument();
  });

  it('renders the Credits header', () => {
    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByText('Credits')).toBeInTheDocument();
  });

  it('renders refresh button', () => {
    render(<XenditBalanceCard {...defaultProps} />);

    expect(screen.getByTitle('Refresh balance')).toBeInTheDocument();
  });

  it('disables refresh button while loading', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 75,
      total: 100,
      unitType: 'requests',
      isLoading: true,
      error: null,
      refetch: mockRefetch
    });

    render(<XenditBalanceCard {...defaultProps} />);

    const refreshButton = screen.getByTitle('Refresh balance');
    expect(refreshButton).toBeDisabled();
  });

  it('handles zero total (0% progress, no division by zero)', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 0,
      total: 0,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const { container } = render(<XenditBalanceCard {...defaultProps} />);

    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar?.getAttribute('style')).toContain('width: 0%');
    // Zero total should not trigger low balance warning (isLow requires total > 0)
    expect(screen.queryByText(/low balance/i)).not.toBeInTheDocument();
  });

  it('clamps percentage at 100% if remaining exceeds total', () => {
    mockUseXenditBalance.mockReturnValue({
      remaining: 150,
      total: 100,
      unitType: 'requests',
      isLoading: false,
      error: null,
      refetch: mockRefetch
    });

    const { container } = render(<XenditBalanceCard {...defaultProps} />);

    const progressBar = container.querySelector('[style*="width"]');
    expect(progressBar?.getAttribute('style')).toContain('width: 100%');
  });
});
