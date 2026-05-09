/**
 * Tests for PaymentRequiredModal — batched on-chain payment approval UI.
 *
 * Mocks the Tempo wallet (`useTempoWallet`) and the per-challenge submit
 * fetch so the component logic is exercised without network/wallet I/O.
 */
import type { PaymentChallenge } from '@/hooks/use-chat-workflow';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PaymentRequiredModal } from '@/components/payment-required-modal';

// =============================================================================
// Mocks
// =============================================================================

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

const { mockUseWalletForPayments, mockUnlockWallet, mockSignCredential } = vi.hoisted(() => ({
  mockUseWalletForPayments: vi.fn(),
  mockUnlockWallet: vi.fn(),
  mockSignCredential: vi.fn()
}));

vi.mock('@/lib/payment-stubs', () => ({
  useWalletForPayments: (): unknown => mockUseWalletForPayments(),
  // `parseChallenge` is real but our test challenge strings aren't valid MPP
  // challenges. Stub it to return a deterministic ParsedChallenge so the
  // modal logic can run end-to-end without depending on parser internals.
  parseChallenge: (raw: string): unknown => ({
    id: `parsed-${raw}`,
    realm: 'test',
    method: 'tempo',
    intent: 'charge',
    request: 'cmVxdWVzdA',
    expires: '2099-01-01T00:00:00Z',
    amount: '0.10',
    currency: '0x1111111111111111111111111111111111111111',
    recipient: '0x2222222222222222222222222222222222222222'
  })
}));

vi.mock('@/lib/sdk-client', () => ({
  syftClient: {
    getTokens: vi.fn().mockReturnValue({ accessToken: 'test-token' })
  }
}));

// =============================================================================
// Fixtures
// =============================================================================

function makeChallenge(overrides: Partial<PaymentChallenge> = {}): PaymentChallenge {
  return {
    chatSessionId: 'session-1',
    endpointSlug: 'demo-model',
    challenge: 'Payment id="abc"',
    amount: '0.10',
    currency: '0x1111111111111111111111111111111111111111',
    recipient: '0x2222222222222222222222222222222222222222',
    challengeId: 'chal-1',
    intent: 'charge',
    ...overrides
  };
}

// =============================================================================
// Tests
// =============================================================================

