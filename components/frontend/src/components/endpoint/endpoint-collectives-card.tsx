import Database from 'lucide-react/dist/esm/icons/database';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import { Link } from 'react-router-dom';

import { CollectiveIcon } from '@/components/collectives/collective-icon';
import { useCollectivesForEndpoint } from '@/hooks/use-collectives';

interface EndpointCollectivesCardProperties {
  owner: string | undefined | null;
  slug: string | undefined | null;
}

/**
 * Sidebar card listing the collectives an endpoint is an approved member of.
 *
 * Returns ``null`` (and renders nothing) while loading, on error, or when the
 * endpoint has no approved memberships — the card only appears when it has
 * something to show, matching the conditional pattern of ``ConnectionCard``.
 *
 * Rows are compact and link the whole row to the collective page. The list
 * area scrolls once it grows past the card's visible height so the sidebar
 * doesn't stretch arbitrarily.
 */
export function EndpointCollectivesCard({
  owner,
  slug
}: Readonly<EndpointCollectivesCardProperties>) {
  const { data, isLoading, error } = useCollectivesForEndpoint(owner, slug);

  if (isLoading || error) return null;
  const collectives = data ?? [];
  if (collectives.length === 0) return null;

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      <div className='mb-4 flex items-center justify-between'>
        <h3 className='font-rubik text-foreground text-sm font-medium'>Collectives</h3>
        <span className='bg-accent text-muted-foreground rounded-full px-2 py-0.5 text-xs font-medium'>
          {collectives.length}
        </span>
      </div>

      <div className='scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border/50 hover:scrollbar-thumb-border/80 [&::-webkit-scrollbar-thumb]:bg-border/40 [&::-webkit-scrollbar-thumb:hover]:bg-border/60 -mr-1 max-h-[280px] space-y-1 overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent'>
        {collectives.map((collective) => (
          <Link
            key={collective.id}
            to={`/c/${collective.slug}`}
            className='hover:bg-accent/50 -mx-2 flex items-center gap-3 rounded-lg px-2 py-2 transition-colors'
          >
            <CollectiveIcon collective={collective} size='md' />
            <div className='min-w-0 flex-1'>
              <div className='flex items-center gap-1'>
                <span className='font-inter text-foreground truncate text-sm font-medium'>
                  {collective.name}
                </span>
                {collective.verified ? (
                  <ShieldCheck
                    className='h-3.5 w-3.5 shrink-0 text-green-500'
                    aria-label='Verified collective'
                  />
                ) : null}
              </div>
              <div className='text-muted-foreground flex items-center gap-2 text-xs'>
                <span className='truncate'>@{collective.slug}</span>
                <span aria-hidden='true'>·</span>
                <span className='flex items-center gap-1 whitespace-nowrap'>
                  <Database className='h-3 w-3' />
                  {collective.member_count}
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
