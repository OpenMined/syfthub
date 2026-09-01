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

/**
 * Policy `type` values that bill via publisher-side prepaid credits. `cluster`
 * is a station-hosted *shared* wallet — many spaces publish the same
 * `wallet_id` under one wallet-owner account, so one balance backs them all.
 * Keep in lockstep with the backend `PREPAID_POLICY_TYPES` in
 * `schemas/endpoint.py`.
 */
export const PREPAID_POLICY_TYPES = new Set<string>(['xendit', 'stripe', 'cluster']);

/** The one policy type whose wallet claims are verified at publish time. */
export const CLUSTER_POLICY_TYPE = 'cluster';

export function isPrepaidPolicyType(type: string): boolean {
  return PREPAID_POLICY_TYPES.has(type.toLowerCase());
}

// Billing unit on a payment policy. Syft Space publishes the field as
// `unit_type` in policy.config; legacy policies omit it and bill per request.
export type PolicyUnit = 'request' | 'document';

export const UNIT_LABEL: Record<PolicyUnit, { singular: string; plural: string }> = {
  request: { singular: 'request', plural: 'requests' },
  document: { singular: 'document', plural: 'documents' }
};

export function normalizeUnit(raw: unknown): PolicyUnit {
  if (typeof raw === 'string') {
    const lower = raw.toLowerCase();
    if (lower === 'request' || lower === 'document') return lower;
  }
  return 'request';
}

export interface MoneyBundle {
  name: string;
  amount: number;
}

export interface ParsedXenditConfig {
  paymentUrl: string | null;
  creditsUrl: string | null;
  invoicesUrl: string | null;
  bundles: MoneyBundle[];
  currency: string;
  pricePerUnit: number | null;
  unit: PolicyUnit;
  country: string | null;
  /**
   * Stable shared-wallet identifier (cluster policies). Preferred over
   * `creditsUrl` as a grouping key: N spaces publish the URL independently,
   * so string drift would split one wallet into several.
   */
  walletId: string | null;
  /**
   * Username of the wallet-hosting Hub account, injected server-side at
   * publish time (cluster policies). This is the satellite-token audience;
   * `null` means self-hosted → the endpoint owner is the audience.
   */
  walletOwnerUsername: string | null;
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
  const invoicesUrl = pickConfigValue(config, 'invoices_url', 'invoicesUrl', isValidUrl);
  const currency = pickConfigValue(config, 'currency', 'currency', isStringValue) ?? 'IDR';
  const country = pickConfigValue(config, 'country', 'country', isStringValue);
  // New shape sends generic `price`; legacy policies used `price_per_request`.
  const pricePerUnit =
    pickConfigValue(config, 'price', 'price', isNumberValue) ??
    pickConfigValue(config, 'price_per_request', 'pricePerRequest', isNumberValue);
  const unit = normalizeUnit(pickConfigValue(config, 'unit_type', 'unitType', isStringValue));
  const rawBundles = pickConfigValue(config, 'bundles', 'bundles', isUnknownArray) ?? [];
  const bundles: MoneyBundle[] = rawBundles.filter(
    (b): b is MoneyBundle =>
      typeof b === 'object' &&
      b !== null &&
      typeof (b as Record<string, unknown>).name === 'string' &&
      typeof (b as Record<string, unknown>).amount === 'number'
  );
  const walletId = pickConfigValue(config, 'wallet_id', 'walletId', isStringValue);
  const walletOwnerUsername = pickConfigValue(
    config,
    'wallet_owner_username',
    'walletOwnerUsername',
    isStringValue
  );
  return {
    paymentUrl,
    creditsUrl,
    invoicesUrl,
    bundles,
    currency,
    pricePerUnit,
    unit,
    country,
    walletId: walletId !== null && walletId !== '' ? walletId : null,
    walletOwnerUsername:
      walletOwnerUsername !== null && walletOwnerUsername !== '' ? walletOwnerUsername : null
  };
}

/**
 * Whether a policy may carry a wallet identity (`wallet_id`,
 * `wallet_owner_username`) of its own.
 *
 * Only `cluster` may. Its `wallet_owner` and every wallet URL are verified
 * against that owner's registered domain when it is published, so the claim
 * has been proven. Self-hosted (`xendit` / `stripe`) policy URLs are never
 * domain-verified, so the same fields on one are ignored: honoring them would
 * let a publisher group their endpoint into somebody else's wallet, or have
 * buyers mint satellite tokens for an account they don't own and collect
 * those tokens at a host they do.
 *
 * Gating on read — rather than trusting publish-time stripping alone — also
 * neutralizes rows stored before that stripping existed.
 */
