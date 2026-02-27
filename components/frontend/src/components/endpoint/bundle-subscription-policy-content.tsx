import React, { memo } from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const BILLING_CYCLE_LABELS: Record<string, string> = {
  one_time: 'One Time',
  monthly: 'Monthly',
  yearly: 'Yearly'
};

function isValidInvoiceUrl(url: string | undefined): url is string {
  return typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'));
}

export interface BundleSubscriptionPolicyContentProperties {
  config: Record<string, unknown>;
  enabled: boolean;
}

export const BundleSubscriptionPolicyContent = memo(function BundleSubscriptionPolicyContent({
  config,
  enabled
}: Readonly<BundleSubscriptionPolicyContentProperties>) {
  const planName = config.plan_name as string | undefined;
  const price = typeof config.price === 'number' ? config.price : undefined;
  const currency = (config.currency as string | undefined) ?? 'USD';
  const billingCycle = config.billing_cycle as string | undefined;
  const invoiceUrl = config.invoice_url as string | undefined;

  const validUrl = isValidInvoiceUrl(invoiceUrl);
  const billingCycleLabel = billingCycle
    ? (BILLING_CYCLE_LABELS[billingCycle] ?? billingCycle)
    : undefined;

  return (
    <div className='mt-3 space-y-2'>
      {/* Subscription Required badge */}
      <Badge
        variant='outline'
        className='border-violet-200 bg-violet-50 text-[10px] font-medium text-violet-700 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-400'
      >
        Subscription Required
      </Badge>

      {/* Plan details */}
      <div className='bg-card/60 rounded-md border border-violet-200 dark:border-violet-800'>
        <div className='border-b border-violet-100 px-3 py-1.5 dark:border-violet-800'>
          <span className='text-[10px] font-semibold tracking-wide text-violet-700 uppercase dark:text-violet-400'>
            Plan Details
          </span>
        </div>
        <div className='divide-y divide-violet-100 dark:divide-violet-800'>
          {planName ? (
            <div className='flex items-center justify-between px-3 py-1.5'>
              <span className='text-muted-foreground text-xs'>Plan</span>
              <span className='text-foreground font-mono text-xs font-medium'>{planName}</span>
            </div>
          ) : null}
          {price === undefined ? null : (
            <div className='flex items-center justify-between px-3 py-1.5'>
              <span className='text-muted-foreground text-xs'>Price</span>
              <span className='text-foreground font-mono text-xs font-medium'>
                {currency} {price.toFixed(2)}
                {billingCycleLabel ? ` / ${billingCycleLabel}` : ''}
              </span>
            </div>
          )}
          {billingCycleLabel && price === undefined ? (
            <div className='flex items-center justify-between px-3 py-1.5'>
              <span className='text-muted-foreground text-xs'>Billing Cycle</span>
              <span className='text-foreground font-mono text-xs font-medium'>
                {billingCycleLabel}
              </span>
            </div>
          ) : null}
        </div>
      </div>

      {/* Subscribe CTA */}
      <a
        href={validUrl ? invoiceUrl : undefined}
        target='_blank'
        rel='noopener noreferrer'
        aria-disabled={!enabled || !validUrl}
        className={cn(
          'inline-flex items-center justify-center rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
          'border border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
          enabled && validUrl
            ? 'cursor-pointer hover:bg-violet-100 dark:hover:bg-violet-900/40'
            : 'pointer-events-none cursor-not-allowed opacity-50'
        )}
        onClick={
          !enabled || !validUrl
            ? (e) => {
                e.preventDefault();
              }
            : undefined
        }
      >
        Subscribe
      </a>
    </div>
  );
});
