import type { ReactNode } from 'react';

import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import Zap from 'lucide-react/dist/esm/icons/zap';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { PageHeader } from '@/components/ui/page-header';
import { useCollectives } from '@/hooks/use-collectives';

/**
 * Collectives landing page (`/collectives`).
 *
 * Introduces the feature and surfaces a few active collectives. A collective
 * is a user-owned grouping of endpoints — see `lib/collectives-api.ts`.
 */
export default function CollectivesPage() {
  const { data: collectives, isLoading } = useCollectives();

  // Feature verified collectives first, then fall back to the newest few.
  const featured = [...(collectives ?? [])]
    .toSorted((a, b) => Number(b.verified) - Number(a.verified))
    .slice(0, 3);

  let featuredView: ReactNode;
  if (isLoading) {
    featuredView = (
      <div className='flex justify-center py-12'>
        <LoadingSpinner />
      </div>
    );
  } else if (featured.length > 0) {
    featuredView = (
      <div className='grid grid-cols-1 gap-6 md:grid-cols-3'>
        {featured.map((collective) => (
          <Link key={collective.id} to={`/c/${collective.slug}`}>
            <Card className='hover:border-primary/30 h-full p-5 transition-all hover:shadow-lg'>
              <div className='mb-3 flex items-start gap-3'>
                {collective.icon_url ? (
                  <img
                    src={collective.icon_url}
                    alt={collective.name}
                    className='h-12 w-12 rounded-lg object-cover'
                  />
                ) : (
                  <div className='from-primary/20 to-primary/10 flex h-12 w-12 items-center justify-center rounded-lg bg-gradient-to-br'>
                    <Users className='text-primary h-6 w-6' />
                  </div>
                )}
                <div className='min-w-0 flex-1'>
                  <div className='flex items-center gap-1.5'>
                    <h3 className='truncate text-sm font-semibold'>{collective.name}</h3>
                    {collective.verified && (
                      <CheckCircle className='h-4 w-4 shrink-0 text-green-500' />
                    )}
                  </div>
                  <p className='text-muted-foreground mt-0.5 text-xs'>
                    {collective.member_count}{' '}
                    {collective.member_count === 1 ? 'endpoint' : 'endpoints'}
                  </p>
                </div>
              </div>
              <p className='text-muted-foreground mb-3 line-clamp-2 text-sm'>
                {collective.description || 'No description provided.'}
              </p>
              <div className='flex flex-wrap gap-2'>
                {collective.tags.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant='secondary' className='text-xs'>
                    {tag}
                  </Badge>
                ))}
              </div>
            </Card>
          </Link>
        ))}
      </div>
    );
  } else {
    featuredView = (
      <Card className='text-muted-foreground p-8 text-center text-sm'>
        No collectives yet — be the first to create one.
      </Card>
    );
  }

  return (
    <>
      <PageHeader title='Collectives' path='~/collectives' />

      <div className='mx-auto max-w-6xl px-6 py-6'>
        {/* Hero */}
        <div className='mb-12'>
          <p className='text-muted-foreground mb-6 text-lg'>
            Trusted groups of endpoints. Better discovery, shared identity, collective leverage.
          </p>
          <Button asChild size='lg' className='px-8'>
            <Link to='/collectives/browse'>Browse Collectives</Link>
          </Button>
        </div>

        {/* Active collectives */}
        <div className='mb-12'>
          <div className='mb-6 flex items-center justify-between'>
            <h2 className='text-lg font-semibold'>Active Collectives</h2>
            <Link
              to='/collectives/browse'
              className='text-muted-foreground hover:text-primary text-sm transition-colors'
            >
              View all →
            </Link>
          </div>

          {featuredView}
        </div>

        {/* Benefits */}
        <div className='bg-muted/30 mb-12 rounded-xl p-8'>
          <div className='grid gap-8 md:grid-cols-2'>
            <div>
              <h3 className='text-muted-foreground mb-4 text-sm font-semibold tracking-wide uppercase'>
                For Data Buyers
              </h3>
              <ul className='space-y-3'>
                <li className='flex gap-3'>
                  <CheckCircle className='mt-0.5 h-4 w-4 shrink-0 text-green-500' />
                  <span className='text-sm'>
                    Discover related endpoints grouped under one trusted identity
                  </span>
                </li>
                <li className='flex gap-3'>
                  <Shield className='mt-0.5 h-4 w-4 shrink-0 text-blue-500' />
                  <span className='text-sm'>
                    Verified collectives signal consistent quality across endpoints
                  </span>
                </li>
              </ul>
            </div>
            <div>
              <h3 className='text-muted-foreground mb-4 text-sm font-semibold tracking-wide uppercase'>
                For Data Owners
              </h3>
              <ul className='space-y-3'>
                <li className='flex gap-3'>
                  <Users className='mt-0.5 h-4 w-4 shrink-0 text-purple-500' />
                  <span className='text-sm'>
                    Get discovered through a collective rather than going it alone
                  </span>
                </li>
                <li className='flex gap-3'>
                  <Zap className='mt-0.5 h-4 w-4 shrink-0 text-yellow-500' />
                  <span className='text-sm'>
                    Pool endpoints into a shared, recognizable group identity
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Create CTA */}
        <div className='border-t py-12 text-center'>
          <h3 className='mb-3 text-lg font-semibold'>Curating a set of related endpoints?</h3>
          <p className='text-muted-foreground mx-auto mb-6 max-w-xl text-sm'>
            Create a collective to group your endpoints — and others' — under one identity that data
            buyers can discover and trust.
          </p>
          <Button asChild variant='outline' size='lg'>
            <Link to='/collectives/create'>Create Collective</Link>
          </Button>
        </div>
      </div>
    </>
  );
}
