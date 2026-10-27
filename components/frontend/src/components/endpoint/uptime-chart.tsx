import { useId, useState } from 'react';

import type { BucketGroup } from '@/lib/uptime';

import { useContainerWidth } from '@/hooks/use-container-width';

interface UptimeChartProperties {
  groups: BucketGroup[];
  /** Window the groups cover, used to pick time-axis label formats. */
  windowHours: number;
}

type Band = 'operational' | 'degraded' | 'down';

const OPERATIONAL_PCT = 99;
const DEGRADED_PCT = 90;

const BAND_FILL: Record<Band, string> = {
  operational: 'fill-green-500 dark:fill-green-600',
  degraded: 'fill-yellow-500',
  down: 'fill-red-500 dark:fill-red-600'
};

const BAND_LABEL: Record<Band, string> = {
  operational: `Operational (≥ ${String(OPERATIONAL_PCT)}%)`,
  degraded: `Degraded (${String(DEGRADED_PCT)} to ${String(OPERATIONAL_PCT)}%)`,
  down: `Down (< ${String(DEGRADED_PCT)}%)`
};

export function bandFor(uptimePct: number): Band {
  if (uptimePct >= OPERATIONAL_PCT) return 'operational';
  if (uptimePct >= DEGRADED_PCT) return 'degraded';
  return 'down';
}

