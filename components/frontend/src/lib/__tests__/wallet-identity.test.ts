/**
 * Wallet identity gating.
 *
 * Only a `cluster` policy may carry a `wallet_id` / `wallet_owner_username`
 * of its own — those claims are verified against the wallet owner's registered
 * domain at publish time. The same fields on a self-hosted policy are ignored,
 * including on rows stored before publish-time stripping existed.
 */
import { describe, expect, it } from 'vitest';

import { resolveWalletAudience, resolveWalletKey } from '@/lib/xendit-client';

const CREDITS_URL = 'https://station.example.com/api/v1/credits/018f2c3a/balance';
const ENDPOINT_OWNER = 'publisher';

// A cluster wallet as stored after successful publish-time validation.
const VERIFIED = {
  walletId: '018f2c3a-7b1e-4c2d-9a6f-3e8d5b1c4a90',
  walletOwnerUsername: 'station42'
};

describe('resolveWalletAudience', () => {
  it('honors the wallet owner on a verified cluster policy', () => {
    expect(resolveWalletAudience(VERIFIED, 'cluster', ENDPOINT_OWNER)).toBe('station42');
  });

  it('is case-insensitive about the policy type', () => {
    expect(resolveWalletAudience(VERIFIED, 'CLUSTER', ENDPOINT_OWNER)).toBe('station42');
  });

  it('ignores a wallet owner claimed by a self-hosted policy', () => {
    // Poisoned row: minting for station42 would hand that account's token to
    // whatever host this policy's unverified credits_url points at.
    expect(resolveWalletAudience(VERIFIED, 'xendit', ENDPOINT_OWNER)).toBe(ENDPOINT_OWNER);
    expect(resolveWalletAudience(VERIFIED, 'stripe', ENDPOINT_OWNER)).toBe(ENDPOINT_OWNER);
  });

  it('falls back to the endpoint owner when a cluster policy names nobody', () => {
    expect(resolveWalletAudience({ walletOwnerUsername: null }, 'cluster', ENDPOINT_OWNER)).toBe(
      ENDPOINT_OWNER
    );
  });
});

describe('resolveWalletKey', () => {
  it('groups a verified cluster policy by its wallet id', () => {
    expect(resolveWalletKey(VERIFIED, 'cluster', CREDITS_URL)).toBe(VERIFIED.walletId);
  });

  it('ignores a wallet id claimed by a self-hosted policy', () => {
    // Otherwise the row joins a wallet it does not own: its balance would
    // stand in for the real one and mark those endpoints funded.
    expect(resolveWalletKey(VERIFIED, 'xendit', CREDITS_URL)).toBe(CREDITS_URL);
  });

  it('falls back to credits_url when a cluster policy has no wallet id', () => {
    expect(resolveWalletKey({ walletId: null }, 'cluster', CREDITS_URL)).toBe(CREDITS_URL);
  });
});
