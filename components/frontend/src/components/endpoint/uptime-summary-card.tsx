import type { UptimeSummary } from '@/lib/uptime';

import { formatDuration } from '@/lib/uptime';

interface UptimeSummaryCardProperties {
  summary: UptimeSummary;
  /** Window label, e.g. "30-day". Defaults to "30-day". */
  windowLabel?: string;
}

function formatPct(value: number | null): string {
  if (value === null) return '—';
  return value.toFixed(2);
}

function classifyUptimeTone(uptimePct: number | null): string {
  if (uptimePct === null) return 'text-foreground';
  if (uptimePct >= 99) return 'text-green-600 dark:text-green-500';
  if (uptimePct >= 90) return 'text-yellow-600 dark:text-yellow-500';
  return 'text-red-600 dark:text-red-500';
}

export function UptimeSummaryCard({
  summary,
  windowLabel = '30-day'
}: Readonly<UptimeSummaryCardProperties>) {
  const uptimeTone = classifyUptimeTone(summary.uptime_pct);
  return (
    <section className='border-border bg-card rounded-xl border p-6'>
      <div className='grid grid-cols-1 gap-6 sm:grid-cols-3'>
        <div>
          <p className='font-inter text-muted-foreground mb-1 text-xs tracking-wide uppercase'>
            {windowLabel} uptime
          </p>
          <p className={`font-rubik text-3xl font-medium tabular-nums ${uptimeTone}`}>
            {formatPct(summary.uptime_pct)}
            {summary.uptime_pct !== null && (
              <span className='text-muted-foreground ml-0.5 text-xl'>%</span>
            )}
          </p>
        </div>

        <div>
          <p className='font-inter text-muted-foreground mb-1 text-xs tracking-wide uppercase'>
            Total downtime
          </p>
          <p className='font-rubik text-foreground text-3xl font-medium tabular-nums'>
            {formatDuration(summary.downtime_seconds)}
          </p>
        </div>

        <div>
          <p className='font-inter text-muted-foreground mb-1 text-xs tracking-wide uppercase'>
            Incidents
          </p>
          <p className='font-rubik text-foreground text-3xl font-medium tabular-nums'>
            {summary.incident_count}
          </p>
        </div>
      </div>
    </section>
  );
}