describe('PaymentRequiredModal', () => {
  let onApproved: ReturnType<typeof vi.fn>;
  let onCanceled: ReturnType<typeof vi.fn>;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    globalThis.localStorage.clear();
    onApproved = vi.fn();
    onCanceled = vi.fn();

    // The real unlockWallet returns Promise<void>; vitest infers the type
    // from the resolved value, so we settle with a sentinel and ignore.
    mockUnlockWallet.mockResolvedValue(null);
    mockSignCredential.mockResolvedValue({
      credential: 'Payment eyJtb2NrIjoidHJ1ZSJ9',
      txHash: '0xabcdef0123456789'
    });
    mockUseWalletForPayments.mockReturnValue({
      address: '0x1234567890abcdef1234567890abcdef12345678',
      hasWallet: true,
      isUnlocked: false,
      unlockWallet: mockUnlockWallet,
      signCredential: mockSignCredential
    });

    fetchSpy = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, text: () => Promise.resolve('') });
    globalThis.fetch = fetchSpy as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderModal(challenges: PaymentChallenge[]) {
    return render(
      <PaymentRequiredModal
        challenges={challenges}
        aggregatorURL='https://agg.example.com'
        rpcURL='https://rpc.example.com'
        chainID={42_431}
        onApproved={
          onApproved as unknown as (results: Array<{ challengeID: string; txHash: string }>) => void
        }
        onCanceled={onCanceled as unknown as () => void}
      />
    );
  }

  it('renders one challenge with amount and truncated recipient', () => {
    renderModal([makeChallenge()]);
    expect(screen.getByText('Payment required')).toBeInTheDocument();
    expect(screen.getByText('demo-model')).toBeInTheDocument();
    expect(screen.getByText(/0\.10/)).toBeInTheDocument();
    expect(screen.getByText(/0x2222…2222/)).toBeInTheDocument();
  });

  it('shows total = sum of amounts across multiple challenges', () => {
    const challenges = [
      makeChallenge({ challengeId: 'a', amount: '0.10', endpointSlug: 'one' }),
      makeChallenge({ challengeId: 'b', amount: '0.25', endpointSlug: 'two' }),
      makeChallenge({ challengeId: 'c', amount: '1.50', endpointSlug: 'three' })
    ];
    renderModal(challenges);
    // 0.10 + 0.25 + 1.50 = 1.85
    expect(screen.getByText(/1\.85/)).toBeInTheDocument();
    expect(screen.getByText(/across 3 endpoints/)).toBeInTheDocument();
  });

  it('approves all challenges: calls fetch per challenge and invokes onApproved', async () => {
    const user = userEvent.setup();
    const challenges = [
      makeChallenge({ challengeId: 'a', endpointSlug: 'one' }),
      makeChallenge({ challengeId: 'b', endpointSlug: 'two' })
    ];
    renderModal(challenges);

    const passphraseInput = screen.getByLabelText(/passphrase/i);
    fireEvent.change(passphraseInput, { target: { value: 'secret' } });
    await user.click(screen.getByRole('button', { name: /approve all/i }));

    await waitFor(() => {
      expect(onApproved).toHaveBeenCalledTimes(1);
    });

    expect(mockUnlockWallet).toHaveBeenCalledWith('secret');
    expect(mockSignCredential).toHaveBeenCalledTimes(2);
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    // Check fetch URL + body shape per challenge
    const calls = fetchSpy.mock.calls;
    const urls = calls.map((c) => String(c[0])).toSorted((a, b) => a.localeCompare(b));
    expect(urls).toEqual([
      'https://agg.example.com/chat/session-1/payment',
      'https://agg.example.com/chat/session-1/payment'
    ]);
    const bodies = calls
      .map((c) => {
        const body = (c[1] as RequestInit).body;
        return JSON.parse(typeof body === 'string' ? body : '') as Record<string, unknown>;
      })
      .map((b) => String(b.challenge_id))
      .toSorted((a, b) => a.localeCompare(b));
    expect(bodies).toEqual(['a', 'b']);

    // onApproved received both tx hashes
    const result = onApproved.mock.calls[0]?.[0] as Array<{ challengeID: string; txHash: string }>;
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.challengeID).toSorted((a, b) => a.localeCompare(b))).toEqual([
      'a',
      'b'
    ]);

    // Persisted to localStorage
    const history = JSON.parse(
      globalThis.localStorage.getItem('syft_payment_history_v1') ?? '[]'
    ) as Array<{ tx_hash: string; status: string }>;
    expect(history).toHaveLength(2);
    expect(history[0]?.status).toBe('verified');
  });

  it('shows per-challenge error and Retry button when one signing fails', async () => {
    const user = userEvent.setup();
    mockSignCredential.mockImplementation(async (parsed: { id: string }) => {
      if (parsed.id === 'parsed-Payment id="bad"') {
        throw new Error('insufficient funds');
      }
      return {
        credential: 'Payment ok',
        txHash: '0xabc'
      };
    });

    const challenges = [
      makeChallenge({ challengeId: 'good', challenge: 'Payment id="good"' }),
      makeChallenge({ challengeId: 'bad', challenge: 'Payment id="bad"' })
    ];
    renderModal(challenges);

    const passphraseInput = screen.getByLabelText(/passphrase/i);
    fireEvent.change(passphraseInput, { target: { value: 'secret' } });
    await user.click(screen.getByRole('button', { name: /approve all/i }));

    await waitFor(() => {
      expect(screen.getByText(/Sign failed: insufficient funds/i)).toBeInTheDocument();
    });

    expect(onApproved).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /retry failed/i })).toBeInTheDocument();
  });

  it('cancel calls onCanceled', async () => {
    const user = userEvent.setup();
    renderModal([makeChallenge()]);
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCanceled).toHaveBeenCalledTimes(1);
  });

  it('shows "Create a wallet first" when no wallet exists', () => {
    mockUseWalletForPayments.mockReturnValue({
      address: null,
      hasWallet: false,
      isUnlocked: false,
      unlockWallet: mockUnlockWallet,
      signCredential: mockSignCredential
    });
    renderModal([makeChallenge()]);
    expect(screen.getByText(/Create a wallet first/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve all/i })).toBeDisabled();
  });
});
