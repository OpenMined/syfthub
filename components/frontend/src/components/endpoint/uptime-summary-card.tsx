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

interface TileProperties {
  label: string;
  children: React.ReactNode;
  detail?: string;
  tone?: string;
}

function Tile({ label, children, detail, tone = 'text-foreground' }: Readonly<TileProperties>) {
  return (
    <div className='border-border bg-card min-w-0 rounded-xl border p-5'>
      <p className='font-inter text-muted-foreground mb-1 text-xs tracking-wide uppercase'>
        {label}
      </p>
      <p className={`font-rubik text-3xl font-medium tabular-nums ${tone}`}>{children}</p>
      {detail && (
        <p className='font-inter text-muted-foreground mt-1 text-xs tabular-nums'>{detail}</p>
      )}
    </div>
  );
}

export function UptimeSummaryCard({
  summary,
  windowLabel = '30-day'
}: Readonly<UptimeSummaryCardProperties>) {
  return (
    <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
      <Tile
        label={`${windowLabel} uptime`}
        tone={classifyUptimeTone(summary.uptime_pct)}
        detail={
          summary.total_samples > 0
            ? `${summary.total_healthy.toLocaleString()} of ${summary.total_samples.toLocaleString()} checks`
            : undefined
        }
      >
        {formatPct(summary.uptime_pct)}
        {summary.uptime_pct !== null && (
          <span className='text-muted-foreground ml-0.5 text-xl'>%</span>
        )}
      </Tile>
      <Tile label='Total downtime' detail='time the Hub listed it down'>
        {formatDuration(summary.downtime_seconds)}
      </Tile>
      <Tile label='Unhealthy checks' detail='monitor cycles that found it down'>
        {summary.total_unhealthy.toLocaleString()}
      </Tile>
      <Tile label='Incidents' detail='runs of 30 min below 90% uptime'>
        {summary.incident_count}
      </Tile>
    </div>
  );
}
