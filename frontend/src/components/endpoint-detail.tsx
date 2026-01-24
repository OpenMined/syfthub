import React, { memo, useEffect, useState } from 'react';

import type { ChatSource, EndpointType, Policy } from '@/lib/types';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Calendar from 'lucide-react/dist/esm/icons/calendar';
import Coins from 'lucide-react/dist/esm/icons/coins';
import Gauge from 'lucide-react/dist/esm/icons/gauge';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Key from 'lucide-react/dist/esm/icons/key';
import Lock from 'lucide-react/dist/esm/icons/lock';
import MapPin from 'lucide-react/dist/esm/icons/map-pin';
import Package from 'lucide-react/dist/esm/icons/package';
import Shield from 'lucide-react/dist/esm/icons/shield';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Star from 'lucide-react/dist/esm/icons/star';
import Unlock from 'lucide-react/dist/esm/icons/unlock';
import Users from 'lucide-react/dist/esm/icons/users';
import Zap from 'lucide-react/dist/esm/icons/zap';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { getPublicEndpoints } from '@/lib/endpoint-utils';
import { cn } from '@/lib/utils';

import { ConnectionCard } from './connection-card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

// Helper functions moved outside component for consistent-function-scoping
function getStatusBadgeColor(status: 'active' | 'warning' | 'inactive') {
  switch (status) {
    case 'active': {
      return 'bg-green-100 text-green-800 border-green-200 hover:bg-green-200';
    }
    case 'warning': {
      return 'bg-yellow-100 text-yellow-800 border-yellow-200 hover:bg-yellow-200';
    }
    case 'inactive': {
      return 'bg-red-100 text-red-800 border-red-200 hover:bg-red-200';
    }
    default: {
      return 'bg-syft-surface text-syft-primary border-syft-border';
    }
  }
}

function getTypeStyles(type: EndpointType) {
  switch (type) {
    case 'model': {
      return 'bg-purple-100 text-purple-800 border-purple-200 hover:bg-purple-200';
    }
    case 'data_source': {
      return 'bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-200';
    }
    default: {
      return 'bg-syft-surface text-syft-primary border-syft-border';
    }
  }
}

function getTypeLabel(type: EndpointType) {
  switch (type) {
    case 'model': {
      return 'Model';
    }
    case 'data_source': {
      return 'Data Source';
    }
    default: {
      return type;
    }
  }
}

// Policy type configuration for styling and icons
const POLICY_TYPE_CONFIG: Record<
  string,
  {
    icon: React.ElementType;
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
    description: string;
  }
> = {
  // Transaction/Pricing policies
  transaction: {
    icon: Coins,
    label: 'Transaction Policy',
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-200',
    description: 'Pay-per-use pricing for this endpoint'
  },
  // Access control policies
  public: {
    icon: Globe,
    label: 'Public Access',
    color: 'text-sky-600',
    bgColor: 'bg-sky-50',
    borderColor: 'border-sky-200',
    description: 'Anyone can access this endpoint without authentication'
  },
  private: {
    icon: Lock,
    label: 'Private Access',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    description: 'Only the owner can access this endpoint'
  },
  authenticated: {
    icon: Key,
    label: 'Authentication Required',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    description: 'Requires authentication to access'
  },
  internal: {
    icon: Shield,
    label: 'Internal Only',
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
    borderColor: 'border-indigo-200',
    description: 'Only accessible within the organization'
  },
  // Rate limiting and quotas
  rate_limit: {
    icon: Gauge,
    label: 'Rate Limit',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    description: 'Request rate is limited'
  },
  quota: {
    icon: Zap,
    label: 'Usage Quota',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    description: 'Usage quota applies to this endpoint'
  },
  // Geographic restrictions
  geographic: {
    icon: MapPin,
    label: 'Geographic Restriction',
    color: 'text-rose-600',
    bgColor: 'bg-rose-50',
    borderColor: 'border-rose-200',
    description: 'Access restricted by geographic location'
  }
};

const DEFAULT_POLICY_CONFIG = {
  icon: ShieldCheck,
  label: 'Policy',
  color: 'text-slate-600',
  bgColor: 'bg-slate-50',
  borderColor: 'border-slate-200',
  description: 'Custom policy configuration'
};

function getPolicyConfig(type: string) {
  return POLICY_TYPE_CONFIG[type.toLowerCase()] ?? DEFAULT_POLICY_CONFIG;
}

