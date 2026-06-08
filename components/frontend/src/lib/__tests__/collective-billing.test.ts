import type {
  CollectiveBillingSummary,
  CollectiveMemberBilling,
  MemberBillingDetail
} from '@/lib/collectives-api';

import { describe, expect, it } from 'vitest';

import {
  collectivePrepaidGroups,
  collectivePrepaidMembers,
  parseCollectivePath
} from '../collective-billing';

// ── fixtures ────────────────────────────────────────────────────────────────

function prepaidBilling(over: Partial<MemberBillingDetail> = {}): MemberBillingDetail {
  return {
    kind: 'prepaid',
    provider: 'xendit',
    currency: 'IDR',
    price_per_unit: 2500,
    unit: 'request',
    payment_url: 'https://pay.example.com/invoice',
    credits_url: 'https://pay.example.com/balance',
    invoices_url: null,
    bundles: [{ name: 'Starter', amount: 50_000 }],
    ...over
  };
}

function member(
  id: number,
  billing: MemberBillingDetail,
  over: Partial<CollectiveMemberBilling> = {}
): CollectiveMemberBilling {
  return {
    endpoint_id: id,
    endpoint_name: `Endpoint ${String(id)}`,
    endpoint_slug: `endpoint-${String(id)}`,
    endpoint_owner_username: 'alice',
    endpoint_owner_full_name: 'Alice',
    endpoint_type: 'data_source',
    billing,
    ...over
  };
}

function summary(members: CollectiveMemberBilling[]): CollectiveBillingSummary {
  return {
    members,
    estimated_price: [],
    free_count: 0,
    prepaid_count: 0,
    mpp_count: 0
  };
}

const freeBilling: MemberBillingDetail = {
  kind: 'free',
  provider: null,
  currency: null,
  price_per_unit: null,
  unit: 'request',
  payment_url: null,
  credits_url: null,
  invoices_url: null,
  bundles: []
};

const mppBilling: MemberBillingDetail = {
  kind: 'mpp',
  provider: null,
  currency: 'USD',
  price_per_unit: 1.5,
  unit: 'request',
  payment_url: null,
  credits_url: null,
  invoices_url: null,
  bundles: []
};

// ── parseCollectivePath ──────────────────────────────────────────────────────

describe('parseCollectivePath', () => {
  it('parses a bare collective path', () => {
    expect(parseCollectivePath('collective/genomics')).toEqual({ slug: 'genomics' });
  });

  it('treats the /all alias as the whole collective', () => {
    expect(parseCollectivePath('collective/genomics/all')).toEqual({ slug: 'genomics' });
  });

  it('parses a curated subset slug', () => {
    expect(parseCollectivePath('collective/genomics/oncology')).toEqual({
      slug: 'genomics',
      sharedSlug: 'oncology'
    });
  });

  it('returns null for non-collective and malformed paths', () => {
    const invalid: (string | undefined | null)[] = ['alice/model', 'collective/', undefined, null];
    for (const path of invalid) {
      expect(parseCollectivePath(path)).toBeNull();
    }
  });
});

// ── collectivePrepaidMembers ─────────────────────────────────────────────────

describe('collectivePrepaidMembers', () => {
  it('returns only settlable prepaid members', () => {
    const result = collectivePrepaidMembers(
      summary([member(1, prepaidBilling()), member(2, mppBilling), member(3, freeBilling)])
    );
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      endpointId: 1,
      ownerUsername: 'alice',
      path: 'alice/endpoint-1',
      creditsUrl: 'https://pay.example.com/balance',
      currency: 'IDR',
      pricePerUnit: 2500
    });
  });

  it('drops prepaid members missing the payment/credits URLs', () => {
    const result = collectivePrepaidMembers(
      summary([
        member(1, prepaidBilling({ credits_url: null })),
        member(2, prepaidBilling({ payment_url: null }))
      ])
    );
    expect(result).toEqual([]);
  });

  it('drops prepaid members with no owner or slug', () => {
    const result = collectivePrepaidMembers(
      summary([
        member(1, prepaidBilling(), { endpoint_owner_username: null }),
        member(2, prepaidBilling(), { endpoint_slug: null })
      ])
    );
    expect(result).toEqual([]);
  });

  it('handles an empty summary', () => {
    const empties: (CollectiveBillingSummary | null | undefined)[] = [null, undefined];
    for (const empty of empties) {
      expect(collectivePrepaidMembers(empty)).toEqual([]);
    }
  });
});

// ── collectivePrepaidGroups ──────────────────────────────────────────────────

describe('collectivePrepaidGroups', () => {
  it('groups members sharing a wallet into one subscription', () => {
    const sharedWallet = 'https://pay.example.com/shared-balance';
    const groups = collectivePrepaidGroups(
      summary([
        member(1, prepaidBilling({ credits_url: sharedWallet })),
        member(2, prepaidBilling({ credits_url: sharedWallet })),
        member(3, prepaidBilling()) // its own wallet
      ])
    );
    expect(groups).toHaveLength(2);
    const shared = groups.find((g) => g.walletKey === sharedWallet);
    expect(shared?.endpoints).toHaveLength(2);
    const solo = groups.find((g) => g.walletKey !== sharedWallet);
    expect(solo?.endpoints).toHaveLength(1);
  });

  it('seeds each subscription balance at 0', () => {
    const groups = collectivePrepaidGroups(summary([member(1, prepaidBilling())]));
    expect(groups[0]?.balance).toBe(0);
  });
});
