/**
 * Mock data for Collectives UI prototype
 * This file contains hardcoded data to visualize the collectives feature
 */

export interface CollectivePricingTier {
  id: string;
  name: string;
  description: string;
  price: number;
  unit: 'per-call' | 'per-token' | 'per-month';
  isDefault?: boolean;
}

export interface CollectiveMember {
  id: string;
  userId: string;
  username: string;
  displayName: string;
  avatarUrl?: string;
  role: 'owner' | 'admin' | 'member';
  joinedAt: string;
  endpointCount: number;
  contribution?: number; // Revenue contribution
}

export interface CollectiveEndpoint {
  id: string;
  name: string;
  slug: string;
  owner: string;
  description: string;
  type: 'dataset' | 'model' | 'api';
  usesCollectivePricing: boolean;
  queryCount: number;
  revenue: number;
}

export interface JoinRequest {
  id: string;
  userId: string;
  username: string;
  displayName: string;
  avatarUrl?: string;
  message: string;
  requestedAt: string;
  institution?: string;
}

export interface CollectivePolicy {
  id: string;
  name: string;
  type: 'pricing' | 'access' | 'usage';
  description: string;
  adoptionCount: number;
  config: any;
}

// User's collective membership
export interface UserCollectiveMembership {
  collective: {
    id: string;
    name: string;
    slug: string;
    verified: boolean;
  };
  role: 'owner' | 'admin' | 'member';
  joinedAt: string;
}

export interface Collective {
  id: string;
  name: string;
  slug: string;
  description: string;
  avatarUrl?: string;
  bannerUrl?: string;
  domain?: string;
  isVerified: boolean;
  verified?: boolean; // Alias for isVerified for compatibility
  membershipVisibility: 'open' | 'invite-only' | 'request';
  governance?: 'democratic' | 'representative' | 'corporate';
  hasLegalEntity?: boolean;
  hasInsurance?: boolean;
  established?: string;
  capabilities: {
    unifiedEndpoint: boolean;
    sharedPricing: boolean;
    memberHosting: boolean;
    collectivePolicies: boolean;
    memberVetting: boolean;
  };
  stats: {
    memberCount: number;
    endpointCount: number;
    monthlyQueries: number;
    monthlyRevenue: number;
    trustScore: number;
  };
  pricingTiers: CollectivePricingTier[];
  members: CollectiveMember[];
  endpoints: CollectiveEndpoint[];
  pendingRequests: JoinRequest[];
  policies: CollectivePolicy[];
  createdAt: string;
  tags: string[];
}

