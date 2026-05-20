import type { Collective } from '@/lib/collectives-api';

import Database from 'lucide-react/dist/esm/icons/database';
import Lock from 'lucide-react/dist/esm/icons/lock';
import LockOpen from 'lucide-react/dist/esm/icons/lock-open';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link } from 'react-router-dom';

import { CollectiveIcon } from '@/components/collectives/collective-icon';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

interface CollectiveCardProps {
  collective: Collective;
}

/**
 * Compact collective summary used in the browse grid and landing page.
 *
 * Layout separates three distinct kinds of information so none is mistaken
 * for an action: identity (header), descriptive metadata (counts + join
 * policy, as borderless inline facts), and topic tags (the only badges).
 */
export function CollectiveCard({ collective }: Readonly<CollectiveCardProps>) {
  return (
    <Link to={`/c/${collective.slug}`}>
      <Card className='hover:border-primary/50 h-full p-5 transition-all hover:shadow-lg'>
        {/* Header: icon, name, verification, slug */}
        <div className='mb-3 flex items-start gap-3'>
          <CollectiveIcon collective={collective} size='md' />
          <div className='min-w-0 flex-1'>
            <div className='flex items-center gap-1.5'>
              <h3 className='text-foreground truncate font-semibold'>{collective.name}</h3>
              {collective.verified && (
                <ShieldCheck
                  className='h-4 w-4 shrink-0 text-green-500'
                  aria-label='Verified collective'
                />
              )}
            </div>
            <p className='text-muted-foreground truncate text-sm'>@{collective.slug}</p>
          </div>
        </div>

        {/* Description */}
        <p className='text-muted-foreground mb-3 line-clamp-2 min-h-[2.5rem] text-sm'>
          {collective.description || 'No description provided.'}
        </p>

        {/* Metadata — members & endpoints as borderless inline facts; the join
            policy as a pastel ghost-style status badge. */}
        <div className='text-muted-foreground mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm'>
          <span className='flex items-center gap-1' title='Members'>
            <Users className='h-3.5 w-3.5' />
            {collective.owner_count}
          </span>
          <span className='flex items-center gap-1' title='Endpoints'>
            <Database className='h-3.5 w-3.5' />
            {collective.member_count}
          </span>
          <Badge
            variant='outline'
            title='How endpoints join'
            className={
              collective.auto_approve
                ? 'gap-1 border-green-500/30 bg-green-500/15 text-green-700 dark:text-green-400'
                : 'gap-1 border-yellow-500/30 bg-yellow-500/15 text-yellow-700 dark:text-yellow-400'
            }
          >
            {collective.auto_approve ? (
              <LockOpen className='h-3 w-3' />
            ) : (
              <Lock className='h-3 w-3' />
            )}
            {collective.auto_approve ? 'Open' : 'Approval required'}
          </Badge>
        </div>

        {/* Topic tags — the only badges on the card */}
        {collective.tags.length > 0 && (
          <div className='flex flex-wrap gap-1.5'>
            {collective.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant='secondary' className='text-xs'>
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </Card>
    </Link>
  );
}
