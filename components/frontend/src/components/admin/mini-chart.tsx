import { useEffect, useRef, useState } from 'react';

import { cn } from '@/lib/utils';

/** Observe an element's width so the SVG can scale to its container. */
function useContainerWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(element);
    setWidth(element.clientWidth);
    return () => {
      observer.disconnect();
    };
  }, []);

  return [ref, width];
}

export interface AreaChartPoint {
  /** X-axis label (e.g. a date). Used for the accessible description + tooltip. */
  label: string;
  value: number;
}

interface AreaChartProperties {
  points: AreaChartPoint[];
  height?: number;
  className?: string;
  /** Accessible title for the chart. */
  ariaLabel: string;
}

/**
 * A dependency-free SVG area + line chart for the signup trend.
 *
 * Scales to its container width via a ResizeObserver and uses the brand
 * `--chart-1` token for the stroke/fill. The series is exposed to assistive
 * tech as an accessible `<title>` plus a visually-hidden data summary.
 */
export function AreaChart({
  points,
  height = 220,
  className,
  ariaLabel
}: Readonly<AreaChartProperties>) {
  const [ref, width] = useContainerWidth();
  const padding = { top: 12, right: 8, bottom: 24, left: 8 };
  const innerW = Math.max(width - padding.left - padding.right, 0);
  const innerH = height - padding.top - padding.bottom;

  const max = Math.max(1, ...points.map((p) => p.value));
  const stepX = points.length > 1 ? innerW / (points.length - 1) : 0;

  const coords = points.map((p, index) => {
    const x = padding.left + stepX * index;
    const y = padding.top + innerH - (p.value / max) * innerH;
    return { x, y, ...p };
  });

  const linePath = coords.map((c, index) => `${index === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ');
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords.at(-1)?.x ?? padding.left} ${padding.top + innerH} L ${
          coords[0]?.x ?? padding.left
        } ${padding.top + innerH} Z`
      : '';

  const total = points.reduce((sum, p) => sum + p.value, 0);
  const gradientId = 'admin-signup-gradient';

  return (
    <div ref={ref} className={cn('w-full', className)}>
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role='img'
          aria-label={ariaLabel}
          className='overflow-visible'
        >
          <title>{ariaLabel}</title>
          <desc>
            {points.length} data points, {total.toLocaleString()} total. Peak {max.toLocaleString()}
            .
          </desc>
          <defs>
            <linearGradient id={gradientId} x1='0' y1='0' x2='0' y2='1'>
              <stop offset='0%' stopColor='var(--color-chart-1)' stopOpacity='0.35' />
              <stop offset='100%' stopColor='var(--color-chart-1)' stopOpacity='0' />
            </linearGradient>
          </defs>
          {/* baseline */}
          <line
            x1={padding.left}
            y1={padding.top + innerH}
            x2={padding.left + innerW}
            y2={padding.top + innerH}
            className='stroke-border'
            strokeWidth={1}
          />
          {areaPath ? <path d={areaPath} fill={`url(#${gradientId})`} /> : null}
          {linePath ? (
            <path
              d={linePath}
              fill='none'
              stroke='var(--color-chart-1)'
              strokeWidth={2}
              strokeLinejoin='round'
              strokeLinecap='round'
            />
          ) : null}
          {coords.map((c) => (
            <circle key={c.label} cx={c.x} cy={c.y} r={2} fill='var(--color-chart-1)'>
              <title>{`${c.label}: ${c.value.toLocaleString()}`}</title>
            </circle>
          ))}
        </svg>
      ) : (
        <div style={{ height }} />
      )}
    </div>
  );
}

export interface BarChartDatum {
  label: string;
  value: number;
  /** CSS color (token var) for the bar fill. */
  color: string;
}

interface HorizontalBarsProperties {
  data: BarChartDatum[];
  className?: string;
}

/**
 * A dependency-free horizontal-bar distribution (used for last-login recency).
 * Each row is a labelled track; bars are sized relative to the largest value.
 */
export function HorizontalBars({ data, className }: Readonly<HorizontalBarsProperties>) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <ul className={cn('flex flex-col gap-3', className)}>
      {data.map((d) => {
        const pct = Math.round((d.value / max) * 100);
        return (
          <li key={d.label} className='flex flex-col gap-1'>
            <div className='flex items-center justify-between text-sm'>
              <span className='text-muted-foreground'>{d.label}</span>
              <span className='text-foreground font-medium tabular-nums'>
                {d.value.toLocaleString()}
              </span>
            </div>
            <div
              className='bg-muted h-2 w-full overflow-hidden rounded-full'
              role='img'
              aria-label={`${d.label}: ${d.value.toLocaleString()} users`}
            >
              <div
                className='h-full rounded-full transition-all'
                style={{ width: `${pct}%`, backgroundColor: d.color }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
