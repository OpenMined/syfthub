import type { EndpointUptimeResponse, UptimeBucket } from '../uptime';

import { describe, expect, it } from 'vitest';

import {
  aggregateByDay,
  classifyDay,
  countIncidents,
  formatDuration,
  summarize,
  utcDateKey
} from '../uptime';

function bucket(bucket_start: string, samples: number, healthy_samples: number): UptimeBucket {
  return {
    bucket_start,
    samples,
    healthy_samples,
    uptime_pct: samples > 0 ? (100 * healthy_samples) / samples : 0
  };
}

function response(buckets: UptimeBucket[]): EndpointUptimeResponse {
  return {
    endpoint_id: 1,
    owner_username: 'alice',
    slug: 'demo',
    bucket_seconds: 1800,
    window_hours: 720,
    buckets
  };
}

// ----------------------------------------------------------------------------
// classifyDay
// ----------------------------------------------------------------------------

describe('classifyDay', () => {
  it('returns no-data when samples is 0', () => {
    expect(classifyDay(100, 0)).toBe('no-data');
  });

  it('returns no-data when min_uptime_pct is null', () => {
    expect(classifyDay(null, 10)).toBe('no-data');
  });

  it('returns operational at or above 99', () => {
    expect(classifyDay(99, 10)).toBe('operational');
    expect(classifyDay(100, 10)).toBe('operational');
  });

  it('returns degraded between 90 and 99', () => {
    expect(classifyDay(95, 10)).toBe('degraded');
    expect(classifyDay(90, 10)).toBe('degraded');
  });

  it('returns down below 90', () => {
    expect(classifyDay(89.9, 10)).toBe('down');
    expect(classifyDay(0, 10)).toBe('down');
  });
});

// ----------------------------------------------------------------------------
// countIncidents
// ----------------------------------------------------------------------------

describe('countIncidents', () => {
  it('counts a single isolated dip', () => {
    expect(
      countIncidents([
        bucket('2026-05-01T00:00:00Z', 60, 60),
        bucket('2026-05-01T00:30:00Z', 60, 30), // 50% → down
        bucket('2026-05-01T01:00:00Z', 60, 60)
      ])
    ).toBe(1);
  });

  it('collapses consecutive bad buckets into one incident', () => {
    expect(
      countIncidents([
        bucket('2026-05-01T00:00:00Z', 60, 60),
        bucket('2026-05-01T00:30:00Z', 60, 30),
        bucket('2026-05-01T01:00:00Z', 60, 10),
        bucket('2026-05-01T01:30:00Z', 60, 60)
      ])
    ).toBe(1);
  });

  it('counts separated bad buckets as separate incidents', () => {
    expect(
      countIncidents([
        bucket('2026-05-01T00:00:00Z', 60, 30),
        bucket('2026-05-01T00:30:00Z', 60, 60),
        bucket('2026-05-01T01:00:00Z', 60, 30)
      ])
    ).toBe(2);
  });

  it('ignores empty buckets when counting streaks', () => {
    // An empty bucket between two bad ones must NOT split a real incident,
    // because "no data" is not "recovered".
    expect(
      countIncidents([
        bucket('2026-05-01T00:00:00Z', 60, 30),
        bucket('2026-05-01T00:30:00Z', 0, 0),
        bucket('2026-05-01T01:00:00Z', 60, 30)
      ])
    ).toBe(1);
  });
});

// ----------------------------------------------------------------------------
// aggregateByDay
// ----------------------------------------------------------------------------

