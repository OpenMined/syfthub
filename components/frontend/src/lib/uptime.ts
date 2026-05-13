/**
 * Pure utilities for the endpoint uptime tab.
 *
 * The backend exposes 30-minute buckets via
 * GET /api/v1/endpoints/{owner}/{slug}/uptime?window_hours=720, where each
 * bucket aggregates the health monitor's per-cycle decisions. These helpers
 * roll the bucket array up into day-level cells for the strip chart and
 * compute window-wide summary stats.
 *
 * All functions are pure so the math can be unit-tested without rendering.
 */

export interface UptimeBucket {
  /** ISO timestamp marking the start of the 30-min bucket. */
  bucket_start: string;
  /** Number of monitor cycles recorded in this bucket. */
  samples: number;
  /** Number of those cycles in which the endpoint was healthy. */
  healthy_samples: number;
  /** healthy_samples / samples * 100. */
  uptime_pct: number;
}

export interface EndpointUptimeResponse {
  endpoint_id: number;
  owner_username: string;
  slug: string;
  /** Bucket size in seconds (default 1800 = 30 min). */
  bucket_seconds: number;
  /** Window covered by the response. */
  window_hours: number;
  buckets: UptimeBucket[];
}

export type DayStatus = 'operational' | 'degraded' | 'down' | 'no-data';

export interface DayCell {
  /** UTC midnight for this day. */
  date: Date;
  /** YYYY-MM-DD key (UTC). */
  dateKey: string;
  samples: number;
  healthy_samples: number;
  /** Sum of `bucket_seconds * (samples - healthy_samples) / samples` across the day. */
  downtime_seconds: number;
  /** mean uptime % across the day, or null if no samples. */
  mean_uptime_pct: number | null;
  /** Worst (lowest) uptime % observed in any bucket of the day. */
  min_uptime_pct: number | null;
  /** Number of distinct unhealthy incidents in the day (see countIncidents). */
  incident_count: number;
  status: DayStatus;
}

export interface UptimeSummary {
  uptime_pct: number | null;
  downtime_seconds: number;
  incident_count: number;
  total_samples: number;
  total_healthy: number;
}

/**
 * A bucket is "unhealthy enough to count as an incident" when its uptime
 * dipped below 90%. Chosen to match the strip's red threshold so the
 * incident count visibly tracks what the user sees.
 */
const INCIDENT_THRESHOLD_PCT = 90;

export function utcDateKey(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function utcMidnight(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
}

/**
 * Classify a day cell into one of four visual states based on its worst
 * (lowest) bucket uptime. Worst-of, not average, because operators care
 * about whether *anything* went wrong, not the smoothed mean.
 */
export function classifyDay(min_uptime_pct: number | null, samples: number): DayStatus {
  if (samples === 0 || min_uptime_pct === null) return 'no-data';
  if (min_uptime_pct >= 99) return 'operational';
  if (min_uptime_pct >= INCIDENT_THRESHOLD_PCT) return 'degraded';
  return 'down';
}

/**
 * Count maximal contiguous runs of buckets that fell below the incident
 * threshold. A single sub-90% bucket is one incident; consecutive sub-90%
 * buckets are still one incident.
 */
export function countIncidents(buckets: UptimeBucket[]): number {
  let incidents = 0;
  let inIncident = false;
  for (const b of buckets) {
    if (b.samples === 0) continue;
    if (b.uptime_pct < INCIDENT_THRESHOLD_PCT) {
      if (!inIncident) {
        incidents += 1;
        inIncident = true;
      }
    } else {
      inIncident = false;
    }
  }
  return incidents;
}

/**
 * Group buckets into day cells covering the last `days` days, ending at
 * `now`. Missing days are filled with no-data cells so the strip always
 * renders `days` items regardless of how much history exists.
 */
export function aggregateByDay(
  response: EndpointUptimeResponse | null | undefined,
  days = 30,
  now: Date = new Date()
): DayCell[] {
  const cells: DayCell[] = [];

  const todayMidnight = utcMidnight(now);
  const dayKeys: string[] = [];
  for (let index = days - 1; index >= 0; index--) {
    const d = new Date(todayMidnight);
    d.setUTCDate(d.getUTCDate() - index);
    dayKeys.push(utcDateKey(d));
  }

  const grouped = new Map<string, UptimeBucket[]>();
  if (response) {
    for (const b of response.buckets) {
      const d = new Date(b.bucket_start);
      const key = utcDateKey(d);
      const array = grouped.get(key);
      if (array) array.push(b);
      else grouped.set(key, [b]);
    }
  }

  const bucketSeconds = response?.bucket_seconds ?? 1800;

  for (const key of dayKeys) {
    const dayBuckets = grouped.get(key) ?? [];
    const samples = dayBuckets.reduce((s, b) => s + b.samples, 0);
    const healthy = dayBuckets.reduce((s, b) => s + b.healthy_samples, 0);

    let downtime = 0;
    let minPct: number | null = null;
    for (const b of dayBuckets) {
      if (b.samples === 0) continue;
      downtime += bucketSeconds * ((b.samples - b.healthy_samples) / b.samples);
      minPct = minPct === null ? b.uptime_pct : Math.min(minPct, b.uptime_pct);
    }
    const meanPct = samples > 0 ? (100 * healthy) / samples : null;

    const parts = key.split('-');
    const y = Number(parts[0]);
    const m = Number(parts[1]);
    const d = Number(parts[2]);
    cells.push({
      date: new Date(Date.UTC(y, m - 1, d)),
      dateKey: key,
      samples,
      healthy_samples: healthy,
      downtime_seconds: downtime,
      mean_uptime_pct: meanPct,
      min_uptime_pct: minPct,
      incident_count: countIncidents(dayBuckets),
      status: classifyDay(minPct, samples)
    });
  }

  return cells;
}

/**
 * Compute window-wide summary stats. Returns null uptime_pct when no
 * samples have been recorded (so the UI can show "—" instead of "NaN%").
 */
export function summarize(response: EndpointUptimeResponse | null | undefined): UptimeSummary {
  if (!response || response.buckets.length === 0) {
    return {
      uptime_pct: null,
      downtime_seconds: 0,
      incident_count: 0,
      total_samples: 0,
      total_healthy: 0
    };
  }

  const total_samples = response.buckets.reduce((s, b) => s + b.samples, 0);
  const total_healthy = response.buckets.reduce((s, b) => s + b.healthy_samples, 0);

  let downtime_seconds = 0;
  for (const b of response.buckets) {
    if (b.samples === 0) continue;
    downtime_seconds += response.bucket_seconds * ((b.samples - b.healthy_samples) / b.samples);
  }

  return {
    uptime_pct: total_samples > 0 ? (100 * total_healthy) / total_samples : null,
    downtime_seconds,
    incident_count: countIncidents(response.buckets),
    total_samples,
    total_healthy
  };
}

/**
 * Compact human duration: "4h 12m", "37m", "12s", "0s".
 *
 * Drops smaller units when larger ones dominate. Designed for stat cards
 * where the value should read at a glance, not for precise timestamps.
 */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total === 0) return '0s';
  if (total < 60) return `${total}s`;

  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);

  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h ${minutes}m`;
}
