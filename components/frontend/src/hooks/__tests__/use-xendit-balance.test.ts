import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AllProviders } from '@/test/render-with-providers';

import { useXenditBalance } from '../use-xendit-balance';

// Mock the SDK client module
vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

// Hoist the mock so vi.mock can reference it
const { mockGetSatelliteToken } = vi.hoisted(() => ({
  mockGetSatelliteToken: vi.fn().mockResolvedValue({ targetToken: 'sat-token-123' })
}));

// Patch the mock SDK client's auth to include getSatelliteToken
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

describe('useXenditBalance', () => {
  const spaceBaseUrl = 'https://space.example.com';
  const ownerUsername = 'alice';
  const balancePath = '/api/v1/balance';

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSatelliteToken.mockResolvedValue({ targetToken: 'sat-token-123' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns null values and loading=false when params are undefined', () => {
    // eslint-disable-next-line unicorn/no-useless-undefined -- testing explicit undefined input
    const { result } = renderHook(() => useXenditBalance(undefined, undefined, undefined), {
      wrapper: AllProviders
    });

    // Query is disabled so it should not be loading
    expect(result.current.remaining).toBeNull();
    expect(result.current.total).toBeNull();
    expect(result.current.unitType).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('is disabled when spaceBaseUrl is undefined', () => {
    const { result } = renderHook(() => useXenditBalance(undefined, ownerUsername, balancePath), {
      wrapper: AllProviders
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.remaining).toBeNull();
  });

  it('is disabled when ownerUsername is undefined', () => {
    const { result } = renderHook(() => useXenditBalance(spaceBaseUrl, undefined, balancePath), {
      wrapper: AllProviders
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.remaining).toBeNull();
  });

  it('is disabled when balancePath is undefined', () => {
    // eslint-disable-next-line unicorn/no-useless-undefined -- testing explicit undefined input
    const { result } = renderHook(() => useXenditBalance(spaceBaseUrl, ownerUsername, undefined), {
      wrapper: AllProviders
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.remaining).toBeNull();
  });

  it('fetches and returns balance data on mount', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          remaining_units: 75,
          total_purchased: 100,
          unit_type: 'requests'
        })
      })
    );

    const { result } = renderHook(
      () => useXenditBalance(spaceBaseUrl, ownerUsername, balancePath),
      { wrapper: AllProviders }
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.remaining).toBe(75);
    expect(result.current.total).toBe(100);
    expect(result.current.unitType).toBe('requests');
    expect(result.current.error).toBeNull();
  });

  it('handles 404 (no purchases yet) by returning zero balance', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Not found' })
      })
    );

    const { result } = renderHook(
      () => useXenditBalance(spaceBaseUrl, ownerUsername, balancePath),
      { wrapper: AllProviders }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.remaining).toBe(0);
    expect(result.current.total).toBe(0);
    expect(result.current.unitType).toBe('requests');
    expect(result.current.error).toBeNull();
  });

  it('handles fetch errors gracefully', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' })
      })
    );

    const { result } = renderHook(
      () => useXenditBalance(spaceBaseUrl, ownerUsername, balancePath),
      { wrapper: AllProviders }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.remaining).toBeNull();
    expect(result.current.total).toBeNull();
    expect(result.current.error).toBe('Failed to fetch balance (500)');
  });

  it('calls fetch with correct URL and authorization header', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        remaining_units: 50,
        total_purchased: 200,
        unit_type: 'requests'
      })
    });
    vi.stubGlobal('fetch', mockFetch);

    const { result } = renderHook(
      () => useXenditBalance(spaceBaseUrl, ownerUsername, balancePath),
      { wrapper: AllProviders }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      `${spaceBaseUrl}${balancePath}?unit_type=requests`,
      expect.objectContaining({
        headers: {
          Authorization: 'Bearer sat-token-123'
        }
      })
    );
  });

  it('refetch works after initial load', async () => {
    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        callCount++;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            remaining_units: callCount === 1 ? 75 : 50,
            total_purchased: 100,
            unit_type: 'requests'
          })
        };
      })
    );

    const { result } = renderHook(
      () => useXenditBalance(spaceBaseUrl, ownerUsername, balancePath),
      { wrapper: AllProviders }
    );

    await waitFor(() => {
      expect(result.current.remaining).toBe(75);
    });

    // Trigger refetch
    await result.current.refetch();

    await waitFor(() => {
      expect(result.current.remaining).toBe(50);
    });
  });
});