function mayCarryWalletIdentity(policyType: string): boolean {
  return policyType.toLowerCase() === CLUSTER_POLICY_TYPE;
}

/**
 * The audience to mint a satellite token for when talking to this wallet's
 * gateway: the wallet-hosting account (verified cluster) or the endpoint
 * owner. The station/space verifies `aud` against its own account, so minting
 * for the wrong party yields `audience_mismatch` rejections that surface as
 * permanently-null balances.
 */
export function resolveWalletAudience(
  parsed: Pick<ParsedXenditConfig, 'walletOwnerUsername'>,
  policyType: string,
  endpointOwner: string
): string {
  if (!mayCarryWalletIdentity(policyType)) return endpointOwner;
  return parsed.walletOwnerUsername ?? endpointOwner;
}

/**
 * Stable grouping key for a wallet: the published `wallet_id` (verified
 * cluster) or the wallet's `credits_url`. Rows sharing a key share a balance
 * — one payment funds them all — so an unverified `wallet_id` must never
 * join a wallet the publisher does not own.
 */
export function resolveWalletKey(
  parsed: Pick<ParsedXenditConfig, 'walletId'>,
  policyType: string,
  creditsUrl: string
): string {
  if (!mayCarryWalletIdentity(policyType)) return creditsUrl;
  return parsed.walletId ?? creditsUrl;
}

export function formatUnitEstimate(amount: number, pricePerUnit: number, unit: PolicyUnit): string {
  const count = Math.floor(amount / pricePerUnit);
  return `~${count.toLocaleString()} ${UNIT_LABEL[unit].plural}`;
}

export function openCheckoutWindow(url: string): void {
  const width = 800;
  const height = 900;
  const left = Math.max(0, Math.round((window.screen.availWidth - width) / 2));
  const top = Math.max(0, Math.round((window.screen.availHeight - height) / 2));
  const features = `popup=yes,width=${String(width)},height=${String(height)},left=${String(left)},top=${String(top)},noopener,noreferrer`;
  window.open(url, 'xendit-checkout', features);
}

/**
 * Origin of `url`, or the raw string if it will not parse.
 *
 * The cache key for a satellite token. SyftHub resolves a satellite by origin,
 * so a wallet's credits and payment URLs share one token.
 */
export function tokenScope(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return url;
  }
}

/**
 * Mint a satellite token for `audience`, bound to `resource`.
 *
 * `resource` is the URL the token is sent to. A token only works at that one
 * host, so cache per {@link tokenScope}, never per audience — one account can
 * serve from several hosts.
 */
export async function getSatelliteToken(
  audience: string,
  resource?: string
): Promise<string | null> {
  try {
    const response = await syftClient.auth.getSatelliteToken(audience, resource);
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

export interface PendingInvoice {
  checkoutUrl: string;
  bundleName: string;
}

/**
 * Look up the caller's most recent pending invoice on a publisher wallet.
 *
 * Returns the latest pending invoice (newest first per gateway contract) so
 * that the policy card can resume an in-flight checkout when the user
 * revisits the page after closing the popup. Returns null when there is no
 * pending invoice, the gateway response is malformed, or any error occurs.
 */
export async function fetchPendingInvoice(
  invoicesUrl: string,
  satelliteToken: string,
  signal?: AbortSignal
): Promise<PendingInvoice | null> {
  try {
    const url = new URL(invoicesUrl);
    url.searchParams.set('status', 'pending');
    const response = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${satelliteToken}` },
      signal
    });
    if (!response.ok) return null;
    const data: unknown = await response.json();
    if (!Array.isArray(data) || data.length === 0) return null;
    const first = data[0];
    if (typeof first !== 'object' || first === null) return null;
    const record = first as Record<string, unknown>;
    const checkoutUrl = record.checkout_url ?? record.checkoutUrl;
    const bundleName = record.bundle_name ?? record.bundleName;
    if (typeof checkoutUrl !== 'string' || typeof bundleName !== 'string') return null;
    return { checkoutUrl, bundleName };
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
