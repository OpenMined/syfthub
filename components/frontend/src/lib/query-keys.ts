export const endpointKeys = {
  all: ['endpoints'] as const,
  public: (limit: number) => [...endpointKeys.all, 'public', limit] as const,
  publicPaginated: (page: number, limit: number, endpointType?: string, search?: string) =>
    [
      ...endpointKeys.all,
      'public',
      'paginated',
      page,
      limit,
      endpointType ?? 'all',
      search ?? ''
    ] as const,
  publicGrouped: (maxPerOwner: number) =>
    [...endpointKeys.all, 'public', 'grouped', maxPerOwner] as const,
  trending: (limit: number) => [...endpointKeys.all, 'trending', limit] as const,
  count: () => [...endpointKeys.all, 'count'] as const,
  byPath: (path: string) => [...endpointKeys.all, 'byPath', path] as const,
  byOwner: (owner: string) => [...endpointKeys.all, 'byOwner', owner] as const,
  myEndpoints: (username: string) => [...endpointKeys.all, 'mine', username] as const,
  uptime: (owner: string, slug: string, windowHours: number) =>
    [...endpointKeys.all, 'uptime', owner, slug, windowHours] as const
};

export const userKeys = {
  all: ['users'] as const,
  publicProfile: (username: string) => [...userKeys.all, 'public', username] as const
};

export const modelKeys = {
  all: ['models'] as const,
  chat: (limit: number, isAuthenticated: boolean) =>
    [...modelKeys.all, 'chat', limit, isAuthenticated] as const
};

export const dataSourceKeys = {
  all: ['dataSources'] as const,
  chat: (limit: number, isAuthenticated: boolean) =>
    [...dataSourceKeys.all, 'chat', limit, isAuthenticated] as const
};

export const walletKeys = {
  all: ['wallet'] as const,
  info: () => [...walletKeys.all, 'info'] as const,
  balance: () => [...walletKeys.all, 'balance'] as const,
  transactions: () => [...walletKeys.all, 'transactions'] as const,
  subscriptions: () => [...walletKeys.all, 'subscriptions'] as const,
  subscriptionBalance: (creditsUrl: string) =>
    [...walletKeys.all, 'subscriptions', 'balance', creditsUrl] as const
};

export const collectiveKeys = {
  all: ['collectives'] as const,
  list: (ownerId?: number) => [...collectiveKeys.all, 'list', ownerId ?? 'all'] as const,
  paginated: (page: number, limit: number, search?: string) =>
    [...collectiveKeys.all, 'list', 'paginated', page, limit, search ?? ''] as const,
  detail: (slug: string) => [...collectiveKeys.all, 'detail', slug] as const,
  membersByCollective: (collectiveId: number) =>
    [...collectiveKeys.all, 'members', collectiveId] as const,
  members: (collectiveId: number, status?: string) =>
    [...collectiveKeys.all, 'members', collectiveId, status ?? 'all'] as const,
  invitation: (collectiveId: number, endpointId: number) =>
    [...collectiveKeys.all, 'invitation', collectiveId, endpointId] as const,
  byEndpoint: (owner: string, slug: string) =>
    [...collectiveKeys.all, 'byEndpoint', owner, slug] as const
};
