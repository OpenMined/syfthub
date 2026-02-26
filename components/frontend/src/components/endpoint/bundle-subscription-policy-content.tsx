import React, { memo } from 'react';

import ExternalLink from 'lucide-react/dist/esm/icons/external-link';

import { Badge } from '@/components/ui/badge';

import { formatConfigKey } from './transaction-policy-content';

const BILLING_CYCLE_LABELS: Record<string, string> = {
  one_time: 'One Time',
  monthly: 'Monthly',
  yearly: 'Yearly'
};

function isValidUrl(url: string): boolean {
  return url.startsWith('https://') || url.startsWith('http://');
}

export interface BundleSubscriptionPolicyContentProperties {
  config: Record<string, unknown>;
}

export const BundleSubscriptionPolicyContent = memo(function BundleSubscriptionPolicyContent({
  config
}: Readonly<BundleSubscriptionPolicyContentProperties>) {
  const planName = config.plan_name as string | undefined;
  const price = config.price as number | undefined;
  const currency = config.currency as string | undefined;
  const billingCycle = config.billing_cycle as string | undefined;
  const invoiceUrl = config.invoice_url as string | undefined;

  let formattedPrice: string | undefined;
  if (price !== undefined) {
    formattedPrice = currency ? `${currency} ${price.toFixed(2)}` : `$${price.toFixed(2)}`;
  }

  const formattedCycle = billingCycle
    ? (BILLING_CYCLE_LABELS[billingCycle] ?? formatConfigKey(billingCycle))
    : undefined;

  const validInvoiceUrl = invoiceUrl && isValidUrl(invoiceUrl) ? invoiceUrl : undefined;

  return (
    <div className='mt-3 space-y-2'>
      <Badge
        variant='outline'
        className='border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-400'
      >
        Subscription Required
      </Badge>

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
              <span className='text-foreground text-xs font-medium'>{planName}</span>
            </div>
          ) : null}
          {formattedPrice ? (
            <div className='flex items-center justify-between px-3 py-1.5'>
              <span className='text-muted-foreground text-xs'>Price</span>
              <span className='text-foreground font-mono text-xs font-medium'>
                {formattedPrice}
              </span>
            </div>
          ) : null}
          {formattedCycle ? (
            <div className='flex items-center justify-between px-3 py-1.5'>
              <span className='text-muted-foreground text-xs'>Billing Cycle</span>
              <span className='text-foreground text-xs font-medium'>{formattedCycle}</span>
            </div>
          ) : null}
        </div>
      </div>

      {validInvoiceUrl ? (
        <a
          href={validInvoiceUrl}
          target='_blank'
          rel='noopener noreferrer'
          className='inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-600'
        >
          Subscribe
          <ExternalLink className='h-3 w-3' />
        </a>
      ) : null}
    </div>
  );
});
