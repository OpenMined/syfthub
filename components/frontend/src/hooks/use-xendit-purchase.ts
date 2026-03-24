import { useCallback, useEffect, useRef } from 'react';

import type { XenditPaymentApi } from '@/lib/types';

import { useMutation } from '@tanstack/react-query';

import { syftClient } from '@/lib/sdk-client';

interface UseXenditPurchaseReturn {
  /** Initiate purchase for a tier. Opens checkout in a popup window. */
  purchase: (tierName: string) => Promise<void>;
  /** Whether a purchase is in progress */
  isLoading: boolean;
  /** Error message from the last purchase attempt */
  error: string | null;
  /** Clear the error state */
  clearError: () => void;
}

interface CreateInvoiceResponse {
  id: string;
  checkout_url: string;
  status: string;
}

const POPUP_WIDTH = 500;
const POPUP_HEIGHT = 700;
const POPUP_POLL_INTERVAL = 500;

/**
 * Hook for purchasing Xendit bundle tiers via Syft Space.
 *
 * Flow:
 * 1. Get satellite token for the Syft Space tenant
 * 2. POST to {spaceBaseUrl}{paymentApi.create_invoice}
 * 3. Open checkout_url in a centered popup window
 * 4. Poll for popup close, then call onPopupClosed to refresh balance
 */
export function useXenditPurchase(
  spaceBaseUrl: string | undefined,
  ownerUsername: string | undefined,
  endpointSlug: string | undefined,
  paymentApi: XenditPaymentApi | undefined,
  onPopupClosed?: () => void
): UseXenditPurchaseReturn {
  const pollTimerReference = useRef<ReturnType<typeof setInterval> | null>(null);
  const onPopupClosedRef = useRef(onPopupClosed);
  onPopupClosedRef.current = onPopupClosed;

  // Cleanup poll timer on unmount
  useEffect(() => {
    return () => {
      if (pollTimerReference.current) {
        clearInterval(pollTimerReference.current);
      }
    };
  }, []);

  const mutation = useMutation({
    mutationFn: async (tierName: string) => {
      if (!spaceBaseUrl || !ownerUsername || !endpointSlug || !paymentApi?.create_invoice) {
        throw new Error('Purchase is not available for this endpoint.');
      }

      // Pre-open popup synchronously within user gesture context to avoid browser blocking
      const left = Math.round(window.screenX + (window.outerWidth - POPUP_WIDTH) / 2);
      const top = Math.round(window.screenY + (window.outerHeight - POPUP_HEIGHT) / 2);
      const popup = window.open(
        'about:blank',
        'xendit-checkout',
        `width=${String(POPUP_WIDTH)},height=${String(POPUP_HEIGHT)},left=${String(left)},top=${String(top)},menubar=no,toolbar=no,location=no,status=no`
      );

      try {
        // Get satellite token for the Syft Space tenant
        const tokenResponse = await syftClient.auth.getSatelliteToken(ownerUsername);
        const token = tokenResponse.targetToken;

        // Call Syft Space create invoice API
        const invoiceUrl = `${spaceBaseUrl}${paymentApi.create_invoice}`;
        const response = await fetch(invoiceUrl, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            endpoint_slug: endpointSlug,
            tier_name: tierName
          })
        });

        if (!response.ok) {
          const errorData = (await response.json().catch(() => null)) as Record<
            string,
            unknown
          > | null;
          const detail =
            typeof errorData?.detail === 'string'
              ? errorData.detail
              : `Failed to create invoice (${String(response.status)})`;
          throw new Error(detail);
        }

        const data = (await response.json()) as CreateInvoiceResponse;

        if (!data.checkout_url) {
          throw new Error('No checkout URL returned from payment service.');
        }

        // Navigate the pre-opened popup to the checkout URL
        if (popup) {
          popup.location.href = data.checkout_url;
        }

        // Clear any existing poll timer before setting a new one
        if (pollTimerReference.current) {
          clearInterval(pollTimerReference.current);
          pollTimerReference.current = null;
        }

        // Poll for popup close to trigger balance refresh
        if (popup) {
          pollTimerReference.current = setInterval(() => {
            if (popup.closed) {
              if (pollTimerReference.current) {
                clearInterval(pollTimerReference.current);
                pollTimerReference.current = null;
              }
              onPopupClosedRef.current?.();
            }
          }, POPUP_POLL_INTERVAL);
        }
      } catch (error_) {
        // Close the pre-opened popup on failure
        if (popup && !popup.closed) {
          popup.close();
        }
        throw error_;
      }
    }
  });

  const purchase = useCallback(
    async (tierName: string): Promise<void> => {
      await mutation.mutateAsync(tierName);
    },
    [mutation.mutateAsync]
  );

  const clearError = useCallback(() => {
    mutation.reset();
  }, [mutation.reset]);

  const error =
    mutation.error instanceof Error
      ? mutation.error.message
      : mutation.error
        ? 'Purchase failed. Please try again.'
        : null;

  return { purchase, isLoading: mutation.isPending, error, clearError };
}
