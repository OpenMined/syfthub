import type { Collective } from '@/lib/collectives-api';

/** API-shaped collectives for browse/landing when the backend has no data yet. */
export const mockApiCollectives: Collective[] = [
  {
    id: 1,
    owner_id: 101,
    name: 'Harvard Medical Collective',
    slug: 'harvard-medical',
    shared_endpoint_path: 'collective/harvard-medical',
    description:
      'Medical research institutions sharing genomic, clinical, and pharmaceutical datasets.',
    about:
      '## Harvard Medical Collective\n\nA verified grouping of hospital and lab endpoints for healthcare AI.',
    auto_approve: false,
    icon_url: 'https://ui-avatars.com/api/?name=Harvard+Medical&background=a51c30&color=fff',
    tags: ['healthcare', 'genomics', 'clinical-research', 'verified'],
    verified: true,
    member_count: 3,
    owner_count: 2,
    created_at: '2024-01-15T00:00:00.000Z',
    updated_at: '2025-01-10T00:00:00.000Z'
  },
  {
    id: 2,
    owner_id: 103,
    name: 'Climate Data Alliance',
    slug: 'climate-alliance',
    shared_endpoint_path: 'collective/climate-alliance',
    description: 'Environmental monitoring, satellite operators, and climate scientists.',
    about: 'Real-time Earth observation data with open and prepaid bulk tiers.',
    auto_approve: true,
    icon_url: 'https://ui-avatars.com/api/?name=Climate&background=059669&color=fff',
    tags: ['climate', 'environment', 'open-data', 'satellite'],
    verified: true,
    member_count: 2,
    owner_count: 1,
    created_at: '2024-03-01T00:00:00.000Z',
    updated_at: '2025-02-01T00:00:00.000Z'
  },
  {
    id: 3,
    owner_id: 104,
    name: 'FinTech Data Consortium',
    slug: 'fintech-consortium',
    shared_endpoint_path: 'collective/fintech-consortium',
    description: 'Secure marketplace for financial institutions — risk models and market data.',
    about: 'Invite-only collective with prepaid enterprise endpoints.',
    auto_approve: false,
    icon_url: 'https://ui-avatars.com/api/?name=FinTech&background=7c3aed&color=fff',
    tags: ['finance', 'risk-management', 'compliance', 'enterprise', 'prepaid'],
    verified: true,
    member_count: 1,
    owner_count: 1,
    created_at: '2024-04-01T00:00:00.000Z',
    updated_at: '2025-03-01T00:00:00.000Z'
  },
  {
    id: 4,
    owner_id: 107,
    name: 'Open Science Initiative',
    slug: 'open-science',
    shared_endpoint_path: 'collective/open-science',
    description: 'Community-driven research data and reproducible experiments.',
    about: 'Free and open endpoints across disciplines.',
    auto_approve: true,
    icon_url: 'https://ui-avatars.com/api/?name=Open+Science&background=f59e0b&color=fff',
    tags: ['open-science', 'research', 'academic', 'free'],
    verified: false,
    member_count: 1,
    owner_count: 1,
    created_at: '2024-05-01T00:00:00.000Z',
    updated_at: '2025-01-20T00:00:00.000Z'
  },
  {
    id: 5,
    owner_id: 105,
    name: 'Legal AI Publishers',
    slug: 'legal-ai-publishers',
    shared_endpoint_path: 'collective/legal-ai-publishers',
    description: 'Legal-tech models and document corpora with prepaid enterprise bundles.',
    about: 'Endpoints in this collective typically require **prepaid credits** (Xendit).',
    auto_approve: false,
    icon_url: 'https://ui-avatars.com/api/?name=Legal+AI&background=4f46e5&color=fff',
    tags: ['legal', 'nlp', 'prepaid', 'enterprise'],
    verified: true,
    member_count: 2,
    owner_count: 2,
    created_at: '2024-08-01T00:00:00.000Z',
    updated_at: '2025-04-01T00:00:00.000Z'
  },
  {
    id: 6,
    owner_id: 106,
    name: 'Pharma Research Network',
    slug: 'pharma-research',
    shared_endpoint_path: 'collective/pharma-research',
    description: 'Pharmaceutical trial data and chemistry sources for R&D teams.',
    about: 'Mix of open summaries and prepaid full-trial document access.',
    auto_approve: false,
    icon_url: 'https://ui-avatars.com/api/?name=Pharma&background=dc2626&color=fff',
    tags: ['pharma', 'clinical', 'prepaid'],
    verified: false,
    member_count: 1,
    owner_count: 1,
    created_at: '2024-09-10T00:00:00.000Z',
    updated_at: '2025-04-15T00:00:00.000Z'
  }
];

export function getMockApiCollectiveBySlug(slug: string): Collective | undefined {
  return mockApiCollectives.find((c) => c.slug === slug);
}
