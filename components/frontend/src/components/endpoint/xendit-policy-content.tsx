import { memo, useCallback, useState } from 'react';

import type { XenditBundleTier, XenditPaymentApi } from '@/lib/types';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Archive from 'lucide-react/dist/esm/icons/archive';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import ShoppingCart from 'lucide-react/dist/esm/icons/shopping-cart';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useXenditPurchase } from '@/hooks/use-xendit-purchase';
import { cn } from '@/lib/utils';
import { useModalStore } from '@/stores/modal-store';

/** Context needed by Xendit payment policy rendering. */
export interface XenditContext {
  endpointSlug?: string;
  ownerUsername?: string;
  spaceBaseUrl?: string;
  isLoggedIn?: boolean;
  onPurchaseSuccess?: () => void;
  archived?: boolean;
}

export interface XenditPolicyContentProperties {
  config: Record<string, unknown>;
  enabled: boolean;
  xenditContext?: XenditContext;
}

function formatPrice(price: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(price);
  } catch {
    return `${currency} ${price.toLocaleString()}`;
  }
}

/** Validates that a value conforms to the XenditBundleTier shape. */
export function isValidBundleTier(value: unknown): value is XenditBundleTier {
  if (typeof value !== 'object' || value === null) return false;
  const tier = value as Record<string, unknown>;
  return (
    typeof tier.name === 'string' &&
    typeof tier.units === 'number' &&
    typeof tier.unit_type === 'string' &&
    typeof tier.price === 'number'
  );
}

/** Validates that a value conforms to the XenditPaymentApi shape. */
export function isValidPaymentApi(value: unknown): value is XenditPaymentApi {
  if (typeof value !== 'object' || value === null) return false;
  const api = value as Record<string, unknown>;
  return typeof api.create_invoice === 'string' && typeof api.get_balance === 'string';
}

export const XenditPolicyContent = memo(function XenditPolicyContent({
  config,
  enabled,
  xenditContext
}: Readonly<XenditPolicyContentProperties>) {
  const {
    endpointSlug,
    ownerUsername,
    spaceBaseUrl,
    isLoggedIn,
    onPurchaseSuccess,
    archived = false
  } = xenditContext ?? {};
  const bundleTiers = Array.isArray(config.bundle_tiers)
    ? config.bundle_tiers.filter((tier) => isValidBundleTier(tier))
    : [];
  const paymentApi = isValidPaymentApi(config.payment_api) ? config.payment_api : undefined;
  const defaultCurrency = (config.currency as string | undefined) ?? 'USD';
  const { openLogin } = useModalStore();

  const { purchase, isLoading, error, clearError } = useXenditPurchase(
    spaceBaseUrl,
    ownerUsername,
    endpointSlug,
    paymentApi,
    onPurchaseSuccess
  );

  const [purchasingTier, setPurchasingTier] = useState<string | null>(null);

  const handleBuy = useCallback(
    async (tier: XenditBundleTier) => {
      if (!isLoggedIn) {
        openLogin();
        return;
      }
      setPurchasingTier(tier.name);
      clearError();
      try {
        await purchase(tier.name);
      } finally {
        setPurchasingTier(null);
      }
    },
    [purchase, clearError, isLoggedIn, openLogin]
  );

  if (bundleTiers.length === 0) {
    return null;
  }

  const canPurchase = enabled && !archived && !!paymentApi && !!spaceBaseUrl && !!ownerUsername;

  return (
    <div className='mt-3 space-y-2'>
      {/* Archived badge */}
      {archived ? (
        <Badge
          variant='outline'
          className='border-gray-300 bg-gray-50 text-[10px] font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-900/30 dark:text-gray-400'
        >
          <Archive className='mr-1 h-3 w-3' />
          Archived
        </Badge>
      ) : null}

      {/* Bundle tiers */}
      <div className='bg-card/60 rounded-md border border-teal-200 dark:border-teal-800'>
        <div className='border-b border-teal-100 px-3 py-1.5 dark:border-teal-800'>
          <span className='text-[10px] font-semibold tracking-wide text-teal-700 uppercase dark:text-teal-400'>
            Bundle Tiers
          </span>
        </div>
        <div className='divide-y divide-teal-100 dark:divide-teal-800'>
          {bundleTiers.map((tier) => {
            const isBuying = isLoading && purchasingTier === tier.name;
            const buttonActive = isLoggedIn ? canPurchase && !isBuying : true;

            return (
              <div key={tier.name} className='space-y-1.5 px-3 py-2'>
                {/* Top row: name + price */}
                <div className='flex items-center justify-between'>
                  <span className='text-foreground text-xs font-medium'>{tier.name}</span>
                  <span className='text-foreground font-mono text-xs font-medium'>
                    {formatPrice(tier.price, defaultCurrency)}
                  </span>
                </div>
                {/* Bottom row: units + buy button */}
                <div className='flex items-center justify-between'>
                  <span className='text-muted-foreground text-[10px]'>
                    {tier.units.toLocaleString()} {tier.unit_type}
                  </span>
                  {archived ? null : (
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={!buttonActive}
                      className={cn(
                        'h-6 px-2 text-[10px]',
                        buttonActive
                          ? 'border-teal-300 text-teal-700 hover:bg-teal-50 dark:border-teal-700 dark:text-teal-300 dark:hover:bg-teal-900/40'
                          : ''
                      )}
                      onClick={() => void handleBuy(tier)}
                    >
                      {isBuying ? (
                        <Loader2 className='mr-1 h-3 w-3 animate-spin' />
                      ) : (
                        <ShoppingCart className='mr-1 h-3 w-3' />
                      )}
                      Buy
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Error message */}
      {error ? (
        <div className='flex items-center gap-1.5 text-[10px] text-red-600 dark:text-red-400'>
          <AlertCircle className='h-3 w-3 shrink-0' />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
});
