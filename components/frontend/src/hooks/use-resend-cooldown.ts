import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Countdown that throttles "resend code" buttons.
 *
 * Extracted so every OTP surface (registration, email change) shares one
 * implementation rather than each keeping its own timer.
 *
 * Uses a setTimeout chain rather than setInterval so the effect is not
 * re-registered on every tick.
 *
 * @param seconds - How long to block resending after each send. Default 60.
 */
export function useResendCooldown(seconds = 60) {
  const [remaining, setRemaining] = useState(0);
  const timerReference = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (remaining <= 0) return;
    timerReference.current = setTimeout(() => {
      setRemaining((previous) => previous - 1);
    }, 1000);
    return () => {
      if (timerReference.current) clearTimeout(timerReference.current);
    };
  }, [remaining]);

  const start = useCallback(() => {
    setRemaining(seconds);
  }, [seconds]);

  const reset = useCallback(() => {
    setRemaining(0);
  }, []);

  // Memoised so the identity only changes when the countdown does. Returning a
  // fresh object every render makes this unusable as a `useEffect` dependency:
  // the effect re-runs on every render, and if its body triggers one — a
  // react-hook-form `reset()`, say — that is an infinite loop.
  return useMemo(
    () => ({
      /** Seconds left before another send is allowed; 0 when ready. */
      remaining,
      /** True while a resend must be blocked. */
      isCoolingDown: remaining > 0,
      /** Begin the countdown — call after a successful send. */
      start,
      /** Clear the countdown, e.g. when the surface is dismissed. */
      reset
    }),
    [remaining, start, reset]
  );
}