// Mock data for Harvard Medical Collective
const harvardMedical: Collective = {
  id: 'collective-1',
  name: 'Harvard Medical Collective',
  slug: 'harvard-medical',
  description: 'Leading medical research institutions sharing genomic, clinical, and pharmaceutical datasets for advancing healthcare AI.',
  avatarUrl: 'https://ui-avatars.com/api/?name=Harvard+Medical&background=a51c30&color=fff',
  bannerUrl: 'https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=1600&h=400&fit=crop',
  domain: 'harvard.syfthub.ai',
  isVerified: true,
  verified: true,
  governance: 'democratic',
  hasLegalEntity: true,
  hasInsurance: true,
  established: '2020-03-15',
  membershipVisibility: 'request',
  capabilities: {
    unifiedEndpoint: true,
    sharedPricing: true,
    memberHosting: true,
    collectivePolicies: true,
    memberVetting: true,
  },
  stats: {
    memberCount: 127,
    endpointCount: 89,
    monthlyQueries: 450000,
    monthlyRevenue: 45000,
    trustScore: 98,
  },
  pricingTiers: [
    {
      id: 'hm-free',
      name: 'Research',
      description: 'For academic research and education',
      price: 0,
      unit: 'per-month',
    },
    {
      id: 'hm-basic',
      name: 'Clinical',
      description: 'For healthcare providers and clinics',
      price: 0.001,
      unit: 'per-call',
      isDefault: true,
    },
    {
      id: 'hm-premium',
      name: 'Enterprise',
      description: 'For pharmaceutical companies and large institutions',
      price: 0.01,
      unit: 'per-call',
    },
  ],
  members: [
    {
      id: 'member-1',
      userId: 'user-1',
      username: 'dr-sarah-chen',
      displayName: 'Dr. Sarah Chen',
      avatarUrl: 'https://ui-avatars.com/api/?name=Sarah+Chen&background=4f46e5&color=fff',
      role: 'owner',
      joinedAt: '2024-01-15',
      endpointCount: 5,
      contribution: 12000,
    },
    {
      id: 'member-2',
      userId: 'user-2',
      username: 'mass-general',
      displayName: 'Mass General Hospital',
      avatarUrl: 'https://ui-avatars.com/api/?name=MGH&background=059669&color=fff',
      role: 'admin',
      joinedAt: '2024-02-01',
      endpointCount: 12,
      contribution: 8500,
    },
    {
      id: 'member-3',
      userId: 'user-3',
      username: 'broad-institute',
      displayName: 'Broad Institute',
      avatarUrl: 'https://ui-avatars.com/api/?name=Broad&background=dc2626&color=fff',
      role: 'admin',
      joinedAt: '2024-02-10',
      endpointCount: 8,
      contribution: 7200,
    },
    {
      id: 'member-4',
      userId: 'user-4',
      username: 'dana-farber',
      displayName: 'Dana-Farber Cancer Institute',
      role: 'member',
      joinedAt: '2024-03-01',
      endpointCount: 6,
      contribution: 5400,
    },
  ],
  endpoints: [
    {
      id: 'endpoint-1',
      name: 'Cancer Genomics Database',
      slug: 'cancer-genomics',
      owner: 'dr-sarah-chen',
      description: 'Comprehensive genomic profiles of 10,000+ cancer patients',
      type: 'dataset',
      usesCollectivePricing: true,
      queryCount: 45000,
      revenue: 4500,
    },
    {
      id: 'endpoint-2',
      name: 'Clinical Trial Outcomes',
      slug: 'clinical-trials',
      owner: 'mass-general',
      description: 'Anonymized outcomes from Phase III clinical trials',
      type: 'dataset',
      usesCollectivePricing: true,
      queryCount: 32000,
      revenue: 3200,
    },
    {
      id: 'endpoint-3',
      name: 'Drug Interaction Predictor',
      slug: 'drug-interactions',
      owner: 'broad-institute',
      description: 'ML model for predicting drug-drug interactions',
      type: 'model',
      usesCollectivePricing: false,
      queryCount: 28000,
      revenue: 5600,
    },
  ],
  pendingRequests: [
    {
      id: 'request-1',
      userId: 'user-10',
      username: 'yale-medical',
      displayName: 'Yale Medical School',
      avatarUrl: 'https://ui-avatars.com/api/?name=Yale&background=00356b&color=fff',
      message: 'We would like to contribute our neuroscience datasets and collaborate on brain research initiatives.',
      requestedAt: '2024-11-20T10:30:00Z',
      institution: 'Yale University',
    },
    {
      id: 'request-2',
      userId: 'user-11',
      username: 'stanford-bio',
      displayName: 'Stanford Bioengineering',
      message: 'Interested in sharing our synthetic biology models and accessing clinical data for validation.',
      requestedAt: '2024-11-19T14:45:00Z',
      institution: 'Stanford University',
    },
  ],
  policies: [
    {
      id: 'policy-1',
      name: 'Academic Discount',
      type: 'pricing',
      description: 'Free access for verified academic institutions',
      adoptionCount: 45,
      config: { discount: 100, verificationRequired: true },
    },
    {
      id: 'policy-2',
      name: 'HIPAA Compliance',
      type: 'access',
      description: 'Enforces HIPAA-compliant data handling',
      adoptionCount: 67,
      config: { encryption: 'AES-256', auditLog: true },
    },
  ],
  createdAt: '2024-01-15',
  tags: ['healthcare', 'genomics', 'clinical-research', 'verified'],
};

