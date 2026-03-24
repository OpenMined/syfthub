import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AllProviders } from '@/test/render-with-providers';

import { useXenditPurchase } from '../use-xendit-purchase';

// Hoist mocks
const { mockGetSatelliteToken } = vi.hoisted(() => ({
  mockGetSatelliteToken: vi.fn().mockResolvedValue({ targetToken: 'sat-token-123' })
}));

vi.mock('@/lib/sdk-client', async () => {
  const mock = await import('@/test/mocks/sdk-client');
  return {
    ...mock,
    syftClient: {
      ...mock.syftClient,
      auth: {
        ...mock.syftClient.auth,
        getSatelliteToken: mockGetSatelliteToken
      }
    }
  };
});

describe('useXenditPurchase', () => {
  const spaceBaseUrl = 'https://space.example.com';
  const ownerUsername = 'alice';
  const endpointSlug = 'my-model';
  const paymentApi = {
    create_invoice: '/api/v1/invoices',
    get_balance: '/api/v1/balance'
  };

  let mockPopup: {
    location: { href: string };
    closed: boolean;
    close: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockGetSatelliteToken.mockResolvedValue({ targetToken: 'sat-token-123' });

    mockPopup = {
      location: { href: '' },
      closed: false,
      close: vi.fn()
    };

    vi.stubGlobal('open', vi.fn().mockReturnValue(mockPopup));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('returns initial state correctly', () => {
    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.purchase).toBe('function');
    expect(typeof result.current.clearError).toBe('function');
  });

  it('returns error when spaceBaseUrl is undefined', async () => {
    vi.useRealTimers();
    const { result } = renderHook(
      () => useXenditPurchase(undefined, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Purchase is not available for this endpoint.');
    });
  });

  it('returns error when ownerUsername is undefined', async () => {
    vi.useRealTimers();
    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, undefined, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Purchase is not available for this endpoint.');
    });
  });

  it('returns error when endpointSlug is undefined', async () => {
    vi.useRealTimers();
    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, undefined, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Purchase is not available for this endpoint.');
    });
  });

  it('returns error when paymentApi is undefined', async () => {
    vi.useRealTimers();
    const { result } = renderHook(
      // eslint-disable-next-line unicorn/no-useless-undefined -- paymentApi is required
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, undefined),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Purchase is not available for this endpoint.');
    });
  });

  it('pre-opens popup synchronously before async fetch', async () => {
    // Set up fetch to never resolve — we just want to check popup was opened before fetch
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValue(
        new Promise<never>(() => {
          /* intentionally pending */
        })
      )
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    // Trigger the mutation without awaiting
    act(() => {
      void result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    // Allow the microtask for getSatelliteToken to resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Popup should have been opened (window.open called)
    expect(window.open).toHaveBeenCalledWith(
      'about:blank',
      'xendit-checkout',
      expect.stringContaining('width=500')
    );
  });

  it('calls create_invoice API with correct payload', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: 'inv-123',
        checkout_url: 'https://checkout.xendit.co/inv-123',
        status: 'PENDING'
      })
    });
    vi.stubGlobal('fetch', mockFetch);

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter');
    });

    expect(mockFetch).toHaveBeenCalledWith(
      `${spaceBaseUrl}${paymentApi.create_invoice}`,
      expect.objectContaining({
        method: 'POST',
        headers: {
          Authorization: 'Bearer sat-token-123',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          endpoint_slug: endpointSlug,
          tier_name: 'Starter'
        })
      })
    );
  });

  it('navigates popup to checkout URL after successful API call', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'inv-123',
          checkout_url: 'https://checkout.xendit.co/inv-123',
          status: 'PENDING'
        })
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter');
    });

    expect(mockPopup.location.href).toBe('https://checkout.xendit.co/inv-123');
  });

  it('calls onPopupClosed when popup is closed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'inv-123',
          checkout_url: 'https://checkout.xendit.co/inv-123',
          status: 'PENDING'
        })
      })
    );

    const onPopupClosed = vi.fn();
    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi, onPopupClosed),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter');
    });

    // Simulate popup closing
    mockPopup.closed = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(onPopupClosed).toHaveBeenCalledTimes(1);
  });

  it('clears previous poll timer before starting a new one', async () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'inv-123',
          checkout_url: 'https://checkout.xendit.co/inv-123',
          status: 'PENDING'
        })
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    // First purchase
    await act(async () => {
      await result.current.purchase('Starter');
    });

    const clearIntervalCallsBefore = clearIntervalSpy.mock.calls.length;

    // Reset popup for second purchase
    mockPopup.location.href = '';
    mockPopup.closed = false;
    (window.open as ReturnType<typeof vi.fn>).mockReturnValue(mockPopup);

    // Second purchase — should clear the timer from the first
    await act(async () => {
      await result.current.purchase('Pro');
    });

    // clearInterval should have been called at least once more for the existing timer
    expect(clearIntervalSpy.mock.calls.length).toBeGreaterThan(clearIntervalCallsBefore);

    clearIntervalSpy.mockRestore();
  });

  it('handles API error with detail message', async () => {
    vi.useRealTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Invalid tier name' })
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('InvalidTier').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Invalid tier name');
    });
  });

  it('handles API error without detail (fallback message)', async () => {
    vi.useRealTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        }
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('Failed to create invoice (500)');
    });
  });

  it('handles missing checkout URL in response', async () => {
    vi.useRealTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 'inv-123',
          checkout_url: '',
          status: 'PENDING'
        })
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('No checkout URL returned from payment service.');
    });
  });

  it('closes popup on failure', async () => {
    vi.useRealTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        }
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });
    expect(mockPopup.close).toHaveBeenCalled();
  });

  it('clearError resets error state', async () => {
    vi.useRealTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        }
      })
    );

    const { result } = renderHook(
      () => useXenditPurchase(spaceBaseUrl, ownerUsername, endpointSlug, paymentApi),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.purchase('Starter').catch(() => {
        /* expected */
      });
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    act(() => {
      result.current.clearError();
    });

    await waitFor(() => {
      expect(result.current.error).toBeNull();
    });
  });
});
