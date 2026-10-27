import type { EndpointUptimeResponse, UptimeBucket } from '../uptime';

import { describe, expect, it } from 'vitest';

import {
  countIncidents,
  formatDuration,
  groupBuckets,
  groupSecondsFor,
  summarize,
  utcDateKey,
  windowLabel
} from '../uptime';

function bucket(bucket_start: string, samples: number, healthy_samples: number): UptimeBucket {
  return {
    bucket_start,
    samples,
    healthy_samples,
    uptime_pct: samples > 0 ? (100 * healthy_samples) / samples : 0
  };
}

function response(buckets: UptimeBucket[], window_hours = 720): EndpointUptimeResponse {
  return {
    endpoint_id: 1,
    owner_username: 'alice',
    slug: 'demo',
    bucket_seconds: 1800,
    window_hours,
    buckets
  };
}

// A fixed "now" on a 12 h boundary so slot counts are exact.
const fixedNow = new Date('2026-05-13T12:00:00Z');

// ----------------------------------------------------------------------------
// groupSecondsFor / windowLabel
// ----------------------------------------------------------------------------

describe('groupSecondsFor', () => {
  it('uses 30-minute columns for a day', () => {
    expect(groupSecondsFor(24)).toBe(1800);
  });

  it('uses 3-hour columns for a week', () => {
    expect(groupSecondsFor(168)).toBe(3 * 3600);
  });

  it('uses 12-hour columns for a month', () => {
    expect(groupSecondsFor(720)).toBe(12 * 3600);
  });

  it('never goes below the backend bucket size', () => {
    expect(groupSecondsFor(24, 3600)).toBe(3600);
  });
});

describe('windowLabel', () => {
  it('names day windows in days and short windows in hours', () => {
    expect(windowLabel(720)).toBe('30-day');
    expect(windowLabel(168)).toBe('7-day');
    expect(windowLabel(24)).toBe('24-hour');
  });
});

// ----------------------------------------------------------------------------
// groupBuckets
// ----------------------------------------------------------------------------

describe('groupBuckets', () => {
  it('returns one column per slot ending at now', () => {
    const groups = groupBuckets(response([]), 24, fixedNow);
    expect(groups).toHaveLength(48);
    expect(groups[0]?.start.toISOString()).toBe('2026-05-12T12:30:00.000Z');
    expect(groups.at(-1)?.start.toISOString()).toBe('2026-05-13T12:00:00.000Z');
  });

  it('sums buckets that fall into the same column', () => {
    const r = response([
      bucket('2026-05-13T00:00:00Z', 60, 60),
      bucket('2026-05-13T00:30:00Z', 60, 50),
      bucket('2026-05-13T11:30:00Z', 60, 60)
    ]);
    const groups = groupBuckets(r, 720, fixedNow);
    const morning = groups.find((g) => g.start.toISOString() === '2026-05-13T00:00:00.000Z');
    expect(morning?.samples).toBe(180);
    expect(morning?.healthy_samples).toBe(170);
    expect(morning?.unhealthy_samples).toBe(10);
    expect(morning?.uptime_pct).toBeCloseTo(94.44, 1);
  });

  it('keeps empty columns so monitoring gaps stay visible', () => {
    const r = response([bucket('2026-05-13T11:30:00Z', 60, 60)]);
    const groups = groupBuckets(r, 24, fixedNow);
    const empty = groups.filter((g) => g.samples === 0);
    expect(empty).toHaveLength(47);
    expect(empty[0]?.uptime_pct).toBeNull();
  });

  it('drops buckets outside the window', () => {
    const r = response([bucket('2026-05-11T00:00:00Z', 60, 60)]);
    const groups = groupBuckets(r, 24, fixedNow);
    expect(groups.every((g) => g.samples === 0)).toBe(true);
  });

  it('handles a missing response', () => {
    expect(groupBuckets(null, 24, fixedNow)).toHaveLength(48);
  });
});