// Mock data for Climate Data Alliance
const climateAlliance: Collective = {
  id: 'collective-2',
  name: 'Climate Data Alliance',
  slug: 'climate-alliance',
  description: 'Global network of environmental monitoring stations, satellite operators, and climate scientists sharing real-time Earth observation data.',
  avatarUrl: 'https://ui-avatars.com/api/?name=Climate&background=059669&color=fff',
  bannerUrl: 'https://images.unsplash.com/photo-1569163139394-de4798aa62b6?w=1600&h=400&fit=crop',
  domain: 'climate.syfthub.ai',
  isVerified: true,
  verified: true,
  governance: 'representative',
  hasLegalEntity: true,
  hasInsurance: false,
  established: '2021-06-01',
  membershipVisibility: 'open',
  capabilities: {
    unifiedEndpoint: true,
    sharedPricing: true,
    memberHosting: false,
    collectivePolicies: true,
    memberVetting: false,
  },
  stats: {
    memberCount: 234,
    endpointCount: 156,
    monthlyQueries: 780000,
    monthlyRevenue: 23000,
    trustScore: 95,
  },
  pricingTiers: [
    {
      id: 'ca-free',
      name: 'Public Good',
      description: 'Free for NGOs and educational use',
      price: 0,
      unit: 'per-month',
      isDefault: true,
    },
    {
      id: 'ca-commercial',
      name: 'Commercial',
      description: 'For business and commercial applications',
      price: 0.0005,
      unit: 'per-call',
    },
  ],
  members: [
    {
      id: 'member-5',
      userId: 'user-5',
      username: 'noaa-satellite',
      displayName: 'NOAA Satellite Division',
      avatarUrl: 'https://ui-avatars.com/api/?name=NOAA&background=0891b2&color=fff',
      role: 'owner',
      joinedAt: '2024-03-01',
      endpointCount: 15,
      contribution: 8000,
    },
    {
      id: 'member-6',
      userId: 'user-6',
      username: 'esa-copernicus',
      displayName: 'ESA Copernicus',
      role: 'admin',
      joinedAt: '2024-03-15',
      endpointCount: 12,
      contribution: 5500,
    },
  ],
  endpoints: [
    {
      id: 'endpoint-4',
      name: 'Global Weather Stations',
      slug: 'weather-stations',
      owner: 'noaa-satellite',
      description: 'Real-time data from 10,000+ weather stations worldwide',
      type: 'api',
      usesCollectivePricing: true,
      queryCount: 125000,
      revenue: 6250,
    },
    {
      id: 'endpoint-5',
      name: 'Satellite Imagery Archive',
      slug: 'satellite-imagery',
      owner: 'esa-copernicus',
      description: 'High-resolution Earth observation imagery',
      type: 'dataset',
      usesCollectivePricing: true,
      queryCount: 89000,
      revenue: 4450,
    },
  ],
  pendingRequests: [],
  policies: [
    {
      id: 'policy-3',
      name: 'Open Data License',
      type: 'access',
      description: 'CC BY 4.0 for all public datasets',
      adoptionCount: 134,
      config: { license: 'CC-BY-4.0' },
    },
  ],
  createdAt: '2024-03-01',
  tags: ['climate', 'environment', 'open-data', 'satellite'],
};

