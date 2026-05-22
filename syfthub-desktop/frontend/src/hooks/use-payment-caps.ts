/**
 * React hook wrapping the Wails-bound payment-cap CRUD methods.
 *
 * The desktop persists per-endpoint spend caps to ~/.syfthub-desktop/payment_caps.json
 * (see payment_caps.go). This hook exposes a cached config object plus an
 * imperative `evaluate(slug, amount, currency)` call the chat workflow uses
 * to decide whether to silently auto-pay a payment_required challenge, fire
 * a non-blocking toast, or open the blocking modal.
 *
 * The config is loaded lazily on first use and re-fetched whenever a write
 * succeeds so two tabs sharing the same on-disk file stay roughly consistent.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  EvaluatePaymentDecision,
  GetPaymentCaps,
  ResetPaymentCap,
  SetPaymentCap,
} from '../../wailsjs/go/main/App';
import { main } from '../../wailsjs/go/models';

export type PaymentCap = main.PaymentCap;
export type PaymentCapsConfig = main.PaymentCapsConfig;
export type PaymentDecision = main.PaymentDecision;

/** Canonical PaymentDecision.Action values mirrored from payment_caps.go. */
export const PaymentDecisionAction = {
  AutoPay: 'auto_pay',
  ToastPay: 'toast_pay',
  Prompt: 'prompt',
} as const;

export type PaymentDecisionAction =
  (typeof PaymentDecisionAction)[keyof typeof PaymentDecisionAction];

export interface UsePaymentCapsReturn {
  /** Latest snapshot of the on-disk config; null until first load resolves. */
  config: PaymentCapsConfig | null;
  /** True while the initial load is in flight. */
  loading: boolean;
  /** Last error from a CRUD call (load / set / reset). */
  error: string | null;
  /** Force-reload the config from disk. */
  refresh: () => Promise<void>;
  /** Upsert a per-endpoint cap; triggers a refresh on success. */
  setCap: (cap: PaymentCap) => Promise<void>;
  /** Delete a per-endpoint cap; triggers a refresh on success. */
  resetCap: (endpointSlug: string) => Promise<void>;
  /** Pure RPC pass-through to EvaluatePaymentDecision. */
  evaluate: (
    endpointSlug: string,
    amount: string,
    currency: string,
  ) => Promise<PaymentDecision>;
}

export function usePaymentCaps(): UsePaymentCapsReturn {
  const [config, setConfig] = useState<PaymentCapsConfig | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // Guards against setState after unmount. We don't use AbortController here
  // because the Wails bound calls don't accept signals.
  const mountedRef = useRef<boolean>(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await GetPaymentCaps();
      if (mountedRef.current) {
        setConfig(cfg);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(String(err));
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  const setCap = useCallback(
    async (cap: PaymentCap) => {
      try {
        await SetPaymentCap(cap);
        await refresh();
      } catch (err) {
        if (mountedRef.current) {
          setError(String(err));
        }
        throw err;
      }
    },
    [refresh],
  );

  const resetCap = useCallback(
    async (endpointSlug: string) => {
      try {
        await ResetPaymentCap(endpointSlug);
        await refresh();
      } catch (err) {
        if (mountedRef.current) {
          setError(String(err));
        }
        throw err;
      }
    },
    [refresh],
  );

  const evaluate = useCallback(
    async (endpointSlug: string, amount: string, currency: string) => {
      return EvaluatePaymentDecision(endpointSlug, amount, currency);
    },
    [],
  );

  return { config, loading, error, refresh, setCap, resetCap, evaluate };
}
