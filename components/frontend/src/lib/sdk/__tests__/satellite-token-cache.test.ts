// @vitest-environment node
/**
 * Satellite tokens are reused while they have enough life left, and never
 * across a change of signed-in identity.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SyftHubClient } from '../client';
import { MIN_REMAINING_SECONDS, SatelliteTokenCache } from '../resources/satellite-token-cache';

const LIFETIME = 60;

describe('SatelliteTokenCache', () => {
  let nowMs: number;
  let minted: number;
  let cache: SatelliteTokenCache;

  const mint = async () => ({ targetToken: `token-${String(++minted)}`, expiresIn: LIFETIME });
  const noLifetime = async () => ({ targetToken: `token-${String(++minted)}` });
  const advance = (seconds: number) => {
    nowMs += seconds * 1000;
  };

  beforeEach(() => {
    nowMs = 1_000_000;
    minted = 0;
    cache = new SatelliteTokenCache(() => nowMs);
  });

  it('reuses a token that has enough life left', async () => {
    await cache.get('a', mint);
    advance(LIFETIME - MIN_REMAINING_SECONDS);

    const again = await cache.get('a', mint);

    expect(again.targetToken).toBe('token-1');
    expect(minted).toBe(1);
  });

  it('reports the time left on a reused token, not its lifetime', async () => {
    await cache.get('a', mint);
    advance(15);

    const result = await cache.get('a', mint);

    expect(result.expiresIn).toBe(LIFETIME - 15);
  });

  it('mints again once less than the margin is left', async () => {
    await cache.get('a', mint);
    advance(LIFETIME - MIN_REMAINING_SECONDS + 1);

    const result = await cache.get('a', mint);

    expect(result.targetToken).toBe('token-2');
  });

  it('keeps tokens for different keys apart', async () => {
    const a = await cache.get('a', mint);
    const b = await cache.get('b', mint);

    expect(a.targetToken).not.toBe(b.targetToken);
  });

  it('shares one mint between concurrent callers', async () => {
    const [first, second] = await Promise.all([cache.get('a', mint), cache.get('a', mint)]);

    expect(first.targetToken).toBe(second.targetToken);
    expect(minted).toBe(1);
  });

  it('does not remember a failed mint', async () => {
    await expect(cache.get('a', () => Promise.reject(new Error('hub down')))).rejects.toThrow();

    const result = await cache.get('a', mint);

    expect(result.targetToken).toBe('token-1');
  });

  it('does not reuse a token that came without a lifetime', async () => {
    await cache.get('a', noLifetime);

    const result = await cache.get('a', noLifetime);

    expect(result.targetToken).toBe('token-2');
  });

  it('mints again after clear', async () => {
    await cache.get('a', mint);
    cache.clear();

    const result = await cache.get('a', mint);

    expect(result.targetToken).toBe('token-2');
  });

  it('does not put back a token whose mint finished after clear', async () => {
    type Token = { targetToken: string; expiresIn: number };
    let finish!: (token: Token) => void;
    const slow = cache.get('a', () => new Promise<Token>((resolve) => (finish = resolve)));
    cache.clear();
    finish({ targetToken: 'old-identity', expiresIn: LIFETIME });
    await slow;

    const result = await cache.get('a', mint);

    expect(result.targetToken).toBe('token-1');
  });
});

describe('AuthResource satellite tokens', () => {
  const mockFetch = vi.fn();
  let client: SyftHubClient;
  let mints: string[];

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    mints = [];
    mockFetch.mockReset();
    mockFetch.mockImplementation(async (url: string) => {
      mints.push(new URL(url).pathname);
      return new Response(
        JSON.stringify({ target_token: `token-${String(mints.length)}`, expires_in: LIFETIME }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    });
    client = new SyftHubClient({ baseUrl: 'https://hub.test' });
    client.setTokens({ accessToken: 'alice', refreshToken: 'r', tokenType: 'bearer' });
  });

  const HOST = 'https://space.test';

  it('mints once for repeated requests to one host', async () => {
    const first = await client.auth.getSatelliteToken('owner', HOST);
    const second = await client.auth.getSatelliteToken('owner', HOST);

    expect(second.targetToken).toBe(first.targetToken);
    expect(mints).toEqual(['/api/v1/token']);
  });

  it('never hands a guest token to a signed-in request', async () => {
    const guest = await client.auth.getGuestSatelliteToken('owner', HOST);
    const user = await client.auth.getSatelliteToken('owner', HOST);

    expect(user.targetToken).not.toBe(guest.targetToken);
    expect(mints).toEqual(['/api/v1/token/guest', '/api/v1/token']);
  });

  it('mints again after another user signs in', async () => {
    const alice = await client.auth.getSatelliteToken('owner', HOST);
    client.setTokens({ accessToken: 'bob', refreshToken: 'r', tokenType: 'bearer' });

    const bob = await client.auth.getSatelliteToken('owner', HOST);

    expect(bob.targetToken).not.toBe(alice.targetToken);
  });

  it('mints again after logout', async () => {
    const before = await client.auth.getGuestSatelliteToken('owner', HOST);
    await client.auth.logout();

    const after = await client.auth.getGuestSatelliteToken('owner', HOST);

    expect(after.targetToken).not.toBe(before.targetToken);
    expect(mints.filter((path) => path === '/api/v1/token/guest')).toHaveLength(2);
  });
});
