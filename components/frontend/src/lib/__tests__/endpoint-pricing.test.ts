import { describe, expect, it } from 'vitest';

import {
  DEFAULT_TRANSACTION_CHAIN_ID,
  formatPricingBadge,
  getPricing,
  PATHUSD_ADDRESS
} from '../endpoint-utils';

describe('getPricing', () => {
  it('returns null when endpoint has no policies field', () => {
    expect(getPricing({})).toBeNull();
  });

  it('returns null when policies array is empty', () => {
    expect(getPricing({ policies: [] })).toBeNull();
  });

  it('returns null when only non-transaction policies are present', () => {
    expect(
      getPricing({
        policies: [
          { type: 'access', config: { foo: 'bar' } },
          { type: 'rate-limit', config: { rps: 5 } }
        ]
      })
    ).toBeNull();
  });

  it('returns null when transaction policy is explicitly disabled', () => {
    expect(
      getPricing({
        policies: [
          {
            type: 'transaction',
            enabled: false,
            config: {
              amount: '0.10',
              currency: PATHUSD_ADDRESS,
              recipient: '0xBEEF000000000000000000000000000000000000'
            }
          }
        ]
      })
    ).toBeNull();
  });

  it('returns pricing for a charge-intent transaction policy', () => {
    const result = getPricing({
      policies: [
        { type: 'access', config: {} },
        {
          type: 'transaction',
          config: {
            amount: '0.10',
            currency: PATHUSD_ADDRESS,
            recipient: '0xBEEF000000000000000000000000000000000000',
            intent: 'charge',
            chain_id: 12_345
          }
        }
      ]
    });
    expect(result).toEqual({
      amount: '0.10',
      currency: PATHUSD_ADDRESS,
      recipient: '0xBEEF000000000000000000000000000000000000',
      intent: 'charge',
      chainID: 12_345
    });
  });

  it('coerces unknown intent values to "charge"', () => {
    const result = getPricing({
      policies: [
        {
          type: 'transaction',
          config: {
            amount: '1',
            currency: PATHUSD_ADDRESS,
            recipient: '0xBEEF000000000000000000000000000000000000',
            intent: 'something-else'
          }
        }
      ]
    });
    expect(result?.intent).toBe('charge');
  });

  it('preserves session intent', () => {
    const result = getPricing({
      policies: [
        {
          type: 'transaction',
          config: {
            amount: '5',
            currency: PATHUSD_ADDRESS,
            recipient: '0xBEEF000000000000000000000000000000000000',
            intent: 'session'
          }
        }
      ]
    });
    expect(result?.intent).toBe('session');
  });

  it('falls back to default chain id when chain_id is missing', () => {
    const result = getPricing({
      policies: [
        {
          type: 'transaction',
          config: {
            amount: '0.05',
            currency: PATHUSD_ADDRESS,
            recipient: '0xBEEF000000000000000000000000000000000000'
          }
        }
      ]
    });
    expect(result?.chainID).toBe(DEFAULT_TRANSACTION_CHAIN_ID);
  });

  it('returns the first transaction policy when multiple are present', () => {
    const result = getPricing({
      policies: [
        {
          type: 'transaction',
          config: { amount: '1', currency: PATHUSD_ADDRESS, recipient: '0xAAA' }
        },
        {
          type: 'transaction',
          config: { amount: '2', currency: PATHUSD_ADDRESS, recipient: '0xBBB' }
        }
      ]
    });
    expect(result?.amount).toBe('1');
  });
});

describe('formatPricingBadge', () => {
  it('returns dollar-prefixed amount for PathUSD currency', () => {
    expect(
      formatPricingBadge({
        amount: '0.10',
        currency: PATHUSD_ADDRESS,
        recipient: '0xBEEF000000000000000000000000000000000000',
        intent: 'charge',
        chainID: DEFAULT_TRANSACTION_CHAIN_ID
      })
    ).toBe('$0.10');
  });

  it('matches PathUSD case-insensitively', () => {
    expect(
      formatPricingBadge({
        amount: '0.42',
        currency: PATHUSD_ADDRESS.toUpperCase(),
        recipient: '0xBEEF000000000000000000000000000000000000',
        intent: 'charge',
        chainID: DEFAULT_TRANSACTION_CHAIN_ID
      })
    ).toBe('$0.42');
  });

  it('returns truncated currency for non-PathUSD addresses', () => {
    expect(
      formatPricingBadge({
        amount: '1.5',
        currency: '0xABCDEF1234567890ABCDEF1234567890ABCDEF12',
        recipient: '0xBEEF000000000000000000000000000000000000',
        intent: 'charge',
        chainID: DEFAULT_TRANSACTION_CHAIN_ID
      })
    ).toBe('1.5 0xABCD…');
  });
});
