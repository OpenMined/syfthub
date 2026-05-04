/**
 * useXenditPrecheck
 *
 * Pre-flight subscription check run before a chat message is sent.
 * Inspects the model + selected data sources for paid-policy gates,
 * dedupes by credits_url (one wallet may back multiple endpoints), and
 * fetches each balance via a satellite token. Returns the rows that
 * still need a paid subscription so the chat view can open the gate
 * modal — or an empty array when the user is clear to send.
 *
 * Also surfaces `mpp`-typed policies as always-pending rows: payment
 * for those endpoints isn't implemented yet, so the gate informs the
 * user and forces them to remove the endpoint to send.
 */
import { useCallback } from 'react';

import type { ChatSource, Policy } from '@/lib/types';
import type { MoneyBundle, ParsedXenditConfig } from '@/lib/xendit-client';

import { syftClient } from '@/lib/sdk-client';
import { fetchBalance, getSatelliteToken, parseXenditConfig } from '@/lib/xendit-client';

export type EndpointRole = 'model' | 'data_source';

export interface EndpointReference {
  /** ChatSource ID — needed to remove the source from the chat selection. */
  id: string;
  /** owner/slug as displayed in the UI */
  path: string;
  owner: string;
  slug: string;
  name: string;
  role: EndpointRole;
}

export type PolicyKind = 'xendit' | 'mpp';

export interface PendingSubscription {
  /** Which policy type this row represents. Drives the gate UI branch. */
  policyType: PolicyKind;
  /** Stable identity. credits_url for xendit; synthetic for mpp. */
  walletKey: string;
  /** All endpoints covered by this single wallet subscription. */
  endpoints: EndpointReference[];
  /** Empty string for mpp (no payment endpoint yet). */
  paymentUrl: string;
  /** Empty string for mpp (no balance endpoint yet). */
  creditsUrl: string;
  bundles: MoneyBundle[];
  currency: string;
  pricePerRequest: number | null;
  /** Last balance reading (0 when unsubscribed; always 0 for mpp). */
  balance: number;
}

interface ResolvedXenditPolicy {
  paymentUrl: string;
  creditsUrl: string;
  bundles: MoneyBundle[];
  currency: string;
  pricePerRequest: number | null;
}

function resolveXenditPolicy(policy: Policy): ResolvedXenditPolicy | null {
  if (!policy.enabled) return null;
  if (policy.type.toLowerCase() !== 'xendit') return null;
  const parsed: ParsedXenditConfig = parseXenditConfig(policy.config);
  if (!parsed.paymentUrl || !parsed.creditsUrl) return null;
  return {
    paymentUrl: parsed.paymentUrl,
    creditsUrl: parsed.creditsUrl,
    bundles: parsed.bundles,
    currency: parsed.currency,
    pricePerRequest: parsed.pricePerRequest
  };
}

function endpointReferenceFor(source: ChatSource, role: EndpointRole): EndpointReference | null {
  if (!source.owner_username || !source.full_path) return null;
  return {
    id: source.id,
    path: source.full_path,
    owner: source.owner_username,
    slug: source.slug,
    name: source.name,
    role
  };
}

interface XenditCandidate {
  kind: 'xendit';
  endpoint: EndpointReference;
  policy: ResolvedXenditPolicy;
}

interface MppCandidate {
  kind: 'mpp';
  endpoint: EndpointReference;
  currency: string;
  pricePerRequest: number | null;
}

type Candidate = XenditCandidate | MppCandidate;

function resolveMppPolicy(
  policy: Policy
): { currency: string; pricePerRequest: number | null } | null {
  if (!policy.enabled) return null;
  if (policy.type.toLowerCase() !== 'mpp') return null;
  const config = policy.config;
  const rawPrice = config.price ?? config.price_per_request ?? config.pricePerRequest;
  const pricePerRequest = typeof rawPrice === 'number' ? rawPrice : null;
  const rawCurrency = config.currency;
  const currency = typeof rawCurrency === 'string' && rawCurrency ? rawCurrency : 'USD';
  return { currency, pricePerRequest };
}

function candidatesFromSource(source: ChatSource, role: EndpointRole): Candidate[] {
  if (!source.policies) return [];
  const ref = endpointReferenceFor(source, role);
  if (!ref) return [];
  const out: Candidate[] = [];
  for (const policy of source.policies) {
    const xendit = resolveXenditPolicy(policy);
    if (xendit) {
      out.push({ kind: 'xendit', endpoint: ref, policy: xendit });
      continue;
    }
    const mpp = resolveMppPolicy(policy);
    if (mpp) {
      out.push({ kind: 'mpp', endpoint: ref, ...mpp });
    }
  }
  return out;
}