describe('aggregateByDay', () => {
  const fixedNow = new Date('2026-05-13T15:00:00Z');

  it('returns exactly N day cells covering the last N days', () => {
    const cells = aggregateByDay(response([]), 30, fixedNow);
    expect(cells).toHaveLength(30);
    expect(cells.at(-1)?.dateKey).toBe('2026-05-13'); // today
    expect(cells[0]?.dateKey).toBe('2026-04-14'); // 29 days ago
  });

  it('fills missing days with no-data cells', () => {
    const cells = aggregateByDay(response([]), 30, fixedNow);
    expect(cells.every((c) => c.status === 'no-data')).toBe(true);
    expect(cells.every((c) => c.samples === 0)).toBe(true);
  });

  it('groups buckets into their UTC day', () => {
    const r = response([
      bucket('2026-05-13T01:00:00Z', 60, 60),
      bucket('2026-05-13T22:00:00Z', 60, 30),
      bucket('2026-05-12T12:00:00Z', 60, 60)
    ]);
    const cells = aggregateByDay(r, 30, fixedNow);
    const today = cells.find((c) => c.dateKey === '2026-05-13');
    const yesterday = cells.find((c) => c.dateKey === '2026-05-12');
    expect(today?.samples).toBe(120);
    expect(today?.healthy_samples).toBe(90);
    expect(today?.status).toBe('down'); // 22:00 bucket was 50%
    expect(yesterday?.samples).toBe(60);
    expect(yesterday?.status).toBe('operational');
  });

  it('classifies a day by its worst bucket, not by its mean', () => {
    const r = response([
      bucket('2026-05-13T00:00:00Z', 60, 60),
      bucket('2026-05-13T01:00:00Z', 60, 60),
      bucket('2026-05-13T02:00:00Z', 60, 56) // ~93%
    ]);
    const cells = aggregateByDay(r, 30, fixedNow);
    const today = cells.find((c) => c.dateKey === '2026-05-13');
    expect(today?.status).toBe('degraded');
  });
});

// ----------------------------------------------------------------------------
// summarize
// ----------------------------------------------------------------------------

describe('summarize', () => {
  it('returns nulls/zeros for empty input', () => {
    const s = summarize(null);
    expect(s.uptime_pct).toBeNull();
    expect(s.downtime_seconds).toBe(0);
    expect(s.incident_count).toBe(0);
  });

  it('computes overall uptime_pct as healthy / total', () => {
    const s = summarize(
      response([bucket('2026-05-13T00:00:00Z', 60, 60), bucket('2026-05-13T00:30:00Z', 60, 30)])
    );
    expect(s.uptime_pct).toBeCloseTo(75);
  });

  it('computes downtime_seconds from missed samples × bucket_seconds', () => {
    // bucket of 60 samples, 30 healthy → 50% down × 1800s = 900s
    const s = summarize(response([bucket('2026-05-13T00:00:00Z', 60, 30)]));
    expect(s.downtime_seconds).toBe(900);
  });
});

// ----------------------------------------------------------------------------
// formatDuration
// ----------------------------------------------------------------------------

describe('formatDuration', () => {
  it('renders 0s for zero', () => {
    expect(formatDuration(0)).toBe('0s');
  });

  it('renders seconds below a minute', () => {
    expect(formatDuration(45)).toBe('45s');
  });

  it('renders minutes below an hour', () => {
    expect(formatDuration(60 * 5)).toBe('5m');
    // Minute display is floored — we count completed minutes, not rounded.
    expect(formatDuration(60 * 5 + 30)).toBe('5m');
    expect(formatDuration(60 * 6 - 1)).toBe('5m');
  });

  it('renders hours without minutes when minutes is 0', () => {
    expect(formatDuration(3600 * 2)).toBe('2h');
  });

  it('combines hours and minutes', () => {
    expect(formatDuration(3600 * 4 + 60 * 12)).toBe('4h 12m');
  });

  it('clamps negative input to 0', () => {
    expect(formatDuration(-10)).toBe('0s');
  });
});

// ----------------------------------------------------------------------------
// utcDateKey
// ----------------------------------------------------------------------------

describe('utcDateKey', () => {
  it('uses UTC midnight, not local', () => {
    expect(utcDateKey(new Date('2026-05-13T23:59:59Z'))).toBe('2026-05-13');
    expect(utcDateKey(new Date('2026-05-14T00:00:00Z'))).toBe('2026-05-14');
  });
});
