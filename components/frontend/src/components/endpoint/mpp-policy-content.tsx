import { memo, useMemo } from 'react';

import { cn } from '@/lib/utils';
import { parseXenditConfig, UNIT_LABEL } from '@/lib/xendit-client';

export interface MppPolicyContentProperties {
  config: Record<string, unknown>;
}

/**
 * Pay-as-you-go (MPP) policy body. Unlike the prepaid card there is no bundle
 * picker or "Buy credits" CTA — billing is automatic, so the only thing to
 * surface is the per-request price that gets deducted from the MPP wallet.
 */
export const MppPolicyContent = memo(function MppPolicyContent({
  config
}: Readonly<MppPolicyContentProperties>) {
  // Reuse the shared config parser — MPP publishes `price` + `currency` +
  // `unit_type` in the same shape the prepaid parser already understands.
  const parsed = useMemo(() => parseXenditConfig(config), [config]);
  const { currency, pricePerUnit, unit } = parsed;

  if (pricePerUnit === null || pricePerUnit <= 0) return null;

  return (
    <div className='mt-3'>
      <div
        className={cn(
          'flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5',
          'border border-emerald-200 bg-emerald-50/70',
          'dark:border-emerald-900/60 dark:bg-emerald-950/20'
        )}
      >
        <span className='text-[11px] font-medium text-emerald-700 dark:text-emerald-400'>
          Price per {UNIT_LABEL[unit].singular}
        </span>
        <span className='text-[11px] font-semibold text-emerald-700 tabular-nums dark:text-emerald-400'>
          {currency} {pricePerUnit.toLocaleString()}
        </span>
      </div>
    </div>
  );
});
