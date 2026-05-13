import { useState } from 'react';

import type { DayCell, DayStatus } from '@/lib/uptime';

import { formatDateLong } from '@/lib/date-utils';
import { formatDuration } from '@/lib/uptime';

interface UptimeStripProperties {
  days: DayCell[];
  /** Bucket size in seconds — used to label the resolution caption. */
  bucketSeconds: number;
}

function dayColor(status: DayStatus): string {
  switch (status) {
    case 'operational': {
      return 'bg-green-500 dark:bg-green-600';
    }
    case 'degraded': {
      return 'bg-yellow-500';
    }
    case 'down': {
      return 'bg-red-500 dark:bg-red-600';
    }
    default: {
      // no-data
      return 'bg-muted';
    }
  }
}

function statusLabel(status: DayStatus): string {
  switch (status) {
    case 'operational': {
      return 'Operational';
    }
    case 'degraded': {
      return 'Degraded';
    }
    case 'down': {
      return 'Down';
    }
    default: {
      return 'No data';
    }
  }
}

function formatIncidents(count: number): string {
  if (count === 0) return 'no incidents';
  if (count === 1) return '1 incident';
  return `${String(count)} incidents`;
}

function accessibleLabel(day: DayCell): string {
  const date = formatDateLong(day.date);
  if (day.samples === 0) return `${date}: no uptime data recorded`;
  const uptime = (day.mean_uptime_pct ?? 0).toFixed(2);
  const downtime = formatDuration(day.downtime_seconds);
  const incidents = formatIncidents(day.incident_count);
  return `${date}: ${uptime}% uptime, ${downtime} downtime, ${incidents}, ${String(day.samples)} samples`;
}

function resolutionLabel(bucketSeconds: number): string {
  if (bucketSeconds % 3600 === 0) return `${String(bucketSeconds / 3600)}-hour resolution`;
  if (bucketSeconds % 60 === 0) return `${String(bucketSeconds / 60)}-minute resolution`;
  return `${String(bucketSeconds)}-second resolution`;
}

export function UptimeStrip({ days, bucketSeconds }: Readonly<UptimeStripProperties>) {
  const [selected, setSelected] = useState<DayCell | null>(null);

  const handleToggle = (day: DayCell) => {
    setSelected((previous) => (previous?.dateKey === day.dateKey ? null : day));
  };

  return (
    <section className='border-border bg-card rounded-xl border p-6'>
      <header className='mb-4 flex items-baseline justify-between gap-4'>
        <h3 className='font-rubik text-foreground text-sm font-medium'>Uptime history</h3>
        <p className='font-inter text-muted-foreground text-xs'>
          Last {String(days.length)} days · {resolutionLabel(bucketSeconds)}
        </p>
      </header>

      <div
        // role="list" lets screen readers walk the cells; each cell's
        // accessible label carries the full status, so colour is never the
        // only signal (WCAG 2.2 SC 1.4.1).
        role='list'
        aria-label={`Daily uptime over the last ${String(days.length)} days`}
        className='mb-3 flex h-10 items-stretch gap-[3px]'
      >
        {days.map((day) => {
          const isSelected = selected?.dateKey === day.dateKey;
          return (
            <button
              key={day.dateKey}
              type='button'
              role='listitem'
              aria-label={accessibleLabel(day)}
              aria-pressed={isSelected}
              onClick={() => {
                handleToggle(day);
              }}
              className={`focus-visible:ring-ring flex-1 rounded-[3px] transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none ${dayColor(day.status)} ${
                isSelected ? 'ring-foreground/40 ring-2 ring-offset-1 ring-offset-transparent' : ''
              }`}
            />
          );
        })}
      </div>

      <div className='font-inter text-muted-foreground flex justify-between text-xs'>
        <span>{String(days.length)} days ago</span>
        <span>Today</span>
      </div>

      <div className='border-border mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-4'>
        {(
          [
            ['operational', 'Operational'],
            ['degraded', 'Degraded'],
            ['down', 'Down'],
            ['no-data', 'No data']
          ] as const
        ).map(([status, label]) => (
          <span
            key={status}
            className='font-inter text-muted-foreground inline-flex items-center gap-1.5 text-xs'
          >
            <span className={`h-2.5 w-2.5 rounded-[2px] ${dayColor(status)}`} aria-hidden='true' />
            {label}
          </span>
        ))}
      </div>

      {selected && (
        <div className='border-border bg-muted/30 mt-4 rounded-lg border p-4'>
          <div className='mb-2 flex items-center justify-between gap-4'>
            <p className='font-rubik text-foreground text-sm font-medium'>
              {formatDateLong(selected.date)}
            </p>
            <span className='font-inter text-muted-foreground text-xs'>
              {statusLabel(selected.status)}
            </span>
          </div>
          {selected.samples === 0 ? (
            <p className='font-inter text-muted-foreground text-sm'>
              No uptime data recorded for this day.
            </p>
          ) : (
            <dl className='grid grid-cols-2 gap-4 text-sm sm:grid-cols-4'>
              <div>
                <dt className='text-muted-foreground text-xs'>Uptime</dt>
                <dd className='font-inter text-foreground tabular-nums'>
                  {(selected.mean_uptime_pct ?? 0).toFixed(2)}%
                </dd>
              </div>
              <div>
                <dt className='text-muted-foreground text-xs'>Downtime</dt>
                <dd className='font-inter text-foreground tabular-nums'>
                  {formatDuration(selected.downtime_seconds)}
                </dd>
              </div>
              <div>
                <dt className='text-muted-foreground text-xs'>Incidents</dt>
                <dd className='font-inter text-foreground tabular-nums'>
                  {selected.incident_count}
                </dd>
              </div>
              <div>
                <dt className='text-muted-foreground text-xs'>Samples</dt>
                <dd className='font-inter text-foreground tabular-nums'>{selected.samples}</dd>
              </div>
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
