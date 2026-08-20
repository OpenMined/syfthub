import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useResendCooldown } from '@/hooks/use-resend-cooldown';

describe('useResendCooldown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts ready and blocks after start()', () => {
    const { result } = renderHook(() => useResendCooldown(60));

    expect(result.current.remaining).toBe(0);
    expect(result.current.isCoolingDown).toBe(false);

    act(() => {
      result.current.start();
    });

    expect(result.current.remaining).toBe(60);
    expect(result.current.isCoolingDown).toBe(true);
  });

  it('counts down and becomes ready again', () => {
    const { result } = renderHook(() => useResendCooldown(3));

    act(() => {
      result.current.start();
    });

    // One second per act: each tick is scheduled by an effect that only
    // re-registers once React has flushed the previous state update, so a single
    // bulk advance would fire just the first timeout.
    for (let index = 0; index < 3; index++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }

    expect(result.current.remaining).toBe(0);
    expect(result.current.isCoolingDown).toBe(false);
  });

  it('reset() clears an active countdown', () => {
    const { result } = renderHook(() => useResendCooldown(60));

    act(() => {
      result.current.start();
    });
    act(() => {
      result.current.reset();
    });

    expect(result.current.isCoolingDown).toBe(false);
  });

  it('keeps a stable identity across unrelated re-renders', () => {
    // Regression: returning a fresh object every render made this unusable as a
    // useEffect dependency — the effect re-ran on every render, and a body that
    // triggered a render looped until React bailed with "Maximum update depth
    // exceeded".
    const { result, rerender } = renderHook(() => useResendCooldown(60));

    const first = result.current;
    rerender();
    rerender();

    expect(result.current).toBe(first);
  });

  it('keeps start and reset stable even as the countdown ticks', () => {
    const { result } = renderHook(() => useResendCooldown(3));
    const { start, reset } = result.current;

    act(() => {
      result.current.start();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.start).toBe(start);
    expect(result.current.reset).toBe(reset);
    // The object itself does change, because `remaining` did.
    expect(result.current.remaining).toBe(2);
  });
});
