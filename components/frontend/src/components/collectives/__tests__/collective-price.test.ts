import { describe, expect, it } from 'vitest';

import { formatEstimatedPrice, formatPriceSlice } from '../collective-price';

describe('formatPriceSlice', () => {
  it('formats an amount with its currency code as a suffix', () => {
    expect(formatPriceSlice({ currency: 'IDR', amount: 10_000 })).toBe('10,000 IDR');
    expect(formatPriceSlice({ currency: 'USD', amount: 10 })).toBe('10 USD');
  });

  it('caps fractional digits at two', () => {
    expect(formatPriceSlice({ currency: 'USD', amount: 0.6543 })).toBe('0.65 USD');
  });
});

describe('formatEstimatedPrice', () => {
  it('joins per-currency slices with a plus (no FX conversion)', () => {
    expect(
      formatEstimatedPrice([
        { currency: 'IDR', amount: 10_000 },
        { currency: 'EUR', amount: 10 }
      ])
    ).toBe('10,000 IDR + 10 EUR');
  });

  it('returns an empty string for no slices', () => {
    expect(formatEstimatedPrice([])).toBe('');
  });
});
