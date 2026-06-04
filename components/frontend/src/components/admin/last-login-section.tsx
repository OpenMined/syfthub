import type { LastLoginStats } from '@/lib/types';
import type { BarChartDatum } from './mini-chart';

import Activity from 'lucide-react/dist/esm/icons/activity';
import MoonStar from 'lucide-react/dist/esm/icons/moon-star';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { percent } from '@/lib/utils';

import { KpiCard } from './kpi-card';
import { HorizontalBars } from './mini-chart';

interface LastLoginSectionProperties {
  stats: LastLoginStats;
  totalUsers: number;
}

/**
 * Map a recency bucket key to a chart color token. Recent buckets use the
 * chart accents; older / never buckets fade to muted to read as "stale".
 */
const BUCKET_COLOR: Record<string, string> = {
  '24h': 'var(--color-chart-1)',
  '7d': 'var(--color-chart-2)',
  '30d': 'var(--color-chart-3)',
  '90d': 'var(--color-muted-foreground)',
  never: 'var(--color-muted-foreground)'
};

/**
 * Activity section: an "Active Now" and a "Dormant Accounts" KPI plus a
 * horizontal-bar distribution of last-login recency across all users.
 */
export function LastLoginSection({ stats, totalUsers }: Readonly<LastLoginSectionProperties>) {
  const bars: BarChartDatum[] = stats.buckets.map((b) => ({
    label: b.label,
    value: b.count,
    color: BUCKET_COLOR[b.bucket] ?? 'var(--color-muted-foreground)'
  }));

  return (
    <section aria-labelledby='admin-activity-heading' className='flex flex-col gap-4'>
      <h2 id='admin-activity-heading' className='text-foreground text-lg font-semibold'>
        Activity
      </h2>

      <div className='grid grid-cols-1 gap-6 lg:grid-cols-3'>
        <KpiCard
          label='Active Now'
          value={stats.active_24h}
          icon={Activity}
          delta={`${percent(stats.active_24h, totalUsers)}% of users`}
          deltaTone='positive'
          hint='Signed in within the last 24 hours'
        />
        <KpiCard
          label='Dormant Accounts'
          value={stats.dormant_30d}
          icon={MoonStar}
          delta={`${percent(stats.dormant_30d, totalUsers)}% of users`}
          deltaTone='muted'
          hint='No login in 30+ days, or never'
        />
        <Card className='border-border/50 lg:col-span-1'>
          <CardHeader>
            <CardTitle className='text-base'>Last login</CardTitle>
          </CardHeader>
          <CardContent>
            <HorizontalBars data={bars} />
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
