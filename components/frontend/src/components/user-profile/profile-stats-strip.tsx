import type { ChatSource } from '@/lib/types';

import Clock from 'lucide-react/dist/esm/icons/clock';
import Package from 'lucide-react/dist/esm/icons/package';
import Star from 'lucide-react/dist/esm/icons/star';

import { formatRelativeTime } from '@/lib/date-utils';

interface ProfileStatsStripProps {
  endpoints: ChatSource[];
}

interface StatTileProps {
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  label: string;
  value: string;
}

function StatTile({ icon: Icon, label, value }: Readonly<StatTileProps>) {
  return (
    <div className='flex items-center gap-2'>
      <Icon className='text-muted-foreground h-4 w-4' aria-hidden={true} />
      <div className='flex flex-col'>
        <span className='font-rubik text-foreground text-sm font-medium tabular-nums'>{value}</span>
        <span className='font-inter text-muted-foreground text-[11px] tracking-wide uppercase'>
          {label}
        </span>
      </div>
    </div>
  );
}

export function ProfileStatsStrip({ endpoints }: Readonly<ProfileStatsStripProps>) {
  const endpointCount = endpoints.length;
  let totalStars = 0;
  let maxTs = 0;
  let mostRecentUpdate: string | null = null;
  for (const ep of endpoints) {
    totalStars += ep.stars_count;
    const ts = Date.parse(ep.updated_at);
    if (ts > maxTs) {
      maxTs = ts;
      mostRecentUpdate = ep.updated_at;
    }
  }

  return (
    <div className='border-border bg-background border-b'>
      <div className='mx-auto flex max-w-5xl flex-wrap gap-x-10 gap-y-4 px-6 py-4'>
        <StatTile
          icon={Package}
          label={endpointCount === 1 ? 'endpoint' : 'endpoints'}
          value={String(endpointCount)}
        />
        <StatTile
          icon={Star}
          label={totalStars === 1 ? 'star' : 'stars'}
          value={String(totalStars)}
        />
        {mostRecentUpdate ? (
          <StatTile
            icon={Clock}
            label='last updated'
            value={formatRelativeTime(mostRecentUpdate)}
          />
        ) : null}
      </div>
    </div>
  );
}