function collectCandidates(model: ChatSource | null, dataSources: ChatSource[]): Candidate[] {
  const out: Candidate[] = [];
  if (model) out.push(...candidatesFromSource(model, 'model'));
  for (const ds of dataSources) out.push(...candidatesFromSource(ds, 'data_source'));
  return out;
}

export interface UseXenditPrecheckOptions {
  model: ChatSource | null;
  dataSources: ChatSource[];
}

export interface UseXenditPrecheckReturn {
  /**
   * Resolve the precheck. Returns the wallets that still need funding.
   * On any unrecoverable error (no satellite token, network), the affected
   * wallet is *omitted* — the user gets the post-error path as a fallback
   * rather than being blocked by a flaky precheck.
   */
  runPrecheck: (signal?: AbortSignal) => Promise<PendingSubscription[]>;
}

export function useXenditPrecheck(options: UseXenditPrecheckOptions): UseXenditPrecheckReturn {
  const { model, dataSources } = options;

  const runPrecheck = useCallback(
    async (signal?: AbortSignal): Promise<PendingSubscription[]> => {
      const candidates = collectCandidates(model, dataSources);
      if (candidates.length === 0) return [];
      if (!syftClient.getTokens()) return [];

      const xenditCandidates = candidates.filter((c): c is XenditCandidate => c.kind === 'xendit');
      const mppCandidates = candidates.filter((c): c is MppCandidate => c.kind === 'mpp');

      // One satellite token per distinct xendit owner — multiple wallets
      // owned by the same publisher reuse the token. mpp rows skip this
      // because they have no balance endpoint to authenticate against.
      const owners = [...new Set(xenditCandidates.map((c) => c.endpoint.owner))];
      const tokenByOwner = new Map<string, string>();
      await Promise.all(
        owners.map(async (owner) => {
          const token = await getSatelliteToken(owner);
          if (token) tokenByOwner.set(owner, token);
        })
      );

      // One balance fetch per distinct credits_url. Multiple endpoints can
      // share a wallet — paying once funds them all — but the gate UI lists
      // each endpoint separately, so we need to know each row's status
      // without re-hitting the same credits_url.
      const distinctCreditsUrls = [...new Set(xenditCandidates.map((c) => c.policy.creditsUrl))];
      const balanceByCreditsUrl = new Map<string, number | null>();
      await Promise.all(
        distinctCreditsUrls.map(async (creditsUrl) => {
          const sample = xenditCandidates.find((c) => c.policy.creditsUrl === creditsUrl);
          if (!sample) return;
          const token = tokenByOwner.get(sample.endpoint.owner);
          if (!token) return;
          const balance = await fetchBalance(creditsUrl, token, signal);
          balanceByCreditsUrl.set(creditsUrl, balance);
        })
      );

      // One PendingSubscription per endpoint. xendit rows that share a
      // wallet keep the same `walletKey` (= credits_url) so the gate's
      // polling loop and auto-registration can dedupe by wallet, and a
      // single payment flips every sibling row to active at once.
      const out: PendingSubscription[] = [];
      for (const c of xenditCandidates) {
        const balance = balanceByCreditsUrl.get(c.policy.creditsUrl);
        if (balance === null || balance === undefined) continue;
        const threshold = c.policy.pricePerRequest ?? 1;
        if (balance >= threshold) continue;
        out.push({
          policyType: 'xendit',
          walletKey: c.policy.creditsUrl,
          endpoints: [c.endpoint],
          paymentUrl: c.policy.paymentUrl,
          creditsUrl: c.policy.creditsUrl,
          bundles: c.policy.bundles,
          currency: c.policy.currency,
          pricePerRequest: c.policy.pricePerRequest,
          balance
        });
      }
      // mpp rows are always pending — no payment flow exists yet, so we
      // surface them in the gate purely to inform the user and force a
      // remove-or-cancel decision. walletKey is synthetic (per-endpoint).
      for (const c of mppCandidates) {
        out.push({
          policyType: 'mpp',
          walletKey: `mpp::${c.endpoint.owner}/${c.endpoint.slug}`,
          endpoints: [c.endpoint],
          paymentUrl: '',
          creditsUrl: '',
          bundles: [],
          currency: c.currency,
          pricePerRequest: c.pricePerRequest,
          balance: 0
        });
      }
      return out;
    },
    [model, dataSources]
  );

  return { runPrecheck };
}
