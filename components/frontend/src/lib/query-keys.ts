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
  byPath: (path: string) => [...endpointKeys.all, 'byPath', path] as const
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
  transactions: () => [...walletKeys.all, 'transactions'] as const
};
