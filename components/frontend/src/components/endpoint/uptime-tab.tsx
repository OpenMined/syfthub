import { useMemo, useState } from 'react';

import type { UptimeWindowHours } from '@/lib/uptime';

import { useEndpointUptime } from '@/hooks/use-endpoint-uptime';
import { groupBuckets, summarize, UPTIME_WINDOWS, windowLabel } from '@/lib/uptime';

import { UptimeChart } from './uptime-chart';
import { UptimeSummaryCard } from './uptime-summary-card';

interface UptimeTabProperties {
  owner: string | undefined;
  slug: string;
  /** Window shown first. Defaults to 168 (7 days). */
  windowHours?: UptimeWindowHours;
}

const WINDOW_NAMES: Record<UptimeWindowHours, string> = {
  24: '24 hours',
  168: '7 days',
  720: '30 days'
};

function UptimeSkeleton() {
  return (
    <div className='space-y-6' role='status' aria-label='Loading uptime data'>
      <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className='border-border bg-card rounded-xl border p-5'>
            <div className='bg-muted mb-2 h-3 w-20 animate-pulse rounded' />
            <div className='bg-muted h-8 w-24 animate-pulse rounded' />
          </div>
        ))}
      </div>
      <div className='border-border bg-card rounded-xl border p-6'>
        <div className='bg-muted mb-4 h-4 w-40 animate-pulse rounded' />
        <div className='bg-muted h-60 animate-pulse rounded' />
      </div>
    </div>
  );
}

interface WindowPickerProperties {
  value: UptimeWindowHours;
  onChange: (next: UptimeWindowHours) => void;
}

function WindowPicker({ value, onChange }: Readonly<WindowPickerProperties>) {
  return (
    <div
      role='group'
      aria-label='Time window'
      className='border-border bg-card inline-flex rounded-lg border p-0.5'
    >
      {UPTIME_WINDOWS.map((hours) => {
        const active = hours === value;
        return (
          <button
            key={hours}
            type='button'
            aria-pressed={active}
            onClick={() => {
              onChange(hours);
            }}
            className={`font-inter focus-visible:ring-ring rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none ${
              active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {WINDOW_NAMES[hours]}
          </button>
        );
      })}
    </div>
  );
}

export function UptimeTab({ owner, slug, windowHours = 168 }: Readonly<UptimeTabProperties>) {
  const [window, setWindow] = useState<UptimeWindowHours>(windowHours);
  const { data, isLoading, error, refetch } = useEndpointUptime(owner, slug, {
    windowHours: window
  });

  const groups = useMemo(() => groupBuckets(data, window), [data, window]);
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

  return (
    <div className='space-y-6'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <p className='font-inter text-muted-foreground text-sm'>
          The Hub checks the Space&apos;s latest health report every 30 seconds. Uptime is the share
          of those checks that found the endpoint up.
        </p>
        <WindowPicker value={window} onChange={setWindow} />
      </div>

      {!data || data.buckets.length === 0 ? (
        <div className='border-border bg-card rounded-xl border p-6 text-center'>
          <h3 className='font-rubik text-foreground mb-2 text-sm font-medium'>
            No uptime data in the last {WINDOW_NAMES[window]}
          </h3>
          <p className='font-inter text-muted-foreground text-sm'>
            The health monitor records one sample every 30 seconds and aggregates them into
            30-minute buckets. The first data point should appear within the next half hour.
          </p>
        </div>
      ) : (
        <>
          <UptimeSummaryCard summary={summary} windowLabel={windowLabel(window)} />
          <UptimeChart groups={groups} windowHours={window} />
        </>
      )}
    </div>
  );
}