function formatCount(value: number): string {
  return value.toLocaleString();
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDay(date: Date): string {
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/** Axis label for a column start: time of day inside one day, otherwise date. */
function axisLabel(date: Date, windowHours: number): string {
  if (windowHours <= 24) return formatTime(date);
  if (windowHours <= 168) return `${formatDay(date)}, ${formatTime(date)}`;
  return formatDay(date);
}

function rangeLabel(group: BucketGroup): string {
  const sameDay = group.start.toDateString() === group.end.toDateString();
  const end = sameDay ? formatTime(group.end) : `${formatDay(group.end)}, ${formatTime(group.end)}`;
  return `${formatDay(group.start)}, ${formatTime(group.start)} to ${end}`;
}

function describeGroup(groups: BucketGroup[]): string {
  const first = groups[0];
  if (!first) return 'slot';
  const minutes = Math.round((first.end.getTime() - first.start.getTime()) / 60_000);
  if (minutes % 60 !== 0) return `${String(minutes)}-minute slot`;
  const hours = minutes / 60;
  return hours === 1 ? 'hour' : `${String(hours)}-hour slot`;
}

/**
 * One column per time slot, height = uptime for that slot on a 0 to 100%
 * axis, colour = the same bands the summary tile uses. Slots with no
 * checks draw a baseline tick, so monitoring gaps read as gaps rather than
 * as outages.
 */
export function UptimeChart({ groups, windowHours }: Readonly<UptimeChartProperties>) {
  const [ref, width] = useContainerWidth();
  const [hovered, setHovered] = useState<number | null>(null);
  const titleId = useId();

  const height = 240;
  const padding = { top: 12, right: 8, bottom: 28, left: 44 };
  const innerW = Math.max(width - padding.left - padding.right, 0);
  const innerH = height - padding.top - padding.bottom;
  const baseline = padding.top + innerH;

  const slot = groups.length > 0 ? innerW / groups.length : 0;
  const barWidth = Math.max(2, slot * 0.72);
  const labelEvery = Math.max(1, Math.ceil(groups.length / 6));
  const scale = (pct: number) => (pct / 100) * innerH;

  const hoveredGroup = hovered === null ? null : groups[hovered];
  const tooltipLeft =
    hovered === null
      ? 0
      : Math.min(Math.max(padding.left + slot * hovered + slot / 2, 90), Math.max(width - 90, 90));

  return (
    <section className='border-border bg-card rounded-xl border p-6'>
      <header className='mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2'>
        <h3 id={titleId} className='font-rubik text-foreground text-sm font-medium'>
          Uptime over time
        </h3>
        <div className='font-inter text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs'>
          {(['operational', 'degraded', 'down'] as const).map((band) => (
            <span key={band} className='inline-flex items-center gap-1.5'>
              <svg width='10' height='10' aria-hidden='true'>
                <rect width='10' height='10' rx='2' className={BAND_FILL[band]} />
              </svg>
              {BAND_LABEL[band]}
            </span>
          ))}
          <span className='inline-flex items-center gap-1.5'>
            <svg width='10' height='10' aria-hidden='true'>
              <rect width='10' height='10' rx='2' className='fill-border' />
            </svg>
            No checks
          </span>
        </div>
      </header>

      <div ref={ref} className='relative w-full'>
        {width > 0 && (
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${String(width)} ${String(height)}`}
            role='img'
            aria-labelledby={titleId}
            className='block overflow-visible'
            onMouseLeave={() => {
              setHovered(null);
            }}
          >
            {[0, 25, 50, 75, 100].map((pct) => {
              const y = baseline - scale(pct);
              return (
                <g key={pct}>
                  <line
                    x1={padding.left}
                    x2={width - padding.right}
                    y1={y}
                    y2={y}
                    className='stroke-border'
                    strokeDasharray={pct === 0 ? undefined : '3 3'}
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 4}
                    textAnchor='end'
                    className='fill-muted-foreground font-inter text-[11px] tabular-nums'
                  >
                    {String(pct)}%
                  </text>
                </g>
              );
            })}
            {/* Threshold guides: where a column changes colour. */}
            {[DEGRADED_PCT, OPERATIONAL_PCT].map((pct) => (
              <line
                key={pct}
                x1={padding.left}
                x2={width - padding.right}
                y1={baseline - scale(pct)}
                y2={baseline - scale(pct)}
                className={pct === OPERATIONAL_PCT ? 'stroke-green-500/40' : 'stroke-yellow-500/50'}
                strokeDasharray='2 4'
              />
            ))}

            {groups.map((group, index) => {
              const x = padding.left + slot * index + (slot - barWidth) / 2;
              const isHovered = hovered === index;
              const pct = group.uptime_pct;
              const label =
                pct === null
                  ? `${rangeLabel(group)}: no checks recorded`
                  : `${rangeLabel(group)}: ${pct.toFixed(2)}% uptime, ${formatCount(group.unhealthy_samples)} of ${formatCount(group.samples)} checks unhealthy`;
              return (
                <g
                  key={group.start.toISOString()}
                  tabIndex={0}
                  role='listitem'
                  aria-label={label}
                  className='focus-visible:outline-none'
                  onMouseEnter={() => {
                    setHovered(index);
                  }}
                  onFocus={() => {
                    setHovered(index);
                  }}
                  onBlur={() => {
                    setHovered(null);
                  }}
                >
                  {/* Wide invisible hit target so thin columns are easy to hover. */}
                  <rect
                    x={padding.left + slot * index}
                    y={padding.top}
                    width={Math.max(slot, 1)}
                    height={innerH}
                    fill='transparent'
                  />
                  {pct === null ? (
                    <rect
                      x={x}
                      y={baseline - 2}
                      width={barWidth}
                      height={2}
                      className='fill-border'
                    />
                  ) : (
                    <rect
                      x={x}
                      y={baseline - Math.max(scale(pct), 2)}
                      width={barWidth}
                      height={Math.max(scale(pct), 2)}
                      rx={2}
                      className={`${BAND_FILL[bandFor(pct)]} ${isHovered ? 'opacity-100' : 'opacity-85'}`}
                    />
                  )}
                </g>
              );
            })}

            {groups.map((group, index) =>
              index % labelEvery === 0 ? (
                <text
                  key={`label-${group.start.toISOString()}`}
                  x={padding.left + slot * index + slot / 2}
                  y={height - 8}
                  textAnchor='middle'
                  className='fill-muted-foreground font-inter text-[11px]'
                >
                  {axisLabel(group.start, windowHours)}
                </text>
              ) : null
            )}
          </svg>
        )}

        {hoveredGroup && (
          <div
            role='status'
            className='border-border bg-popover text-popover-foreground pointer-events-none absolute top-2 z-10 w-48 -translate-x-1/2 rounded-md border px-3 py-2 text-xs shadow-md'
            style={{ left: tooltipLeft }}
          >
            <p className='font-inter text-muted-foreground mb-1'>{rangeLabel(hoveredGroup)}</p>
            {hoveredGroup.uptime_pct === null ? (
              <p className='font-inter'>No checks recorded</p>
            ) : (
              <dl className='font-inter grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums'>
                <dt className='text-muted-foreground'>Uptime</dt>
                <dd className='text-right'>{hoveredGroup.uptime_pct.toFixed(2)}%</dd>
                <dt className='text-muted-foreground'>Checks</dt>
                <dd className='text-right'>{formatCount(hoveredGroup.samples)}</dd>
                <dt className='text-muted-foreground'>Unhealthy</dt>
                <dd className='text-right'>{formatCount(hoveredGroup.unhealthy_samples)}</dd>
              </dl>
            )}
          </div>
        )}
      </div>

      <p className='font-inter text-muted-foreground mt-3 text-xs'>
        Each column is one {describeGroup(groups)}, in your local time. Column height is the share
        of the Hub&apos;s checks in that slot that found the endpoint up.
      </p>
    </section>
  );
}
