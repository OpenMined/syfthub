import { describe, expect, it } from 'vitest';

import { isValidBundleTier, isValidPaymentApi } from '../xendit-policy-content';

// ============================================================================
// isValidBundleTier
// ============================================================================

describe('isValidBundleTier', () => {
  it('accepts a valid tier object', () => {
    expect(
      isValidBundleTier({ name: 'Starter', units: 100, unit_type: 'requests', price: 9.99 })
    ).toBe(true);
  });

  it('accepts a tier with extra properties', () => {
    expect(
      isValidBundleTier({
        name: 'Pro',
        units: 500,
        unit_type: 'requests',
        price: 29.99,
        description: 'For power users'
      })
    ).toBe(true);
  });

  it('accepts a tier with zero units and price', () => {
    expect(isValidBundleTier({ name: 'Free', units: 0, unit_type: 'requests', price: 0 })).toBe(
      true
    );
  });

  it('rejects null', () => {
    expect(isValidBundleTier(null)).toBe(false);
  });

  it('rejects undefined', () => {
    // eslint-disable-next-line unicorn/no-useless-undefined -- testing explicit undefined input
    expect(isValidBundleTier(undefined)).toBe(false);
  });

  it('rejects a string', () => {
    expect(isValidBundleTier('not a tier')).toBe(false);
  });

  it('rejects a number', () => {
    expect(isValidBundleTier(42)).toBe(false);
  });

  it('rejects an empty object', () => {
    expect(isValidBundleTier({})).toBe(false);
  });

  it('rejects when name is missing', () => {
    expect(isValidBundleTier({ units: 100, unit_type: 'requests', price: 9.99 })).toBe(false);
  });

  it('rejects when units is missing', () => {
    expect(isValidBundleTier({ name: 'Starter', unit_type: 'requests', price: 9.99 })).toBe(false);
  });

  it('rejects when unit_type is missing', () => {
    expect(isValidBundleTier({ name: 'Starter', units: 100, price: 9.99 })).toBe(false);
  });

  it('rejects when price is missing', () => {
    expect(isValidBundleTier({ name: 'Starter', units: 100, unit_type: 'requests' })).toBe(false);
  });

  it('rejects when name is not a string', () => {
    expect(isValidBundleTier({ name: 123, units: 100, unit_type: 'requests', price: 9.99 })).toBe(
      false
    );
  });

  it('rejects when units is not a number', () => {
    expect(
      isValidBundleTier({ name: 'Starter', units: '100', unit_type: 'requests', price: 9.99 })
    ).toBe(false);
  });

  it('rejects when unit_type is not a string', () => {
    expect(isValidBundleTier({ name: 'Starter', units: 100, unit_type: 42, price: 9.99 })).toBe(
      false
    );
  });

  it('rejects when price is not a number', () => {
    expect(
      isValidBundleTier({ name: 'Starter', units: 100, unit_type: 'requests', price: '9.99' })
    ).toBe(false);
  });

  it('rejects an array', () => {
    expect(isValidBundleTier([1, 2, 3])).toBe(false);
  });
});

// ============================================================================
// isValidPaymentApi
// ============================================================================

describe('isValidPaymentApi', () => {
  it('accepts a valid payment API object', () => {
    expect(
      isValidPaymentApi({
        create_invoice: '/api/v1/invoices',
        get_balance: '/api/v1/balance'
      })
    ).toBe(true);
  });

  it('accepts a payment API with extra properties', () => {
    expect(
      isValidPaymentApi({
        create_invoice: '/api/v1/invoices',
        get_balance: '/api/v1/balance',
        webhook_url: '/api/v1/webhook'
      })
    ).toBe(true);
  });

  it('rejects null', () => {
    expect(isValidPaymentApi(null)).toBe(false);
  });

  it('rejects undefined', () => {
    // eslint-disable-next-line unicorn/no-useless-undefined -- testing explicit undefined input
    expect(isValidPaymentApi(undefined)).toBe(false);
  });

  it('rejects a string', () => {
    expect(isValidPaymentApi('not an api')).toBe(false);
  });

  it('rejects an empty object', () => {
    expect(isValidPaymentApi({})).toBe(false);
  });

  it('rejects when create_invoice is missing', () => {
    expect(isValidPaymentApi({ get_balance: '/api/v1/balance' })).toBe(false);
  });

  it('rejects when get_balance is missing', () => {
    expect(isValidPaymentApi({ create_invoice: '/api/v1/invoices' })).toBe(false);
  });

  it('rejects when create_invoice is not a string', () => {
    expect(isValidPaymentApi({ create_invoice: 123, get_balance: '/api/v1/balance' })).toBe(false);
  });

  it('rejects when get_balance is not a string', () => {
    expect(isValidPaymentApi({ create_invoice: '/api/v1/invoices', get_balance: true })).toBe(
      false
    );
  });

  it('rejects an array', () => {
    expect(isValidPaymentApi(['/api/v1/invoices', '/api/v1/balance'])).toBe(false);
  });
});
