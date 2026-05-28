import type { PublicUserProfile } from '@/lib/types';

export interface MockUser extends PublicUserProfile {
  id: number;
}

export const mockUsers: MockUser[] = [
  {
    id: 101,
    username: 'dr-sarah-chen',
    full_name: 'Dr. Sarah Chen',
    avatar_url: 'https://ui-avatars.com/api/?name=Sarah+Chen&background=4f46e5&color=fff',
    role: 'user',
    bio: 'Clinical genomics researcher publishing cancer and trial datasets.',
    domain: 'harvard.edu',
    is_email_public: false,
    created_at: '2023-06-12T10:00:00.000Z'
  },
  {
    id: 102,
    username: 'mass-general',
    full_name: 'Mass General Hospital',
    avatar_url: 'https://ui-avatars.com/api/?name=MGH&background=059669&color=fff',
    role: 'user',
    bio: 'Hospital research group — clinical outcomes and imaging endpoints.',
    is_email_public: false,
    created_at: '2023-08-01T10:00:00.000Z'
  },
  {
    id: 103,
    username: 'noaa-satellite',
    full_name: 'NOAA Satellite Division',
    avatar_url: 'https://ui-avatars.com/api/?name=NOAA&background=0891b2&color=fff',
    role: 'user',
    bio: 'Earth observation and weather data for climate research.',
    is_email_public: false,
    created_at: '2023-09-15T10:00:00.000Z'
  },
  {
    id: 104,
    username: 'jp-morgan-quant',
    full_name: 'JP Morgan Quantitative Research',
    role: 'user',
    bio: 'Risk models and market analytics for enterprise buyers.',
    is_email_public: false,
    created_at: '2024-01-10T10:00:00.000Z'
  },
  {
    id: 105,
    username: 'alice-research',
    full_name: 'Alice Okonkwo',
    avatar_url: 'https://ui-avatars.com/api/?name=Alice+Okonkwo&background=7c3aed&color=fff',
    role: 'user',
    bio: 'Legal-tech datasets with prepaid enterprise access.',
    domain: 'alice-research.example',
    email: 'alice@example.com',
    is_email_public: true,
    created_at: '2024-04-20T10:00:00.000Z'
  },
  {
    id: 106,
    username: 'bob-datasets',
    full_name: 'Bob Tanaka',
    avatar_url: 'https://ui-avatars.com/api/?name=Bob+Tanaka&background=f59e0b&color=fff',
    role: 'user',
    bio: 'Open pharmaceutical and chemistry data sources.',
    is_email_public: false,
    created_at: '2024-05-05T10:00:00.000Z'
  },
  {
    id: 107,
    username: 'cern-physics',
    full_name: 'CERN Physics Department',
    avatar_url: 'https://ui-avatars.com/api/?name=CERN&background=0891b2&color=fff',
    role: 'user',
    bio: 'Particle physics datasets — open access collective member.',
    is_email_public: false,
    created_at: '2024-05-01T10:00:00.000Z'
  }
];

const usersByUsername = new Map(mockUsers.map((u) => [u.username.toLowerCase(), u]));

export function getMockUserByUsername(username: string): MockUser | undefined {
  return usersByUsername.get(username.toLowerCase());
}
