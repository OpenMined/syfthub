import type { ChatSource, EndpointGroup, Policy } from '@/lib/types';

import { createTransactionPolicy, createXenditPrepaidPolicy, hasPrepaidPolicy } from './policies';

const NOW = Date.now();
const daysAgo = (days: number) =>
  new Date(NOW - days * 24 * 60 * 60 * 1000).toISOString();

type EndpointFields = Pick<
  ChatSource,
  'name' | 'description' | 'type' | 'tags'
> & {
  policies?: Policy[];
  stars_count?: number;
};

function endpoint(owner: string, slug: string, fields: EndpointFields): ChatSource {
  const tags = [...fields.tags];
  if (hasPrepaidPolicy(fields.policies) && !tags.includes('prepaid')) {
    tags.push('prepaid');
  }

  return {
    id: `${owner}/${slug}`,
    slug,
    owner_username: owner,
    full_path: `${owner}/${slug}`,
    status: 'active',
    updated: '3 days ago',
    updated_at: daysAgo(3),
    contributors_count: 1,
    version: '1.0.0',
    readme: `# ${fields.name}\n\nMock endpoint for local UI development.`,
    stars_count: fields.stars_count ?? 0,
    name: fields.name,
    description: fields.description,
    type: fields.type,
    tags,
    policies: fields.policies
  };
}

export const mockEndpoints: ChatSource[] = [
  endpoint('alice-research', 'legal-doc-search', {
    name: 'Legal Document Search',
    description: 'Semantic search over 2M legal filings — prepaid credit bundles for enterprise buyers.',
    type: 'model',
    tags: ['legal', 'nlp', 'enterprise'],
    policies: [
      createXenditPrepaidPolicy('legal-doc-search', {
        description: 'Prepaid legal search credits',
        price: 0.01,
        bundles: [
          { name: 'Starter', amount: 1_000 },
          { name: 'Pro', amount: 5_000 }
        ]
      })
    ]
  }),
  endpoint('bob-datasets', 'pharma-trials-db', {
    name: 'Pharma Trials Database',
    description: 'Anonymized Phase III outcomes — prepaid per document retrieved.',
    type: 'data_source',
    tags: ['pharma', 'clinical', 'healthcare'],
    policies: [
      createXenditPrepaidPolicy('pharma-trials-db', {
        unit: 'document',
        price: 0.05,
        description: 'Prepaid document retrieval credits'
      })
    ]
  }),
  endpoint('jp-morgan-quant', 'credit-risk', {
    name: 'Credit Risk Scoring Model',
    description: 'ML credit risk scores for institutional portfolios.',
    type: 'model',
    tags: ['finance', 'risk', 'prepaid'],
    policies: [
      createXenditPrepaidPolicy('credit-risk', {
        price: 0.05,
        currency: 'USD',
        bundles: [
          { name: 'Desk', amount: 10_000 },
          { name: 'Desk Pro', amount: 50_000 }
        ]
      })
    ]
  }),
  endpoint('dr-sarah-chen', 'cancer-genomics', {
    name: 'Cancer Genomics Database',
    description: 'Genomic profiles for 10,000+ cancer patients — collective shared pricing.',
    type: 'data_source',
    tags: ['genomics', 'oncology'],
    policies: [createTransactionPolicy(0.001, 'per_call')]
  }),
  endpoint('mass-general', 'clinical-trials', {
    name: 'Clinical Trial Outcomes',
    description: 'Phase III trial outcomes from major hospitals.',
    type: 'data_source',
    tags: ['clinical', 'trials'],
    policies: [createTransactionPolicy(0.002, 'per_call')]
  }),
  endpoint('noaa-satellite', 'weather-stations', {
    name: 'Global Weather Stations',
    description: 'Real-time readings from 10,000+ stations — open with optional prepaid bulk access.',
    type: 'data_source',
    tags: ['climate', 'weather', 'open-data'],
    policies: []
  }),
  endpoint('noaa-satellite', 'satellite-imagery', {
    name: 'Satellite Imagery Archive',
    description: 'High-resolution Earth observation tiles — prepaid bulk download bundles.',
    type: 'data_source',
    tags: ['satellite', 'imagery', 'climate'],
    policies: [
      createXenditPrepaidPolicy('satellite-imagery', {
        unit: 'document',
        price: 0.25,
        description: 'Prepaid imagery tile credits'
      })
    ]
  }),
  endpoint('cern-physics', 'particle-collisions', {
    name: 'Particle Collision Data',
    description: 'LHC experimental datasets — free open access.',
    type: 'data_source',
    tags: ['physics', 'open-science'],
    policies: []
  })
];

const endpointsByOwner = mockEndpoints.reduce<Map<string, ChatSource[]>>((map, ep) => {
  const owner = ep.owner_username ?? '';
  const list = map.get(owner) ?? [];
  list.push(ep);
  map.set(owner, list);
  return map;
}, new Map());

export function getMockEndpointsByOwner(username: string): ChatSource[] {
  return endpointsByOwner.get(username.toLowerCase()) ?? [];
}

/** Grouped directory shape for the homepage global directory. */
export function getMockGroupedEndpoints(maxPerOwner = 15): EndpointGroup[] {
  return [...endpointsByOwner.entries()].map(([owner_username, endpoints]) => ({
    owner_username,
    endpoints: endpoints.slice(0, maxPerOwner),
    total_count: endpoints.length,
    has_more: endpoints.length > maxPerOwner
  }));
}

export function getMockEndpointByPath(owner: string, slug: string): ChatSource | undefined {
  return mockEndpoints.find(
    (e) =>
      e.owner_username?.toLowerCase() === owner.toLowerCase() &&
      e.slug.toLowerCase() === slug.toLowerCase()
  );
}