// Mock data for FinTech Consortium
const fintechConsortium: Collective = {
  id: 'collective-3',
  name: 'FinTech Data Consortium',
  slug: 'fintech-consortium',
  description: 'Secure marketplace for financial institutions to share market data, risk models, and compliance tools while maintaining regulatory standards.',
  avatarUrl: 'https://ui-avatars.com/api/?name=FinTech&background=7c3aed&color=fff',
  bannerUrl: 'https://images.unsplash.com/photo-1639762681485-074b7f938ba0?w=1600&h=400&fit=crop',
  isVerified: true,
  verified: true,
  governance: 'corporate',
  hasLegalEntity: true,
  hasInsurance: true,
  established: '2019-11-10',
  membershipVisibility: 'invite-only',
  capabilities: {
    unifiedEndpoint: true,
    sharedPricing: true,
    memberHosting: true,
    collectivePolicies: true,
    memberVetting: true,
  },
  stats: {
    memberCount: 67,
    endpointCount: 45,
    monthlyQueries: 320000,
    monthlyRevenue: 89000,
    trustScore: 99,
  },
  pricingTiers: [
    {
      id: 'ft-standard',
      name: 'Standard',
      description: 'Real-time market data access',
      price: 0.01,
      unit: 'per-call',
    },
    {
      id: 'ft-premium',
      name: 'Premium',
      description: 'Including predictive models and analytics',
      price: 0.05,
      unit: 'per-call',
      isDefault: true,
    },
    {
      id: 'ft-enterprise',
      name: 'Enterprise',
      description: 'Unlimited access with SLA guarantees',
      price: 50000,
      unit: 'per-month',
    },
  ],
  members: [
    {
      id: 'member-7',
      userId: 'user-7',
      username: 'jp-morgan-quant',
      displayName: 'JP Morgan Quantitative Research',
      role: 'owner',
      joinedAt: '2024-04-01',
      endpointCount: 8,
      contribution: 32000,
    },
    {
      id: 'member-8',
      userId: 'user-8',
      username: 'goldman-risk',
      displayName: 'Goldman Sachs Risk Management',
      role: 'admin',
      joinedAt: '2024-04-10',
      endpointCount: 6,
      contribution: 28000,
    },
  ],
  endpoints: [
    {
      id: 'endpoint-6',
      name: 'Credit Risk Scoring Model',
      slug: 'credit-risk',
      owner: 'jp-morgan-quant',
      description: 'Advanced ML model for credit risk assessment',
      type: 'model',
      usesCollectivePricing: true,
      queryCount: 45000,
      revenue: 22500,
    },
  ],
  pendingRequests: [
    {
      id: 'request-3',
      userId: 'user-12',
      username: 'deutsche-bank',
      displayName: 'Deutsche Bank Analytics',
      message: 'Looking to share our European market models and access US market data.',
      requestedAt: '2024-11-21T09:15:00Z',
      institution: 'Deutsche Bank',
    },
  ],
  policies: [
    {
      id: 'policy-4',
      name: 'SOC 2 Compliance',
      type: 'access',
      description: 'Ensures SOC 2 Type II compliance',
      adoptionCount: 45,
      config: { auditFrequency: 'quarterly' },
    },
  ],
  createdAt: '2024-04-01',
  tags: ['finance', 'risk-management', 'compliance', 'enterprise'],
};

// Mock data for Open Science Initiative
const openScience: Collective = {
  id: 'collective-4',
  name: 'Open Science Initiative',
  slug: 'open-science',
  description: 'Community-driven platform for sharing research data, reproducible experiments, and scientific models across all disciplines.',
  avatarUrl: 'https://ui-avatars.com/api/?name=Open+Science&background=f59e0b&color=fff',
  bannerUrl: 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=1600&h=400&fit=crop',
  isVerified: false,
  verified: false,
  governance: 'democratic',
  hasLegalEntity: false,
  hasInsurance: false,
  established: '2022-09-01',
  membershipVisibility: 'open',
  capabilities: {
    unifiedEndpoint: true,
    sharedPricing: false,
    memberHosting: false,
    collectivePolicies: true,
    memberVetting: false,
  },
  stats: {
    memberCount: 456,
    endpointCount: 234,
    monthlyQueries: 120000,
    monthlyRevenue: 0,
    trustScore: 88,
  },
  pricingTiers: [
    {
      id: 'os-free',
      name: 'Open Access',
      description: 'Free forever for everyone',
      price: 0,
      unit: 'per-month',
      isDefault: true,
    },
  ],
  members: [
    {
      id: 'member-9',
      userId: 'user-9',
      username: 'cern-physics',
      displayName: 'CERN Physics Department',
      avatarUrl: 'https://ui-avatars.com/api/?name=CERN&background=0891b2&color=fff',
      role: 'admin',
      joinedAt: '2024-05-01',
      endpointCount: 12,
      contribution: 0,
    },
  ],
  endpoints: [
    {
      id: 'endpoint-7',
      name: 'Particle Collision Data',
      slug: 'particle-collisions',
      owner: 'cern-physics',
      description: 'Large Hadron Collider experimental data',
      type: 'dataset',
      usesCollectivePricing: true,
      queryCount: 34000,
      revenue: 0,
    },
  ],
  pendingRequests: [],
  policies: [
    {
      id: 'policy-5',
      name: 'Open Access',
      type: 'access',
      description: 'All data freely available under CC0',
      adoptionCount: 234,
      config: { license: 'CC0' },
    },
  ],
  createdAt: '2024-05-01',
  tags: ['open-science', 'research', 'academic', 'free'],
};

