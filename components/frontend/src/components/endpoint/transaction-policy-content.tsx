import React, { memo } from 'react';

// Helper to format cost values for display
export function formatCost(value: number, unit: string): string {
  if (unit === 'token' || unit === 'tokens') {
    // Convert per-token cost to per-million tokens for readability
    const perMillion = value * 1_000_000;
    if (perMillion < 0.01) {
      return `$${(perMillion * 1000).toFixed(2)} / 1B`;
    }
    return `$${perMillion.toFixed(2)} / 1M`;
  }
  if (unit === 'query' || unit === 'queries') {
    // Convert per-query cost to per-thousand queries
    const perThousand = value * 1000;
    return `$${perThousand.toFixed(2)} / 1K`;
  }
  // Default: show as-is with 6 decimal places
  return `$${value.toFixed(6)}`;
}

// Helper to format config key names for display
export function formatConfigKey(key: string): string {
  return key
    .replaceAll('_', ' ')
    .replaceAll(/([A-Z])/g, ' $1')
    .replaceAll(/^./g, (firstChar) => firstChar.toUpperCase())
    .trim();
}

export interface TransactionPolicyContentProperties {
  config: Record<string, unknown>;
}

// Transaction policy specific renderer - memoized to prevent unnecessary re-renders
export const TransactionPolicyContent = memo(function TransactionPolicyContent({
  config
}: Readonly<TransactionPolicyContentProperties>) {
  const costs = config.costs as Record<string, unknown> | undefined;
  const provider = config.provider as string | undefined;
  const pricingModel = config.pricing_model as string | undefined;
  const billingUnit = config.billing_unit as string | undefined;

  return (
    <div className='mt-3 space-y-2'>
      {/* Provider & Model Info */}
      {provider || pricingModel ? (
        <div className='text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs'>
          {provider ? (
            <span>
              Provider: <span className='text-foreground font-medium'>{provider}</span>
            </span>
          ) : null}
          {pricingModel ? (
            <span>
              Model:{' '}
              <span className='text-foreground font-medium'>{formatConfigKey(pricingModel)}</span>
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Pricing Table */}
      {costs ? (
        <div className='bg-card/60 rounded-md border border-emerald-200 dark:border-emerald-800'>
          <div className='border-b border-emerald-100 px-3 py-1.5 dark:border-emerald-800'>
            <span className='text-[10px] font-semibold tracking-wide text-emerald-700 uppercase dark:text-emerald-400'>
              Pricing
            </span>
          </div>
          <div className='divide-y divide-emerald-100 dark:divide-emerald-800'>
            {Object.entries(costs)
              .filter(
                ([key, value]) =>
                  key !== 'currency' && key !== 'retrieval_per_query' && typeof value === 'number'
              )
              .map(([key, value]) => (
                <div key={key} className='flex items-center justify-between px-3 py-1.5'>
                  <span className='text-muted-foreground text-xs'>{formatConfigKey(key)}</span>
                  <span className='text-foreground font-mono text-xs font-medium'>
                    {formatCost(
                      value as number,
                      key.includes('token') ? (billingUnit ?? 'token') : 'query'
                    )}
                  </span>
                </div>
              ))}
          </div>
        </div>
      ) : null}
    </div>
  );
});
