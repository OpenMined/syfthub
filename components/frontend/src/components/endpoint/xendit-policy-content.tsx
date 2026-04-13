import React, { memo, useEffect, useState } from 'react';

import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import { Badge } from '@/components/ui/badge';
import { syftClient } from '@/lib/sdk-client';
import { cn } from '@/lib/utils';

interface MoneyBundle {
  name: string;
  amount: number;
}

type SubscriptionState =
  | { state: 'loading' }
  | { state: 'subscribed'; remaining: number | null }
  | { state: 'not_subscribed' };

function isValidUrl(value: unknown): value is string {
  return typeof value === 'string' && (value.startsWith('https://') || value.startsWith('http://'));
}

// bundleUsageUrl is an external URL owned by the endpoint operator, not a SyftHub API endpoint,
// so raw fetch is intentional here rather than routing through syftClient.
async function fetchSubscriptionStatus(
  bundleUsageUrl: string,
  accessToken: string
): Promise<{ remaining: number | null } | null> {
  try {
    const response = await fetch(bundleUsageUrl, {
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (!response.ok) return null;
    const data: unknown = await response.json();
    if (typeof data !== 'object' || data === null) return { remaining: null };
    const d = data as Record<string, unknown>;
    const remaining = typeof d.remaining_balance === 'number' ? d.remaining_balance : null;
    return { remaining };
  } catch {
    return null;
  }
}

export interface XenditPolicyContentProperties {
  config: Record<string, unknown>;
  enabled: boolean;
}

export const XenditPolicyContent = memo(function XenditPolicyContent({
  config,
  enabled
}: Readonly<XenditPolicyContentProperties>) {
  const currency = typeof config.currency === 'string' ? config.currency : 'IDR';
  const paymentUrl = isValidUrl(config.payment_url) ? config.payment_url : null;
  const bundleUsageUrl = isValidUrl(config.credits_url) ? config.credits_url : null;
  const bundles: MoneyBundle[] = Array.isArray(config.bundles)
    ? (config.bundles as MoneyBundle[])
    : [];

  const [status, setStatus] = useState<SubscriptionState>({ state: 'loading' });

  useEffect(() => {
    const tokens = syftClient.getTokens();
    if (!tokens || !bundleUsageUrl) {
      setStatus({ state: 'not_subscribed' });
      return;
    }

    let cancelled = false;
    void fetchSubscriptionStatus(bundleUsageUrl, tokens.accessToken).then((result) => {
      if (cancelled) return;
      if (result === null) {
        setStatus({ state: 'not_subscribed' });
      } else {
        setStatus({ state: 'subscribed', remaining: result.remaining });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [bundleUsageUrl]);

  return (
    <div className='mt-3 space-y-2'>
      <Badge
        variant='outline'
        className='border-violet-200 bg-violet-50 text-[10px] font-medium text-violet-700 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-400'
      >
        Xendit Bundle Required
      </Badge>

      {status.state === 'loading' && (
        <div className='text-muted-foreground flex items-center gap-2 text-xs'>
          <Loader2 className='h-3 w-3 animate-spin' />
          Checking subscription…
        </div>
      )}

      {status.state === 'subscribed' && (
        <div className='flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-800 dark:bg-emerald-950/30'>
          <CheckCircle2 className='h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400' />
          <span className='text-xs font-medium text-emerald-700 dark:text-emerald-400'>
            Active subscription
            {status.remaining === null
              ? ''
              : ` · ${currency} ${status.remaining.toLocaleString()} remaining`}
          </span>
        </div>
      )}

      {/* Bundle table + CTA — only when not subscribed */}
      {status.state === 'not_subscribed' && (
        <>
          {bundles.length > 0 && (
            <div className='bg-card/60 rounded-md border border-violet-200 dark:border-violet-800'>
              <div className='border-b border-violet-100 px-3 py-1.5 dark:border-violet-800'>
                <span className='text-[10px] font-semibold tracking-wide text-violet-700 uppercase dark:text-violet-400'>
                  Available Plans
                </span>
              </div>
              <div className='divide-y divide-violet-100 dark:divide-violet-800'>
                {bundles.map((bundle) => (
                  <div key={bundle.name} className='flex items-center justify-between px-3 py-1.5'>
                    <span className='text-foreground text-xs font-medium'>{bundle.name}</span>
                    <span className='text-foreground font-mono text-xs font-medium'>
                      {currency} {bundle.amount.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(() => {
            const active = Boolean(paymentUrl && enabled);
            return (
              <a
                href={active ? (paymentUrl ?? undefined) : undefined}
                target={active ? '_blank' : undefined}
                rel={active ? 'noopener noreferrer' : undefined}
                aria-disabled={!active}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  'border border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
                  active
                    ? 'cursor-pointer hover:bg-violet-100 dark:hover:bg-violet-900/40'
                    : 'cursor-not-allowed opacity-50'
                )}
              >
                <ExternalLink className='h-3 w-3' />
                Subscribe
              </a>
            );
          })()}
        </>
      )}
    </div>
  );
});
