import type { PaymentHistoryEntry } from '../payment-history-tab';

import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { PAYMENT_HISTORY_STORAGE_KEY, PaymentHistoryTab } from '../payment-history-tab';

const ENTRY_OLD: PaymentHistoryEntry = {
  timestamp: '2026-04-01T10:00:00.000Z',
  endpoint_slug: 'alice/old',
  amount: '0.10',
  currency: '0x20c0000000000000000000000000000000000000',
  tx_hash: '0xdeadbeef0000000000000000000000000000000000000000000000000000aaaa',
  status: 'verified'
};

const ENTRY_NEW: PaymentHistoryEntry = {
  timestamp: '2026-05-01T12:00:00.000Z',
  endpoint_slug: 'bob/new',
  amount: '0.50',
  currency: '0x20c0000000000000000000000000000000000000',
  tx_hash: '0xfeed00000000000000000000000000000000000000000000000000000000bbbb',
  status: 'failed'
};

function seed(entries: PaymentHistoryEntry[]): void {
  localStorage.setItem(PAYMENT_HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

describe('PaymentHistoryTab', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders the empty state when localStorage is empty', () => {
    render(<PaymentHistoryTab />);
    expect(screen.getByTestId('payment-history-empty')).toBeInTheDocument();
    expect(screen.getByText(/No payments yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId('payment-history-table')).not.toBeInTheDocument();
  });

  it('renders the empty state when localStorage holds invalid JSON', () => {
    localStorage.setItem(PAYMENT_HISTORY_STORAGE_KEY, '{not json');
    render(<PaymentHistoryTab />);
    expect(screen.getByTestId('payment-history-empty')).toBeInTheDocument();
  });

  it('renders entries from localStorage in reverse-chronological order', () => {
    seed([ENTRY_OLD, ENTRY_NEW]);

    render(<PaymentHistoryTab />);

    const rows = screen.getAllByTestId('payment-history-row');
    expect(rows).toHaveLength(2);
    // Newer entry first
    expect(rows[0]).toHaveTextContent('bob/new');
    expect(rows[1]).toHaveTextContent('alice/old');
  });

  it('shows the correct status badges for each entry', () => {
    seed([ENTRY_OLD, ENTRY_NEW]);
    render(<PaymentHistoryTab />);
    expect(screen.getByTestId('payment-status-verified')).toBeInTheDocument();
    expect(screen.getByTestId('payment-status-failed')).toBeInTheDocument();
  });

  it('renders a transaction explorer link with the truncated tx hash', () => {
    seed([ENTRY_OLD]);
    render(<PaymentHistoryTab />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', `https://explorer.tempo.example/tx/${ENTRY_OLD.tx_hash}`);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveTextContent(`${ENTRY_OLD.tx_hash.slice(0, 10)}…`);
  });

  it('updates when a storage event fires for the payment history key', () => {
    render(<PaymentHistoryTab />);
    expect(screen.getByTestId('payment-history-empty')).toBeInTheDocument();

    const newValue = JSON.stringify([ENTRY_NEW]);
    localStorage.setItem(PAYMENT_HISTORY_STORAGE_KEY, newValue);

    act(() => {
      globalThis.dispatchEvent(
        new StorageEvent('storage', {
          key: PAYMENT_HISTORY_STORAGE_KEY,
          newValue
        })
      );
    });

    expect(screen.getByTestId('payment-history-table')).toBeInTheDocument();
    expect(screen.getByText('bob/new')).toBeInTheDocument();
  });

  it('ignores storage events for unrelated keys', () => {
    seed([ENTRY_NEW]);
    render(<PaymentHistoryTab />);
    expect(screen.getByText('bob/new')).toBeInTheDocument();

    act(() => {
      globalThis.dispatchEvent(
        new StorageEvent('storage', { key: 'something_else', newValue: '[]' })
      );
    });

    // Existing entry still rendered, untouched.
    expect(screen.getByText('bob/new')).toBeInTheDocument();
  });

  it('clears history when the clear button is clicked', async () => {
    const user = userEvent.setup();
    seed([ENTRY_OLD, ENTRY_NEW]);

    render(<PaymentHistoryTab />);
    expect(screen.getAllByTestId('payment-history-row')).toHaveLength(2);

    await user.click(screen.getByTestId('payment-history-clear'));

    expect(screen.getByTestId('payment-history-empty')).toBeInTheDocument();
    expect(localStorage.getItem(PAYMENT_HISTORY_STORAGE_KEY)).toBeNull();
  });
});
