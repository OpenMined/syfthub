/**
 * Pure utilities for the endpoint uptime tab.
 *
 * The backend exposes 30-minute buckets via
 * GET /api/v1/endpoints/{owner}/{slug}/uptime?window_hours=N, where each
 * bucket aggregates the health monitor's per-cycle decisions. These helpers
 * regroup the buckets into chart columns sized for the chosen window and
 * compute window-wide summary stats.
 *
 * All functions are pure so the math can be unit-tested without rendering.
 */

export interface UptimeBucket {
  /** ISO timestamp marking the start of the 30-min bucket. */
  bucket_start: string;
  /** Number of monitor cycles recorded in this bucket. */
  samples: number;
  /**
   * Cycles in which the Hub listed the endpoint as active, i.e. after the
   * same consecutive-failure rule that drives the Active badge. This is
   * what the chart draws.
   */
  healthy_samples: number;
  /**
   * Cycles in which the Space's own report said healthy, before smoothing.
   * Optional: older Hubs do not send it. A gap below healthy_samples means
   * short blips the Hub absorbed.
   */
  reported_healthy_samples?: number;
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

/** The windows the tab offers. Hours, so they map straight onto the API. */
export const UPTIME_WINDOWS = [24, 168, 720] as const;
export type UptimeWindowHours = (typeof UPTIME_WINDOWS)[number];

export function windowLabel(windowHours: number): string {
  if (windowHours % 24 === 0 && windowHours >= 48) return `${String(windowHours / 24)}-day`;
  return `${String(windowHours)}-hour`;
}

/**
 * One chart column: every bucket whose start falls inside [start, end).
 * Columns with no buckets keep samples = 0 so gaps in monitoring show as
 * gaps instead of silently closing up.
 */
export interface BucketGroup {
  start: Date;
  end: Date;
  samples: number;
  healthy_samples: number;
  unhealthy_samples: number;
  /** healthy / samples * 100, or null when the column has no samples. */
  uptime_pct: number | null;
}

/**
 * Column width for a window, chosen so the chart has 48 to 60 columns:
 * 30 min over a day, 3 h over a week, 12 h over a month. Never smaller
 * than the backend's own bucket, which is the finest data available.
 */
export function groupSecondsFor(windowHours: number, bucketSeconds = 1800): number {
  let seconds = 12 * 3600;
  if (windowHours <= 24) seconds = 1800;
  else if (windowHours <= 168) seconds = 3 * 3600;
  return Math.max(seconds, bucketSeconds);
}

/**
 * Regroup the response's buckets into fixed-width columns covering the
 * last `windowHours` hours up to `now`, oldest first. Columns are aligned
 * to multiples of the group width in UTC, so a 12 h column always starts
 * at 00:00 or 12:00 UTC and the last column is the one `now` falls in.
 */
export function groupBuckets(
  response: EndpointUptimeResponse | null | undefined,
  windowHours: number,
  now: Date = new Date()
): BucketGroup[] {
  const groupSeconds = groupSecondsFor(windowHours, response?.bucket_seconds ?? 1800);
  const nowSeconds = now.getTime() / 1000;
  const lastSlot = Math.floor(nowSeconds / groupSeconds);
  const firstSlot = Math.floor((nowSeconds - windowHours * 3600) / groupSeconds) + 1;

  const groups = new Map<number, BucketGroup>();
  for (let slot = firstSlot; slot <= lastSlot; slot++) {
    groups.set(slot, {
      start: new Date(slot * groupSeconds * 1000),
      end: new Date((slot + 1) * groupSeconds * 1000),
      samples: 0,
      healthy_samples: 0,
      unhealthy_samples: 0,
      uptime_pct: null
    });
  }

  for (const bucket of response?.buckets ?? []) {
    const slot = Math.floor(new Date(bucket.bucket_start).getTime() / 1000 / groupSeconds);
    const group = groups.get(slot);
    if (!group) continue;
    group.samples += bucket.samples;
    group.healthy_samples += bucket.healthy_samples;
  }

  for (const group of groups.values()) {
    group.unhealthy_samples = group.samples - group.healthy_samples;
    group.uptime_pct = group.samples > 0 ? (100 * group.healthy_samples) / group.samples : null;
  }

  return [...groups.values()];
}

export interface UptimeSummary {
  uptime_pct: number | null;
  downtime_seconds: number;
  incident_count: number;
  total_samples: number;
  total_healthy: number;
  total_unhealthy: number;
}

/**
 * A bucket is "unhealthy enough to count as an incident" when its uptime
 * dipped below 90%. Consecutive such buckets are one incident.
 */
const INCIDENT_THRESHOLD_PCT = 90;

export function utcDateKey(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${String(y)}-${m}-${day}`;
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
      total_healthy: 0,
      total_unhealthy: 0
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
    total_healthy,
    total_unhealthy: total_samples - total_healthy
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
  if (total < 60) return `${String(total)}s`;

  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);

  if (hours === 0) return `${String(minutes)}m`;
  if (minutes === 0) return `${String(hours)}h`;
  return `${String(hours)}h ${String(minutes)}m`;
}
