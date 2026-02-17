import type { EndpointType } from '@/lib/types';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Calendar from 'lucide-react/dist/esm/icons/calendar';
import Package from 'lucide-react/dist/esm/icons/package';
import Star from 'lucide-react/dist/esm/icons/star';
import Users from 'lucide-react/dist/esm/icons/users';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { ConnectionCard } from '@/components/connection-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useEndpointByPath } from '@/hooks/use-endpoint-queries';

import { AccessPoliciesCard } from './access-policies-card';

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
      return 'bg-muted text-foreground border-border';
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
    case 'model_data_source': {
      return 'bg-blue-100 text-blue-800 border-blue-200 hover:bg-blue-200';
    }
    default: {
      return 'bg-muted text-foreground border-border';
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
    case 'model_data_source': {
      return 'Model + Data Source';
    }
    default: {
      return type;
    }
  }
}

interface EndpointDetailProperties {
  slug: string;
  owner?: string | null;
  onBack: () => void;
}

export function EndpointDetail({ slug, owner, onBack }: Readonly<EndpointDetailProperties>) {
  const path = owner ? `${owner}/${slug}` : undefined;
  const { data: fetchedEndpoint, isLoading, error: queryError } = useEndpointByPath(path);

  // Derive endpoint with full_path set
  const endpoint = fetchedEndpoint
    ? {
        ...fetchedEndpoint,
        full_path: `${fetchedEndpoint.owner_username ?? owner ?? 'anonymous'}/${slug}`
      }
    : null;
  const error = queryError
    ? queryError.message
    : !isLoading && !endpoint
      ? 'Endpoint not found'
      : null;

  if (isLoading) {
    return (
      <div className='bg-background min-h-screen p-8'>
        <div className='flex items-center justify-center py-12'>
          <div className='text-muted-foreground flex items-center gap-3'>
            <div className='border-border border-t-secondary h-6 w-6 animate-spin rounded-full border-2'></div>
            <span className='font-inter'>Loading endpoint…</span>
          </div>
        </div>
      </div>
    );
  }

  if (error || !endpoint) {
    return (
      <div className='bg-background min-h-screen p-8'>
        <div className='mx-auto max-w-4xl'>
          <Button variant='ghost' onClick={onBack} className='mb-4 flex items-center gap-2'>
            <ArrowLeft className='h-4 w-4' aria-hidden='true' />
            Back
          </Button>
          <div className='py-12 text-center'>
            <h2 className='font-rubik text-foreground mb-2 text-xl font-medium'>
              {error ?? 'Endpoint not found'}
            </h2>
            <p className='font-inter text-muted-foreground'>
              The endpoint with slug "{slug}" could not be found.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className='bg-background min-h-screen'>
      {/* Header */}
      <div className='border-border bg-card border-b'>
        <div className='mx-auto max-w-5xl px-6 py-4'>
          <Button
            variant='ghost'
            onClick={onBack}
            className='text-muted-foreground hover:text-foreground mb-4 flex items-center gap-2'
          >
            <ArrowLeft className='h-4 w-4' aria-hidden='true' />
            Back to endpoints
          </Button>

          <div className='flex items-start justify-between'>
            <div>
              <h1 className='font-rubik text-foreground mb-2 text-3xl font-medium'>
                {endpoint.name}
              </h1>
              <p className='font-inter text-muted-foreground mb-4 text-lg'>
                {endpoint.description}
              </p>

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
            <div className='border-border bg-card rounded-xl border p-6'>
              <div className='prose prose-sm text-muted-foreground max-w-none'>
                {endpoint.readme ? (
                  <Markdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => (
                        <h1 className='font-rubik text-foreground mt-6 mb-4 text-2xl font-medium'>
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className='font-rubik text-foreground mt-5 mb-3 text-xl font-medium'>
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className='font-rubik text-foreground mt-4 mb-2 text-lg font-medium'>
                          {children}
                        </h3>
                      ),
                      h4: ({ children }) => (
                        <h4 className='font-rubik text-foreground mt-3 mb-2 text-base font-medium'>
                          {children}
                        </h4>
                      ),
                      p: ({ children }) => (
                        <p className='font-inter text-muted-foreground mb-3'>{children}</p>
                      ),
                      ul: ({ children }) => (
                        <ul className='mb-3 list-disc space-y-1 pl-5'>{children}</ul>
                      ),
                      ol: ({ children }) => (
                        <ol className='mb-3 list-decimal space-y-1 pl-5'>{children}</ol>
                      ),
                      li: ({ children }) => (
                        <li className='font-inter text-muted-foreground'>{children}</li>
                      ),
                      code: ({ className, children }) => {
                        const isInline = !className;
                        return isInline ? (
                          <code className='bg-muted text-foreground rounded-lg px-1.5 py-0.5 font-mono text-sm'>
                            {children}
                          </code>
                        ) : (
                          <code className='block'>{children}</code>
                        );
                      },
                      pre: ({ children }) => (
                        <pre className='bg-muted mb-3 overflow-x-auto rounded-lg p-3 text-xs'>
                          {children}
                        </pre>
                      ),
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          className='text-secondary hover:text-foreground hover:underline'
                          target='_blank'
                          rel='noopener noreferrer'
                        >
                          {children}
                        </a>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className='border-border text-muted-foreground my-3 border-l-4 pl-4 italic'>
                          {children}
                        </blockquote>
                      ),
                      hr: () => <hr className='border-border my-4' />,
                      table: ({ children }) => (
                        <div className='my-4 overflow-x-auto'>
                          <table className='divide-border border-border min-w-full divide-y border'>
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => <thead className='bg-muted'>{children}</thead>,
                      tbody: ({ children }) => (
                        <tbody className='divide-border bg-card divide-y'>{children}</tbody>
                      ),
                      tr: ({ children }) => <tr>{children}</tr>,
                      th: ({ children }) => (
                        <th className='font-inter text-foreground px-4 py-2 text-left text-xs font-semibold'>
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className='font-inter text-muted-foreground px-4 py-2 text-sm'>
                          {children}
                        </td>
                      )
                    }}
                  >
                    {endpoint.readme}
                  </Markdown>
                ) : (
                  <p className='font-inter text-muted-foreground italic'>
                    No documentation available for this endpoint.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className='space-y-6'>
            {/* Info Card */}
            <div className='border-border bg-card rounded-xl border p-6'>
              <h3 className='font-rubik text-foreground mb-4 text-sm font-medium'>About</h3>
              <div className='space-y-4'>
                <div>
                  <p className='font-inter text-muted-foreground mb-1 text-xs'>Owner</p>
                  <div className='flex items-center gap-2'>
                    <div className='from-secondary to-chart-3 h-6 w-6 rounded-full bg-gradient-to-br'></div>
                    <span className='font-inter text-foreground text-sm font-medium'>
                      @{endpoint.owner_username ?? 'anonymous'}
                    </span>
                  </div>
                </div>

                <div>
                  <p className='font-inter text-muted-foreground mb-1 text-xs'>Endpoint Type</p>
                  <Badge className={`border ${getTypeStyles(endpoint.type)}`}>
                    {getTypeLabel(endpoint.type)}
                  </Badge>
                </div>

                {endpoint.tags.length > 0 ? (
                  <div>
                    <p className='font-inter text-muted-foreground mb-1 text-xs'>Tags</p>
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
                  <p className='font-inter text-muted-foreground mb-1 text-xs'>Contributors</p>
                  <div className='flex items-center gap-1'>
                    <Users className='text-muted-foreground h-4 w-4' />
                    <span className='font-inter text-foreground text-sm'>
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
