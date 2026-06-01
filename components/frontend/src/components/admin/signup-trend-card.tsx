import type { TrendDays } from '@/hooks/use-admin-api';
import type { SignupTrend } from '@/lib/types';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import { AreaChart } from './mini-chart';

interface SignupTrendCardProperties {
  trend: SignupTrend;
  range: TrendDays;
  onRangeChange: (range: TrendDays) => void;
  /** True while a new range is being fetched — fades the chart. */
  isFetching?: boolean;
}

const RANGES: { value: TrendDays; label: string }[] = [
  { value: 7, label: '7D' },
  { value: 30, label: '30D' },
  { value: 90, label: '90D' }
];

/** Format an ISO `YYYY-MM-DD` date as a short `Mon D` label. */
function shortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * Daily signup-trend card with a 7D / 30D / 90D segmented control. The chart is
 * a dependency-free SVG area chart (see `mini-chart.tsx`).
 */
export function SignupTrendCard({
  trend,
  range,
  onRangeChange,
  isFetching = false
}: Readonly<SignupTrendCardProperties>) {
  const points = trend.buckets.map((b) => ({ label: shortDate(b.date), value: b.signups }));
  const total = trend.buckets.reduce((sum, b) => sum + b.signups, 0);

  return (
    <Card className='border-border/50'>
      <CardHeader className='flex flex-row items-start justify-between gap-4'>
        <div className='flex flex-col gap-1'>
          <CardTitle className='text-base'>New sign-ups</CardTitle>
          <span className='text-muted-foreground text-sm tabular-nums'>
            {total.toLocaleString()} in the last {trend.days} days
          </span>
        </div>
        <div
          className='bg-muted inline-flex items-center gap-1 rounded-lg p-1'
          role='group'
          aria-label='Select trend range'
        >
          {RANGES.map((option) => {
            const isActive = option.value === range;
            return (
              <button
                key={option.value}
                type='button'
                aria-pressed={isActive}
                onClick={() => {
                  onRangeChange(option.value);
                }}
                className={cn(
                  'focus-visible:ring-ring/50 rounded-md px-3 py-1 text-xs font-medium transition-colors focus-visible:ring-[3px] focus-visible:outline-none',
                  isActive
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </CardHeader>
      <CardContent>
        <div className={cn('transition-opacity', isFetching && 'opacity-50')}>
          {total === 0 ? (
            <div className='text-muted-foreground flex h-[220px] items-center justify-center text-sm'>
              No sign-ups in this period.
            </div>
          ) : (
            <AreaChart
              points={points}
              ariaLabel={`Daily sign-ups over the last ${trend.days} days`}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
