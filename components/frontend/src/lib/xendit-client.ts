/**
 * Xendit client — shared helpers for talking to a publisher's syft_space
 * payment gateway. The Xendit-policy sidebar card, the chat-precheck hook,
 * and the subscription gate modal all need the same primitives:
 *
 * - Mint a satellite token for the endpoint owner (SyftHub SDK).
 * - GET the user's per-wallet balance against credits_url.
 * - POST a bundle purchase against payment_url, returning the checkout URL.
 * - Open the checkout in a centred popup window.
 * - Parse a Xendit policy.config dict into a typed shape.
 *
 * The hub returns policy.config through two code paths: a raw-fetch path
 * that preserves snake_case, and the SDK browse/trending path that
 * recursively camelCases every key. parseXenditConfig accepts either.
 */
import { syftClient } from '@/lib/sdk-client';

export const POLL_INTERVAL_MS = 3000;

export interface MoneyBundle {
  name: string;
  amount: number;
}

export interface ParsedXenditConfig {
  paymentUrl: string | null;
  creditsUrl: string | null;
  bundles: MoneyBundle[];
  currency: string;
  pricePerRequest: number | null;
  country: string | null;
}

export function isValidUrl(value: unknown): value is string {
  return typeof value === 'string' && (value.startsWith('https://') || value.startsWith('http://'));
}

function isStringValue(v: unknown): v is string {
  return typeof v === 'string';
}
function isNumberValue(v: unknown): v is number {
  return typeof v === 'number';
}
function isUnknownArray(v: unknown): v is unknown[] {
  return Array.isArray(v);
}

function pickConfigValue<T>(
  config: Record<string, unknown>,
  snake: string,
  camel: string,
  guard: (v: unknown) => v is T
): T | null {
  const snakeValue = config[snake];
  if (guard(snakeValue)) return snakeValue;
  const camelValue = config[camel];
  if (guard(camelValue)) return camelValue;
  return null;
}

export function parseXenditConfig(config: Record<string, unknown>): ParsedXenditConfig {
  const paymentUrl = pickConfigValue(config, 'payment_url', 'paymentUrl', isValidUrl);
  const creditsUrl = pickConfigValue(config, 'credits_url', 'creditsUrl', isValidUrl);
  const currency = pickConfigValue(config, 'currency', 'currency', isStringValue) ?? 'IDR';
  const country = pickConfigValue(config, 'country', 'country', isStringValue);
  const pricePerRequest = pickConfigValue(
    config,
    'price_per_request',
    'pricePerRequest',
    isNumberValue
  );
  const rawBundles = pickConfigValue(config, 'bundles', 'bundles', isUnknownArray) ?? [];
  const bundles: MoneyBundle[] = rawBundles.filter(
    (b): b is MoneyBundle =>
      typeof b === 'object' &&
      b !== null &&
      typeof (b as Record<string, unknown>).name === 'string' &&
      typeof (b as Record<string, unknown>).amount === 'number'
  );
  return { paymentUrl, creditsUrl, bundles, currency, pricePerRequest, country };
}

export function openCheckoutWindow(url: string): void {
  const width = 800;
  const height = 900;
  const left = Math.max(0, Math.round((window.screen.availWidth - width) / 2));
  const top = Math.max(0, Math.round((window.screen.availHeight - height) / 2));
  const features = `popup=yes,width=${String(width)},height=${String(height)},left=${String(left)},top=${String(top)},noopener,noreferrer`;
  window.open(url, 'xendit-checkout', features);
}

export async function getSatelliteToken(audience: string): Promise<string | null> {
  try {
    const response = await syftClient.auth.getSatelliteToken(audience);
    return response.targetToken;
  } catch {
    return null;
  }
}

export async function fetchBalance(
  creditsUrl: string,
  satelliteToken: string,
  signal?: AbortSignal
): Promise<number | null> {
  try {
    const response = await fetch(creditsUrl, {
      headers: { Authorization: `Bearer ${satelliteToken}` },
      signal
    });
    if (!response.ok) return null;
    const data: unknown = await response.json();
    if (typeof data !== 'object' || data === null) return null;
    const balance = (data as Record<string, unknown>).balance;
    return typeof balance === 'number' ? balance : 0;
  } catch {
    return null;
  }
}

export interface CreateInvoiceResult {
  checkoutUrl: string;
}

export async function createInvoice(
  paymentUrl: string,
  satelliteToken: string,
  bundleName: string,
  endpointSlug?: string,
  signal?: AbortSignal
): Promise<CreateInvoiceResult | { error: string }> {
  try {
    const body: Record<string, string> = { bundle_name: bundleName };
    if (endpointSlug) body.endpoint_slug = endpointSlug;
    const response = await fetch(paymentUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${satelliteToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body),
      signal
    });
    if (!response.ok) {
      let message = `Failed to create invoice (${String(response.status)})`;
      try {
        const errorData: unknown = await response.json();
        if (typeof errorData === 'object' && errorData !== null) {
          const detail = (errorData as Record<string, unknown>).detail;
          if (typeof detail === 'string') message = detail;
        }
      } catch {
        /* keep default */
      }
      return { error: message };
    }
    const data: unknown = await response.json();
    if (typeof data !== 'object' || data === null) {
      return { error: 'Invalid invoice response (missing checkout_url)' };
    }
    const checkoutUrl = (data as Record<string, unknown>).checkout_url;
    if (typeof checkoutUrl !== 'string') {
      return { error: 'Invalid invoice response (missing checkout_url)' };
    }
    return { checkoutUrl };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Network error' };
  }
}
