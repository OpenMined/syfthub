import { useMemo } from 'react';

import { useEndpointUptime } from '@/hooks/use-endpoint-uptime';
import { aggregateByDay, summarize } from '@/lib/uptime';

import { UptimeStrip } from './uptime-strip';
import { UptimeSummaryCard } from './uptime-summary-card';

interface UptimeTabProperties {
  owner: string | undefined;
  slug: string;
  /** Rolling window. Defaults to 720 (30 days). */
  windowHours?: number;
}

function UptimeSkeleton() {
  return (
    <div className='space-y-6' role='status' aria-label='Loading uptime data'>
      <div className='border-border bg-card rounded-xl border p-6'>
        <div className='grid grid-cols-1 gap-6 sm:grid-cols-3'>
          {[0, 1, 2].map((index) => (
            <div key={index}>
              <div className='bg-muted mb-2 h-3 w-24 animate-pulse rounded' />
              <div className='bg-muted h-8 w-20 animate-pulse rounded' />
            </div>
          ))}
        </div>
      </div>
      <div className='border-border bg-card rounded-xl border p-6'>
        <div className='bg-muted mb-4 h-4 w-32 animate-pulse rounded' />
        <div className='mb-3 flex h-10 items-stretch gap-[3px]'>
          {Array.from({ length: 30 }, (_, index) => (
            <div key={index} className='bg-muted flex-1 animate-pulse rounded-[3px]' />
          ))}
        </div>
        <div className='bg-muted h-3 w-full max-w-xs animate-pulse rounded' />
      </div>
    </div>
  );
}

export function UptimeTab({ owner, slug, windowHours = 720 }: Readonly<UptimeTabProperties>) {
  const { data, isLoading, error, refetch } = useEndpointUptime(owner, slug, { windowHours });

  const days = useMemo(
    () => aggregateByDay(data, Math.ceil(windowHours / 24)),
    [data, windowHours]
  );
  const summary = useMemo(() => summarize(data), [data]);

  if (isLoading) {
    return <UptimeSkeleton />;
  }

  if (error) {
    return (
      <div className='border-border bg-card rounded-xl border p-6 text-center'>
        <h3 className='font-rubik text-foreground mb-2 text-sm font-medium'>
          Couldn&apos;t load uptime
        </h3>
        <p className='font-inter text-muted-foreground mb-4 text-sm'>
          {error instanceof Error ? error.message : 'Unknown error'}
        </p>
        <button
          type='button'
          onClick={() => void refetch()}
          className='border-border text-foreground hover:bg-muted inline-flex items-center rounded-md border px-4 py-2 text-sm font-medium transition-colors'
        >
          Try again
        </button>
      </div>
    );
  }

  if (!data || data.buckets.length === 0) {
    return (
      <div className='border-border bg-card rounded-xl border p-6 text-center'>
        <h3 className='font-rubik text-foreground mb-2 text-sm font-medium'>No uptime data yet</h3>
        <p className='font-inter text-muted-foreground text-sm'>
          The health monitor records one sample every 30 seconds and aggregates them into 30-minute
          buckets. The first data point should appear within the next half hour.
        </p>
      </div>
    );
  }

  return (
    <div className='space-y-6'>
      <UptimeSummaryCard
        summary={summary}
        windowLabel={`${String(Math.ceil(windowHours / 24))}-day`}
      />
      <UptimeStrip days={days} bucketSeconds={data.bucket_seconds} />
    </div>
  );
}
