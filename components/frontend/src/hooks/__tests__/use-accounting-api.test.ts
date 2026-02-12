import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { parseTransaction, POLLING_INTERVAL_MS } from '../use-accounting-api';

// ============================================================================
// parseTransaction (pure function - no hooks needed)
// ============================================================================

describe('parseTransaction', () => {
  it('converts snake_case to camelCase', () => {
    const response = {
      id: 'tx-1',
      sender_email: 'sender@test.com',
      recipient_email: 'recipient@test.com',
      amount: 50,
      status: 'completed' as const,
      created_by: 'sender' as const,
      resolved_by: 'recipient' as const,
      created_at: '2024-01-15T10:00:00.000Z',
      resolved_at: '2024-01-15T10:05:00.000Z',
      app_name: 'TestApp',
      app_ep_path: 'alice/model'
    };

    const result = parseTransaction(response);
    expect(result.id).toBe('tx-1');
    expect(result.senderEmail).toBe('sender@test.com');
    expect(result.recipientEmail).toBe('recipient@test.com');
    expect(result.amount).toBe(50);
    expect(result.status).toBe('completed');
    expect(result.createdBy).toBe('sender');
    expect(result.resolvedBy).toBe('recipient');
    expect(result.createdAt).toBeInstanceOf(Date);
    expect(result.resolvedAt).toBeInstanceOf(Date);
    expect(result.appName).toBe('TestApp');
    expect(result.appEpPath).toBe('alice/model');
  });

  it('handles null resolved_by and resolved_at', () => {
    const response = {
      id: 'tx-2',
      sender_email: 'sender@test.com',
      recipient_email: 'recipient@test.com',
      amount: 25,
      status: 'pending' as const,
      created_by: 'sender' as const,
      resolved_by: null,
      created_at: '2024-01-15T10:00:00.000Z',
      resolved_at: null,
      app_name: null,
      app_ep_path: null
    };

    const result = parseTransaction(response);
    expect(result.resolvedBy).toBeNull();
    expect(result.resolvedAt).toBeNull();
    expect(result.appName).toBeNull();
    expect(result.appEpPath).toBeNull();
  });

  it('normalizes uppercase status to lowercase', () => {
    const response = {
      id: 'tx-3',
      sender_email: 'a@b.com',
      recipient_email: 'c@d.com',
      amount: 10,
      status: 'PENDING' as const,
      created_by: 'SYSTEM' as const,
      resolved_by: null,
      created_at: '2024-01-15T10:00:00.000Z',
      resolved_at: null,
      app_name: null,
      app_ep_path: null
    };

    const result = parseTransaction(response);
    expect(result.status).toBe('pending');
    expect(result.createdBy).toBe('system');
  });

  it('parses date strings into Date objects', () => {
    const response = {
      id: 'tx-4',
      sender_email: 'a@b.com',
      recipient_email: 'c@d.com',
      amount: 100,
      status: 'completed' as const,
      created_by: 'sender' as const,
      resolved_by: 'recipient' as const,
      created_at: '2024-06-15T14:30:00.000Z',
      resolved_at: '2024-06-15T14:35:00.000Z',
      app_name: null,
      app_ep_path: null
    };

    const result = parseTransaction(response);
    expect(result.createdAt.getFullYear()).toBe(2024);
    expect(result.createdAt.getMonth()).toBe(5); // June is month 5 (0-indexed)
    expect(result.resolvedAt?.getFullYear()).toBe(2024);
  });
});

// ============================================================================
// POLLING_INTERVAL_MS constant
// ============================================================================

describe('POLLING_INTERVAL_MS', () => {
  it('is 30 seconds', () => {
    expect(POLLING_INTERVAL_MS).toBe(30_000);
  });
});

// ============================================================================
// Hooks (require provider context)
// ============================================================================

describe('useAccountingUser (mock integration)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'acc-1',
          email: 'test@example.com',
          balance: 500,
          organization: null
        })
      })
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('exports triggerBalanceRefresh', async () => {
    const { triggerBalanceRefresh } = await import('../use-accounting-api');
    expect(typeof triggerBalanceRefresh).toBe('function');
    // Should not throw when called without listeners
    triggerBalanceRefresh();
  });

  it('exports useBalanceRefresh', async () => {
    const { useBalanceRefresh } = await import('../use-accounting-api');
    expect(typeof useBalanceRefresh).toBe('function');
  });
});

// ============================================================================
// AccountingProxyClient (class tests)
// ============================================================================

describe('AccountingProxyClient', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'acc-1',
          email: 'test@example.com',
          balance: 500,
          organization: null
        })
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('can be instantiated', async () => {
    const { AccountingProxyClient } = await import('../use-accounting-api');
    const client = new AccountingProxyClient();
    expect(client).toBeDefined();
  });

  it('has getUser method', async () => {
    const { AccountingProxyClient } = await import('../use-accounting-api');
    const client = new AccountingProxyClient();
    expect(typeof client.getUser).toBe('function');
  });

  it('has getTransactions method', async () => {
    const { AccountingProxyClient } = await import('../use-accounting-api');
    const client = new AccountingProxyClient();
    expect(typeof client.getTransactions).toBe('function');
  });

  it('has createTransaction method', async () => {
    const { AccountingProxyClient } = await import('../use-accounting-api');
    const client = new AccountingProxyClient();
    expect(typeof client.createTransaction).toBe('function');
  });
});
