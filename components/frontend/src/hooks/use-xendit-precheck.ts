/**
 * useXenditPrecheck
 *
 * Pre-flight subscription check run before a chat message is sent.
 * Inspects the model + selected data sources for Xendit prepaid-credits
 * policies, dedupes by credits_url (one wallet may back multiple endpoints),
 * and fetches each balance via a satellite token. Returns the rows that
 * still need a paid subscription so the chat view can open the gate
 * modal — or an empty array when the user is clear to send.
 *
 * A selected **Collective API** is a single ChatSource with no policies of its
 * own (`full_path` = `collective/<slug>[/<shared-slug>]`); the SDK fans it out
 * to its member endpoints at query time. So this precheck expands such a source
 * via its billing summary into the prepaid wallets of its members and gates
 * them exactly like standalone prepaid endpoints. MPP members are not pre-gated
 * here — like standalone MPP endpoints they settle via the aggregator's 402
 * flow at query time.
 */
import { useCallback } from 'react';

import type { CollectivePrepaidMember } from '@/lib/collective-billing';
import type { CollectiveBillingSummary } from '@/lib/collectives-api';
import type { ChatSource, Policy } from '@/lib/types';
import type { MoneyBundle, ParsedXenditConfig, PolicyUnit } from '@/lib/xendit-client';

import { collectivePrepaidMembers, parseCollectivePath } from '@/lib/collective-billing';
import { getCollectiveBillingSummary } from '@/lib/collectives-api';
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

export interface PendingSubscription {
  /** Stable identity = credits_url. Rows sharing a wallet share this key. */
  walletKey: string;
  /** All endpoints covered by this single wallet subscription. */
  endpoints: EndpointReference[];
  paymentUrl: string;
  creditsUrl: string;
  bundles: MoneyBundle[];
  currency: string;
  pricePerUnit: number | null;
  unit: PolicyUnit;
  /** Last balance reading (0 when unsubscribed). */
  balance: number;
  /**
   * Whether the chat gate may offer to remove this row from the selection.
   * Standalone endpoints are removable; rows expanded from a Collective API are
   * not (you can't drop one member of a collective). Treated as `true` when
   * omitted, so callers that build subscriptions outside the gate need not set it.
   */
  removable?: boolean;
}

interface ResolvedXenditPolicy {
  paymentUrl: string;
  creditsUrl: string;
  bundles: MoneyBundle[];
  currency: string;
  pricePerUnit: number | null;
  unit: PolicyUnit;
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
    pricePerUnit: parsed.pricePerUnit,
    unit: parsed.unit
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
  endpoint: EndpointReference;
  policy: ResolvedXenditPolicy;
  /** Whether the gate row may be removed (false for collective members). */
  removable: boolean;
}

function candidatesFromSource(source: ChatSource, role: EndpointRole): XenditCandidate[] {
  if (!source.policies) return [];
  const ref = endpointReferenceFor(source, role);
  if (!ref) return [];
  const out: XenditCandidate[] = [];
  for (const policy of source.policies) {
    const xendit = resolveXenditPolicy(policy);
    if (xendit) out.push({ endpoint: ref, policy: xendit, removable: true });
  }
  return out;
}

/** Map one collective prepaid member to a gate candidate (non-removable). */
function candidateFromCollectiveMember(member: CollectivePrepaidMember): XenditCandidate {
  return {
    endpoint: {
      id: String(member.endpointId),
      path: member.path,
      owner: member.ownerUsername,
      slug: member.slug,
      name: member.name,
      role: 'data_source'
    },
    policy: {
      paymentUrl: member.paymentUrl,
      creditsUrl: member.creditsUrl,
      bundles: member.bundles,
      currency: member.currency,
      pricePerUnit: member.pricePerUnit,
      unit: member.unit
    },
    removable: false
  };
}

/**
 * Expand a Collective API source into the prepaid candidates of its members.
 *
 * Fetches the source's billing summary (auth-gated) and pulls out the prepaid
 * members. A non-collective source, an unresolvable summary (404/401 → `null`),
 * or one with no prepaid members all yield `[]`, so a failed expansion never
 * blocks send — the aggregator's per-member enforcement remains the backstop.
 */
async function candidatesFromCollective(source: ChatSource): Promise<XenditCandidate[]> {
  const parsed = parseCollectivePath(source.full_path);
  if (!parsed) return [];
  let summary: CollectiveBillingSummary | null;
  try {
    summary = await getCollectiveBillingSummary(parsed.slug, parsed.sharedSlug);
  } catch {
    return [];
  }
  return collectivePrepaidMembers(summary).map((member) => candidateFromCollectiveMember(member));
}

function collectCandidates(model: ChatSource | null, dataSources: ChatSource[]): XenditCandidate[] {
  const out: XenditCandidate[] = [];
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
      // Auth-gate first: the billing-summary expansion (and satellite tokens)
      // both need a signed-in user, so bail before any network work otherwise.
      if (!syftClient.getTokens()) return [];

      // Standalone endpoints expose their policies inline; Collective API
      // sources have none and must be expanded via their billing summary.
      const collectiveLists = await Promise.all(
        dataSources.map((ds) => candidatesFromCollective(ds))
      );
      const candidates = [...collectCandidates(model, dataSources), ...collectiveLists.flat()];
      if (candidates.length === 0) return [];

      // One satellite token per distinct owner — multiple wallets owned by
      // the same publisher reuse the token.
      const owners = [...new Set(candidates.map((c) => c.endpoint.owner))];
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
      const distinctCreditsUrls = [...new Set(candidates.map((c) => c.policy.creditsUrl))];
      const balanceByCreditsUrl = new Map<string, number | null>();
      await Promise.all(
        distinctCreditsUrls.map(async (creditsUrl) => {
          const sample = candidates.find((c) => c.policy.creditsUrl === creditsUrl);
          if (!sample) return;
          const token = tokenByOwner.get(sample.endpoint.owner);
          if (!token) return;
          const balance = await fetchBalance(creditsUrl, token, signal);
          balanceByCreditsUrl.set(creditsUrl, balance);
        })
      );

      // One PendingSubscription per endpoint. Rows that share a wallet keep
      // the same `walletKey` (= credits_url) so the gate's polling loop and
      // auto-registration can dedupe by wallet, and a single payment flips
      // every sibling row to active at once.
      const out: PendingSubscription[] = [];
      for (const c of candidates) {
        const balance = balanceByCreditsUrl.get(c.policy.creditsUrl);
        if (balance === null || balance === undefined) continue;
        const threshold = c.policy.pricePerUnit ?? 1;
        if (balance >= threshold) continue;
        out.push({
          walletKey: c.policy.creditsUrl,
          endpoints: [c.endpoint],
          paymentUrl: c.policy.paymentUrl,
          creditsUrl: c.policy.creditsUrl,
          bundles: c.policy.bundles,
          currency: c.policy.currency,
          pricePerUnit: c.policy.pricePerUnit,
          unit: c.policy.unit,
          balance,
          removable: c.removable
        });
      }
      return out;
    },
    [model, dataSources]
  );

  return { runPrecheck };
}