// ----------------------------------------------------------------------------
// countIncidents
// ----------------------------------------------------------------------------

describe('countIncidents', () => {
  it('counts a single isolated dip', () => {
    expect(
      countIncidents([
        bucket('2026-05-13T00:00:00Z', 60, 60),
        bucket('2026-05-13T00:30:00Z', 60, 30),
        bucket('2026-05-13T01:00:00Z', 60, 60)
      ])
    ).toBe(1);
  });

  it('collapses consecutive bad buckets into one incident', () => {
    expect(
      countIncidents([
        bucket('2026-05-13T00:00:00Z', 60, 30),
        bucket('2026-05-13T00:30:00Z', 60, 20),
        bucket('2026-05-13T01:00:00Z', 60, 10)
      ])
    ).toBe(1);
  });

  it('counts separated bad buckets as separate incidents', () => {
    expect(
      countIncidents([
        bucket('2026-05-13T00:00:00Z', 60, 30),
        bucket('2026-05-13T00:30:00Z', 60, 60),
        bucket('2026-05-13T01:00:00Z', 60, 10)
      ])
    ).toBe(2);
  });

  it('ignores empty buckets when counting streaks', () => {
    expect(
      countIncidents([
        bucket('2026-05-13T00:00:00Z', 60, 30),
        bucket('2026-05-13T00:30:00Z', 0, 0),
        bucket('2026-05-13T01:00:00Z', 60, 10)
      ])
    ).toBe(1);
  });
});

// ----------------------------------------------------------------------------
// summarize
// ----------------------------------------------------------------------------

describe('summarize', () => {
  it('returns nulls/zeros for empty input', () => {
    expect(summarize(null)).toEqual({
      uptime_pct: null,
      downtime_seconds: 0,
      incident_count: 0,
      total_samples: 0,
      total_healthy: 0,
      total_unhealthy: 0
    });
    expect(summarize(response([])).uptime_pct).toBeNull();
  });

  it('computes overall uptime_pct as healthy / total', () => {
    const s = summarize(
      response([bucket('2026-05-13T00:00:00Z', 60, 60), bucket('2026-05-13T00:30:00Z', 60, 30)])
    );
    expect(s.uptime_pct).toBeCloseTo(75, 5);
    expect(s.total_samples).toBe(120);
    expect(s.total_healthy).toBe(90);
    expect(s.total_unhealthy).toBe(30);
  });

  it('computes downtime_seconds from missed samples × bucket_seconds', () => {
    const s = summarize(
      response([bucket('2026-05-13T00:00:00Z', 60, 30), bucket('2026-05-13T00:30:00Z', 60, 60)])
    );
    // half of one 1800 s bucket
    expect(s.downtime_seconds).toBeCloseTo(900, 5);
    expect(s.incident_count).toBe(1);
  });
});

// ----------------------------------------------------------------------------
// formatDuration / utcDateKey
// ----------------------------------------------------------------------------

describe('formatDuration', () => {
  it('renders 0s for zero', () => {
    expect(formatDuration(0)).toBe('0s');
  });

  it('renders seconds below a minute', () => {
    expect(formatDuration(42)).toBe('42s');
  });

  it('renders minutes below an hour', () => {
    expect(formatDuration(37 * 60 + 12)).toBe('37m');
  });

  it('renders hours without minutes when minutes is 0', () => {
    expect(formatDuration(2 * 3600)).toBe('2h');
  });

  it('combines hours and minutes', () => {
    expect(formatDuration(4 * 3600 + 12 * 60)).toBe('4h 12m');
  });

  it('clamps negative input to 0', () => {
    expect(formatDuration(-5)).toBe('0s');
  });
});

describe('utcDateKey', () => {
  it('uses UTC midnight, not local', () => {
    expect(utcDateKey(new Date('2026-05-13T23:30:00Z'))).toBe('2026-05-13');
    expect(utcDateKey(new Date('2026-05-14T00:30:00Z'))).toBe('2026-05-14');
  });
});
