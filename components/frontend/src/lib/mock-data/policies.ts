import type { Policy } from '@/lib/types';

/** Prepaid (Xendit) policy — buy credit bundles, draw down per request/document. */
export function createXenditPrepaidPolicy(
  endpointSlug: string,
  options: {
    description?: string;
    price?: number;
    unit?: 'request' | 'document';
    currency?: string;
    bundles?: Array<{ name: string; amount: number }>;
  } = {}
): Policy {
  const {
    description = 'Prepaid credits — purchase a bundle, then draw down on each API call',
    price = 0.01,
    unit = 'request',
    currency = 'USD',
    bundles = [
      { name: 'Starter', amount: 1_000 },
      { name: 'Growth', amount: 5_000 },
      { name: 'Enterprise', amount: 10_000 }
    ]
  } = options;

  return {
    type: 'xendit',
    version: '1.0',
    enabled: true,
    description,
    config: {
      price,
      unit_type: unit,
      currency,
      country: 'US',
      applied_to: ['*'],
      bundles,
      payment_url: 'https://demo.syft.space/api/v1/payments/gateway/xendit/invoices',
      credits_url: `https://demo.syft.space/api/v1/payments/gateway/bundles/${endpointSlug}`
    }
  };
}

/** Pay-per-use transaction policy (no prepaid bundle). */
export function createTransactionPolicy(
  price: number,
  pricingMode: 'per_call' | 'per_token' = 'per_call'
): Policy {
  return {
    type: 'transaction',
    version: '1.0',
    enabled: true,
    description: 'Pay per use',
    config: {
      pricingMode,
      price,
      currency: 'USD'
    }
  };
}

export function hasPrepaidPolicy(policies: Policy[] | undefined): boolean {
  return (policies ?? []).some((p) => p.type.toLowerCase() === 'xendit' && p.enabled);
}
