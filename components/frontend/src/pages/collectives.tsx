import type { ReactNode } from 'react';

import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import Zap from 'lucide-react/dist/esm/icons/zap';
import { Link } from 'react-router-dom';

import { CollectiveCard } from '@/components/collectives/collective-card';
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
  const featured = (collectives ?? [])
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
          <CollectiveCard key={collective.id} collective={collective} />
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

      <div className='mx-auto max-w-6xl px-6 py-8'>
        <div className='mb-12'>
          <p className='text-muted-foreground mb-6 text-lg'>
            Trusted groups of endpoints. Better discovery, shared identity, collective leverage.
          </p>
          <Button asChild size='lg' className='px-8'>
            <Link to='/browse?tab=collectives'>Browse Collectives</Link>
          </Button>
        </div>

        {/* Active collectives */}
        <div className='mb-12'>
          <div className='mb-6 flex items-center justify-between'>
            <h2 className='text-lg font-semibold'>Active Collectives</h2>
            <Link
              to='/browse?tab=collectives'
              className='text-muted-foreground hover:text-primary text-sm transition-colors'
            >
              View all →
            </Link>
          </div>

          {featuredView}
        </div>

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