// Helper to format cost values for display
function formatCost(value: number, unit: string): string {
  if (unit === 'token' || unit === 'tokens') {
    // Convert per-token cost to per-million tokens for readability
    const perMillion = value * 1_000_000;
    if (perMillion < 0.01) {
      return `$${(perMillion * 1000).toFixed(2)} / 1B`;
    }
    return `$${perMillion.toFixed(2)} / 1M`;
  }
  if (unit === 'query' || unit === 'queries') {
    // Convert per-query cost to per-thousand queries
    const perThousand = value * 1000;
    return `$${perThousand.toFixed(2)} / 1K`;
  }
  // Default: show as-is with 6 decimal places
  return `$${value.toFixed(6)}`;
}

// Helper to format config key names for display
function formatConfigKey(key: string): string {
  return key
    .replaceAll('_', ' ')
    .replaceAll(/([A-Z])/g, ' $1')
    .replaceAll(/^./g, (firstChar) => firstChar.toUpperCase())
    .trim();
}

// Render config value based on type
// eslint-disable-next-line sonarjs/function-return-type -- Different JSX elements are all valid React.ReactNode
function renderConfigValue(value: unknown, key: string): React.ReactNode {
  if (value === null || value === undefined)
    return <span className='text-syft-placeholder'>—</span>;
  if (typeof value === 'boolean') {
    return value ? (
      <span className='text-emerald-600'>Yes</span>
    ) : (
      <span className='text-syft-placeholder'>No</span>
    );
  }
  if (typeof value === 'number') {
    // Check if it looks like a cost value
    if (key.includes('token') || key.includes('cost')) {
      return <span className='font-mono'>{formatCost(value, 'token')}</span>;
    }
    if (key.includes('query') || key.includes('retrieval')) {
      return <span className='font-mono'>{formatCost(value, 'query')}</span>;
    }
    return <span className='font-mono'>{value.toLocaleString()}</span>;
  }
  if (typeof value === 'string') {
    return <span>{value}</span>;
  }
  // Handle objects, arrays, and any other types via JSON serialization
  return <span className='font-mono text-[10px]'>{JSON.stringify(value)}</span>;
}

