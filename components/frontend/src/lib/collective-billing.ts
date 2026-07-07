/**
 * Shared collective-billing helpers.
 *
 * One place that knows how to turn a {@link CollectiveBillingSummary} into the
 * buyer's prepaid settlement units, reused by:
 *
 * - the chat precheck ({@link import('@/hooks/use-xendit-precheck')}), which
 *   renders one gate row per member endpoint (mirroring standalone endpoints);
 * - the collective accounts modal, which groups members per publisher wallet.
 *
 * Both share {@link collectivePrepaidMembers} — the per-member parse that
 * decides which members are *settlable prepaid wallets* and normalises their
 * pricing — so the two surfaces can never disagree on what a collective costs.
 *
 * Also exposes {@link parseCollectivePath}, the client-side mirror of the
 * TypeScript SDK's `collective/<slug>[/<shared-slug>]` parsing, so the chat
 * precheck can map a collective ChatSource back to its billing summary.
 */
import type { EndpointReference, PendingSubscription } from '@/hooks/use-xendit-precheck';
import type { CollectiveBillingSummary } from '@/lib/collectives-api';
import type { MoneyBundle, PolicyUnit } from '@/lib/xendit-client';

const COLLECTIVE_PREFIX = 'collective/';

/**
 * Parse a `collective/<slug>` or `collective/<slug>/<shared-slug>` path into
 * its parts, normalising the `all` subset alias away (it means "every approved
 * member", the same as omitting the subset). Returns `null` for any path that
 * is not a collective reference. Mirrors `expandCollectivePaths` in the
 * TypeScript SDK so chat and the SDK agree on what a collective path means.
 */
export function parseCollectivePath(
  fullPath: string | undefined | null
): { slug: string; sharedSlug?: string } | null {
  if (!fullPath?.startsWith(COLLECTIVE_PREFIX)) return null;
  const rest = fullPath.slice(COLLECTIVE_PREFIX.length);
  const slashAt = rest.indexOf('/');
  const slug = slashAt === -1 ? rest : rest.slice(0, slashAt);
  if (!slug) return null;
  const rawShared = slashAt === -1 ? undefined : rest.slice(slashAt + 1);
  const sharedSlug = rawShared && rawShared !== 'all' ? rawShared : undefined;
  return { slug, sharedSlug };
}

/**
 * A single collective member that settles via a publisher prepaid wallet,
 * normalised for the settlement UIs. Members that aren't prepaid, or whose
 * policy lacks the URLs / identity needed to read a balance or buy credits,
 * are dropped (they can't drive settlement).
 */
export interface CollectivePrepaidMember {
  endpointId: number;
  ownerUsername: string;
  slug: string;
  name: string;
  /** owner/slug, as displayed and as the satellite-token subject. */
  path: string;
  paymentUrl: string;
  creditsUrl: string;
  bundles: MoneyBundle[];
  currency: string;
  pricePerUnit: number | null;
  unit: PolicyUnit;
}

/** Extract the settlable prepaid members from a billing summary. */
export function collectivePrepaidMembers(
  summary: CollectiveBillingSummary | null | undefined
): CollectivePrepaidMember[] {
  if (!summary) return [];
  const out: CollectivePrepaidMember[] = [];
  for (const member of summary.members) {
    const b = member.billing;
    if (b.kind !== 'prepaid') continue;
    if (!b.credits_url || !b.payment_url) continue;
    if (!member.endpoint_owner_username || !member.endpoint_slug) continue;
    out.push({
      endpointId: member.endpoint_id,
      ownerUsername: member.endpoint_owner_username,
      slug: member.endpoint_slug,
      name: member.endpoint_name ?? member.endpoint_slug,
      path: `${member.endpoint_owner_username}/${member.endpoint_slug}`,
      paymentUrl: b.payment_url,
      creditsUrl: b.credits_url,
      bundles: b.bundles.map((bundle) => ({ name: bundle.name, amount: bundle.amount })),
      currency: b.currency ?? 'IDR',
      pricePerUnit: b.price_per_unit,
      unit: b.unit === 'document' ? 'document' : 'request'
    });
  }
  return out;
}

/** Build an {@link EndpointReference} for a prepaid member. */
function memberReference(member: CollectivePrepaidMember): EndpointReference {
  return {
    id: String(member.endpointId),
    path: member.path,
    owner: member.ownerUsername,
    slug: member.slug,
    name: member.name,
    role: 'data_source'
  };
}

/**
 * Group a collective's prepaid members by publisher wallet (`credits_url`) into
 * {@link PendingSubscription}s — one row per wallet, the shape the collective
 * accounts modal renders. Members sharing a wallet collapse into one row whose
 * `endpoints` lists them all (paying once funds them all).
 */
export function collectivePrepaidGroups(
  summary: CollectiveBillingSummary | null | undefined
): PendingSubscription[] {
  const byWallet = new Map<string, PendingSubscription>();
  for (const member of collectivePrepaidMembers(summary)) {
    const reference = memberReference(member);
    const existing = byWallet.get(member.creditsUrl);
    if (existing) {
      existing.endpoints.push(reference);
      continue;
    }
    byWallet.set(member.creditsUrl, {
      walletKey: member.creditsUrl,
      endpoints: [reference],
      paymentUrl: member.paymentUrl,
      creditsUrl: member.creditsUrl,
      bundles: member.bundles,
      currency: member.currency,
      pricePerUnit: member.pricePerUnit,
      unit: member.unit,
      balance: 0
    });
  }
  return [...byWallet.values()];
}