// Export all collectives
export const mockCollectives: Collective[] = [
  harvardMedical,
  climateAlliance,
  fintechConsortium,
  openScience,
];

// Helper functions for mock data
export const getCollectiveBySlug = (slug: string): Collective | undefined => {
  return mockCollectives.find(c => c.slug === slug);
};

export const getUserCollectives = (userId: string): Collective[] => {
  return mockCollectives.filter(c => 
    c.members.some(m => m.userId === userId)
  );
};

export const getCollectiveStats = () => {
  const totalMembers = mockCollectives.reduce((acc, c) => acc + c.stats.memberCount, 0);
  const totalEndpoints = mockCollectives.reduce((acc, c) => acc + c.stats.endpointCount, 0);
  const totalQueries = mockCollectives.reduce((acc, c) => acc + c.stats.monthlyQueries, 0);
  const totalRevenue = mockCollectives.reduce((acc, c) => acc + c.stats.monthlyRevenue, 0);
  
  return {
    collectiveCount: mockCollectives.length,
    totalMembers,
    totalEndpoints,
    totalQueries,
    totalRevenue,
  };
};

// Mock function to get collective for an endpoint
export const getEndpointCollective = (endpointOwner: string): { name: string; slug: string; isVerified: boolean } | null => {
  // Mock mapping of endpoint owners to collectives
  const ownerToCollective: Record<string, { name: string; slug: string; isVerified: boolean }> = {
    'dr-sarah-chen': { name: 'Harvard Medical', slug: 'harvard-medical', isVerified: true },
    'mass-general': { name: 'Harvard Medical', slug: 'harvard-medical', isVerified: true },
    'broad-institute': { name: 'Harvard Medical', slug: 'harvard-medical', isVerified: true },
    'dana-farber': { name: 'Harvard Medical', slug: 'harvard-medical', isVerified: true },
    'noaa-satellite': { name: 'Climate Alliance', slug: 'climate-alliance', isVerified: true },
    'esa-copernicus': { name: 'Climate Alliance', slug: 'climate-alliance', isVerified: true },
    'cern-physics': { name: 'Open Science', slug: 'open-science', isVerified: false },
  };
  
  return ownerToCollective[endpointOwner] || null;
};

// Mock user's collectives (for logged-in user)
export const currentUserCollectives = [
  {
    collective: harvardMedical,
    role: 'member' as const,
    joinedAt: '2024-06-15',
  },
  {
    collective: openScience,
    role: 'admin' as const,
    joinedAt: '2024-05-20',
  },
];

// Get collectives for a specific username
export const getUserCollectivesByUsername = (username: string): UserCollectiveMembership[] => {
  // Mock mapping of usernames to their collective memberships
  const userCollectivesMap: Record<string, UserCollectiveMembership[]> = {
    'dr-sarah-chen': [
      {
        collective: {
          id: 'collective-1',
          name: 'Harvard Medical',
          slug: 'harvard-medical',
          verified: true,
        },
        role: 'member',
        joinedAt: '2024-03-15',
      }
    ],
    'mass-general': [
      {
        collective: {
          id: 'collective-1', 
          name: 'Harvard Medical',
          slug: 'harvard-medical',
          verified: true,
        },
        role: 'admin',
        joinedAt: '2024-01-10',
      }
    ],
    'noaa-satellite': [
      {
        collective: {
          id: 'collective-2',
          name: 'Climate Alliance',
          slug: 'climate-alliance', 
          verified: true,
        },
        role: 'member',
        joinedAt: '2024-02-20',
      }
    ],
    'cambridge-press-oa': [
      {
        collective: {
          id: 'collective-4',
          name: 'Open Science',
          slug: 'open-science',
          verified: false,
        },
        role: 'member', 
        joinedAt: '2024-04-01',
      },
      {
        collective: {
          id: 'collective-5',
          name: 'Academic Publishers',
          slug: 'academic-publishers',
          verified: true,
        },
        role: 'admin',
        joinedAt: '2023-11-15',
      }
    ],
  };
  
  return userCollectivesMap[username] || [];
};