// Transaction policy specific renderer - memoized to prevent unnecessary re-renders
const TransactionPolicyContent = memo(function TransactionPolicyContent({
  config
}: Readonly<{ config: Record<string, unknown> }>) {
  const costs = config.costs as Record<string, unknown> | undefined;
  const provider = config.provider as string | undefined;
  const pricingModel = config.pricing_model as string | undefined;
  const billingUnit = config.billing_unit as string | undefined;

  return (
    <div className='mt-3 space-y-2'>
      {/* Provider & Model Info */}
      {provider || pricingModel ? (
        <div className='text-syft-muted flex flex-wrap gap-x-4 gap-y-1 text-xs'>
          {provider ? (
            <span>
              Provider: <span className='text-syft-primary font-medium'>{provider}</span>
            </span>
          ) : null}
          {pricingModel ? (
            <span>
              Model:{' '}
              <span className='text-syft-primary font-medium'>{formatConfigKey(pricingModel)}</span>
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Pricing Table */}
      {costs ? (
        <div className='bg-card/60 rounded-md border border-emerald-200'>
          <div className='border-b border-emerald-100 px-3 py-1.5'>
            <span className='text-[10px] font-semibold tracking-wide text-emerald-700 uppercase'>
              Pricing
            </span>
          </div>
          <div className='divide-y divide-emerald-100'>
            {Object.entries(costs)
              .filter(
                ([key, value]) =>
                  key !== 'currency' && key !== 'retrieval_per_query' && typeof value === 'number'
              )
              .map(([key, value]) => (
                <div key={key} className='flex items-center justify-between px-3 py-1.5'>
                  <span className='text-syft-muted text-xs'>{formatConfigKey(key)}</span>
                  <span className='text-syft-primary font-mono text-xs font-medium'>
                    {formatCost(
                      value as number,
                      key.includes('token') ? (billingUnit ?? 'token') : 'query'
                    )}
                  </span>
                </div>
              ))}
          </div>
        </div>
      ) : null}
    </div>
  );
});

// Generic config renderer for unknown policy types - memoized to prevent unnecessary re-renders
const GenericPolicyContent = memo(function GenericPolicyContent({
  config
}: Readonly<{ config: Record<string, unknown> }>) {
  const entries = Object.entries(config).filter(
    ([, value]) => value !== null && value !== undefined && value !== ''
  );

  if (entries.length === 0) return null;

  return (
    <div className='mt-3'>
      <div className='border-syft-border bg-card/60 rounded-md border'>
        <div className='border-syft-border border-b px-3 py-1.5'>
          <span className='text-syft-muted text-[10px] font-semibold tracking-wide uppercase'>
            Configuration
          </span>
        </div>
        <div className='divide-syft-border divide-y'>
          {entries.map(([key, value]) => (
            <div key={key} className='flex items-center justify-between gap-2 px-3 py-1.5'>
              <span className='text-syft-muted shrink-0 text-xs'>{formatConfigKey(key)}</span>
              <span className='text-syft-primary truncate text-xs'>
                {renderConfigValue(value, key)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});

// Single policy item component - memoized to prevent unnecessary re-renders
const PolicyItem = memo(function PolicyItem({ policy }: Readonly<{ policy: Policy }>) {
  const config = getPolicyConfig(policy.type);
  const Icon = config.icon;
  const isTransaction = policy.type.toLowerCase() === 'transaction';

  // For unknown policy types, use the type as the label
  const displayLabel = POLICY_TYPE_CONFIG[policy.type.toLowerCase()]
    ? config.label
    : formatConfigKey(policy.type);

  return (
    <div
      className={cn(
        'group relative rounded-lg border p-4 transition-colors transition-shadow duration-200',
        config.borderColor,
        config.bgColor,
        policy.enabled ? 'hover:shadow-md hover:shadow-black/5' : 'opacity-60 grayscale-[30%]'
      )}
    >
      <div className='flex items-start gap-3'>
        {/* Icon */}
        <div
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
            config.bgColor,
            'ring-1 ring-inset',
            config.borderColor
          )}
        >
          <Icon className={cn('h-4.5 w-4.5', config.color)} />
        </div>

        {/* Content */}
        <div className='min-w-0 flex-1'>
          <div className='flex items-center justify-between gap-2'>
            <span className={cn('text-sm font-semibold', config.color)}>{displayLabel}</span>
            <Badge
              variant='outline'
              className={cn(
                'shrink-0 text-[10px] font-medium',
                policy.enabled
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-border bg-muted text-muted-foreground'
              )}
            >
              {policy.enabled ? 'Active' : 'Disabled'}
            </Badge>
          </div>
          <p className='text-syft-muted mt-1 text-xs'>{policy.description || config.description}</p>

          {/* Policy-specific content */}
          {isTransaction && Object.keys(policy.config).length > 0 ? (
            <TransactionPolicyContent config={policy.config} />
          ) : (
            Object.keys(policy.config).length > 0 && <GenericPolicyContent config={policy.config} />
          )}

          {policy.version ? (
            <p className='text-syft-placeholder mt-2 text-[10px]'>Version {policy.version}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
});

// Access Policies Card component - memoized to prevent unnecessary re-renders
interface AccessPoliciesCardProperties {
  policies?: Policy[];
}

const AccessPoliciesCard = memo(function AccessPoliciesCard({
  policies
}: Readonly<AccessPoliciesCardProperties>) {
  const validPolicies = policies?.filter((p) => p.type) ?? [];

  return (
    <div className='border-syft-border bg-card rounded-xl border p-6'>
      {/* Header */}
      <div className='mb-4 flex items-center justify-between'>
        <h3 className='font-rubik text-syft-primary text-sm font-medium'>Access Policies</h3>
        {validPolicies.length > 0 ? (
          <span className='bg-syft-surface text-syft-muted rounded-full px-2 py-0.5 text-xs font-medium'>
            {validPolicies.length}
          </span>
        ) : null}
      </div>

      {/* Policies list */}
      {validPolicies.length > 0 ? (
        <div className='space-y-3'>
          {validPolicies.map((policy, index) => (
            <PolicyItem key={`${policy.type}-${String(index)}`} policy={policy} />
          ))}
        </div>
      ) : (
        <div className='border-syft-border rounded-xl border border-dashed py-6 text-center'>
          <Unlock className='text-syft-placeholder mx-auto h-8 w-8' />
          <p className='font-inter text-syft-muted mt-2 text-sm'>No access policies configured</p>
          <p className='font-inter text-syft-placeholder mt-1 text-xs'>
            This endpoint may be publicly accessible
          </p>
        </div>
      )}
    </div>
  );
});

interface EndpointDetailProperties {
  slug: string;
  owner?: string | null;
  onBack: () => void;
}

export function EndpointDetail({ slug, owner, onBack }: Readonly<EndpointDetailProperties>) {
  const [endpoint, setEndpoint] = useState<ChatSource | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadEndpoint = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // Since we don't have a direct endpoint for getting a single public endpoint by slug,
        // we'll fetch all public endpoints and find the one with the matching slug and owner
        // In a real implementation, you'd want a dedicated endpoint like /api/v1/endpoints/public/{owner}/{slug}
        const endpoints = await getPublicEndpoints({ limit: 100 });
        let foundEndpoint = endpoints.find((ds) => {
          // Match by slug and owner if both are provided
          if (owner && ds.owner_username) {
            return ds.slug === slug && ds.owner_username === owner;
          }
          // Fallback to slug-only match
          return ds.slug === slug;
        });

        // Set the full path for display
        if (foundEndpoint) {
          foundEndpoint = {
            ...foundEndpoint,
            full_path: `${foundEndpoint.owner_username ?? owner ?? 'anonymous'}/${slug}`
          };
        }

        if (foundEndpoint) {
          setEndpoint(foundEndpoint);
        } else {
          setError('Endpoint not found');
        }
      } catch (error_) {
        setError(error_ instanceof Error ? error_.message : 'Failed to load endpoint');
      } finally {
        setIsLoading(false);
      }
    };

    void loadEndpoint();
  }, [slug, owner]);

  if (isLoading) {
    return (
      <div className='bg-syft-background min-h-screen p-8'>
        <div className='flex items-center justify-center py-12'>
          <div className='text-syft-muted flex items-center gap-3'>
            <div className='border-syft-border border-t-syft-secondary h-6 w-6 animate-spin rounded-full border-2'></div>
            <span className='font-inter'>Loading endpoint…</span>
          </div>
        </div>
      </div>
    );
  }

  if (error || !endpoint) {
    return (
      <div className='bg-syft-background min-h-screen p-8'>
        <div className='mx-auto max-w-4xl'>
          <Button variant='ghost' onClick={onBack} className='mb-4 flex items-center gap-2'>
            <ArrowLeft className='h-4 w-4' aria-hidden='true' />
            Back
          </Button>
          <div className='py-12 text-center'>
            <h2 className='font-rubik text-syft-primary mb-2 text-xl font-medium'>
              {error ?? 'Endpoint not found'}
            </h2>
            <p className='font-inter text-syft-muted'>
              The endpoint with slug "{slug}" could not be found.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className='bg-syft-background min-h-screen'>
      {/* Header */}
      <div className='border-syft-border bg-card border-b'>
        <div className='mx-auto max-w-5xl px-6 py-4'>
          <Button
            variant='ghost'
            onClick={onBack}
            className='text-syft-muted hover:text-syft-primary mb-4 flex items-center gap-2'
          >
            <ArrowLeft className='h-4 w-4' aria-hidden='true' />
            Back to endpoints
          </Button>

          <div className='flex items-start justify-between'>
            <div>
              <h1 className='font-rubik text-syft-primary mb-2 text-3xl font-medium'>
                {endpoint.name}
              </h1>
              <p className='font-inter text-syft-muted mb-4 text-lg'>{endpoint.description}</p>

              {/* Badges */}
              <div className='mb-4 flex flex-wrap gap-2'>
                <Badge className={`border ${getTypeStyles(endpoint.type)}`}>
                  {getTypeLabel(endpoint.type)}
                </Badge>
                <Badge className={getStatusBadgeColor(endpoint.status)}>
                  {endpoint.status === 'active' && '● Active'}
                  {endpoint.status === 'warning' && '● Needs Update'}
                  {endpoint.status === 'inactive' && '● Inactive'}
                </Badge>
                <Badge variant='outline'>
                  <Package className='mr-1 h-3 w-3' />v{endpoint.version}
                </Badge>
                {endpoint.stars_count > 0 ? (
                  <Badge variant='outline' className='border-yellow-200 text-yellow-600'>
                    <Star className='mr-1 h-3 w-3' />
                    {endpoint.stars_count}
                  </Badge>
                ) : null}
                <Badge variant='outline'>
                  <Calendar className='mr-1 h-3 w-3' />
                  Updated {endpoint.updated}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='grid gap-8 lg:grid-cols-3'>
          {/* Main content */}
          <div className='space-y-6 lg:col-span-2'>
            {/* README Section */}
            <div className='border-syft-border bg-card rounded-xl border p-6'>
              <div className='prose prose-sm text-syft-muted max-w-none'>
                {endpoint.readme ? (
                  <Markdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => (
                        <h1 className='font-rubik text-syft-primary mt-6 mb-4 text-2xl font-medium'>
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className='font-rubik text-syft-primary mt-5 mb-3 text-xl font-medium'>
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className='font-rubik text-syft-primary mt-4 mb-2 text-lg font-medium'>
                          {children}
                        </h3>
                      ),
                      h4: ({ children }) => (
                        <h4 className='font-rubik text-syft-primary mt-3 mb-2 text-base font-medium'>
                          {children}
                        </h4>
                      ),
                      p: ({ children }) => (
                        <p className='font-inter text-syft-muted mb-3'>{children}</p>
                      ),
                      ul: ({ children }) => (
                        <ul className='mb-3 list-disc space-y-1 pl-5'>{children}</ul>
                      ),
                      ol: ({ children }) => (
                        <ol className='mb-3 list-decimal space-y-1 pl-5'>{children}</ol>
                      ),
                      li: ({ children }) => (
                        <li className='font-inter text-syft-muted'>{children}</li>
                      ),
                      code: ({ className, children }) => {
                        const isInline = !className;
                        return isInline ? (
                          <code className='bg-syft-surface text-syft-primary rounded-lg px-1.5 py-0.5 font-mono text-sm'>
                            {children}
                          </code>
                        ) : (
                          <code className='block'>{children}</code>
                        );
                      },
                      pre: ({ children }) => (
                        <pre className='bg-syft-surface mb-3 overflow-x-auto rounded-lg p-3 text-xs'>
                          {children}
                        </pre>
                      ),
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          className='text-syft-secondary hover:text-syft-primary hover:underline'
                          target='_blank'
                          rel='noopener noreferrer'
                        >
                          {children}
                        </a>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className='border-syft-border text-syft-muted my-3 border-l-4 pl-4 italic'>
                          {children}
                        </blockquote>
                      ),
                      hr: () => <hr className='border-syft-border my-4' />,
                      table: ({ children }) => (
                        <div className='my-4 overflow-x-auto'>
                          <table className='divide-syft-border border-syft-border min-w-full divide-y border'>
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className='bg-syft-surface'>{children}</thead>
                      ),
                      tbody: ({ children }) => (
                        <tbody className='divide-syft-border bg-card divide-y'>{children}</tbody>
                      ),
                      tr: ({ children }) => <tr>{children}</tr>,
                      th: ({ children }) => (
                        <th className='font-inter text-syft-primary px-4 py-2 text-left text-xs font-semibold'>
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className='font-inter text-syft-muted px-4 py-2 text-sm'>{children}</td>
                      )
                    }}
                  >
                    {endpoint.readme}
                  </Markdown>
                ) : (
                  <p className='font-inter text-syft-muted italic'>
                    No documentation available for this endpoint.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className='space-y-6'>
            {/* Info Card */}
            <div className='border-syft-border bg-card rounded-xl border p-6'>
              <h3 className='font-rubik text-syft-primary mb-4 text-sm font-medium'>About</h3>
              <div className='space-y-4'>
                <div>
                  <p className='font-inter text-syft-muted mb-1 text-xs'>Owner</p>
                  <div className='flex items-center gap-2'>
                    <div className='from-syft-secondary to-syft-purple h-6 w-6 rounded-full bg-gradient-to-br'></div>
                    <span className='font-inter text-syft-primary text-sm font-medium'>
                      @{endpoint.owner_username ?? 'anonymous'}
                    </span>
                  </div>
                </div>

                <div>
                  <p className='font-inter text-syft-muted mb-1 text-xs'>Endpoint Type</p>
                  <Badge className={`border ${getTypeStyles(endpoint.type)}`}>
                    {getTypeLabel(endpoint.type)}
                  </Badge>
                </div>

                {endpoint.tags.length > 0 ? (
                  <div>
                    <p className='font-inter text-syft-muted mb-1 text-xs'>Tags</p>
                    <div className='flex flex-wrap gap-1'>
                      {endpoint.tags.map((tag) => (
                        <Badge key={tag} variant='outline'>
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div>
                  <p className='font-inter text-syft-muted mb-1 text-xs'>Contributors</p>
                  <div className='flex items-center gap-1'>
                    <Users className='text-syft-placeholder h-4 w-4' />
                    <span className='font-inter text-syft-primary text-sm'>
                      {endpoint.contributors_count} contributor
                      {endpoint.contributors_count === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Connections Card */}
            {endpoint.connections && endpoint.connections.length > 0 ? (
              <ConnectionCard
                connections={endpoint.connections}
                endpointSlug={
                  endpoint.full_path ?? `${endpoint.owner_username ?? 'anonymous'}/${slug}`
                }
              />
            ) : null}

            {/* Access Policies Card */}
            <AccessPoliciesCard policies={endpoint.policies} />
          </div>
        </div>
      </div>
    </div>
  );
}
