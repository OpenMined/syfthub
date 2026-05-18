import type { Collective } from '@/lib/collectives-api';

import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface CollectiveCardProps {
  collective: Collective;
}

/**
 * Compact collective summary used in the browse grid and landing page.
 *
 * Renders only fields the backend actually provides: name, slug, verification,
 * description, approved-member count, tags, and the join policy (`auto_approve`).
 */
export function CollectiveCard({ collective }: Readonly<CollectiveCardProps>) {
  return (
    <Link to={`/c/${collective.slug}`}>
      <Card className='hover:border-primary/50 group relative h-full overflow-hidden p-5 transition-all hover:shadow-lg'>
        {/* Header: icon, name, verification, slug */}
        <div className='mb-3 flex items-start gap-3'>
          {collective.icon_url ? (
            <img
              src={collective.icon_url}
              alt={collective.name}
              className='h-10 w-10 shrink-0 rounded-lg object-cover'
            />
          ) : (
            <div className='from-primary/20 to-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br'>
              <Users className='text-primary h-5 w-5' />
            </div>
          )}
          <div className='min-w-0 flex-1'>
            <div className='flex items-center gap-1.5'>
              <h3 className='text-foreground truncate font-semibold'>{collective.name}</h3>
              {collective.verified && (
                <CheckCircle
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

        {/* Member count */}
        <div className='text-muted-foreground mb-3 flex items-center gap-1 text-sm'>
          <Users className='h-3.5 w-3.5' />
          <span>
            {collective.member_count} {collective.member_count === 1 ? 'endpoint' : 'endpoints'}
          </span>
        </div>

        {/* Tags + join policy */}
        <div className='flex flex-wrap items-center gap-1.5'>
          {collective.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} variant='secondary' className='text-xs'>
              {tag}
            </Badge>
          ))}
          <Badge
            variant='outline'
            className={cn(
              'ml-auto text-xs',
              collective.auto_approve ? 'text-green-600' : 'text-yellow-600'
            )}
          >
            {collective.auto_approve ? 'Open' : 'Request to join'}
          </Badge>
        </div>
      </Card>
    </Link>
  );
}
