"use client";

import { useState, useEffect, useRef } from "react";
import { useInView } from "./use-in-view";

interface CountUpProps {
  target: number;
  duration?: number;
  formatter?: (n: number) => string;
  className?: string;
}

export function CountUp({
  target,
  duration = 1200,
  formatter = (n: number) => Math.round(n).toLocaleString(),
  className,
}: CountUpProps) {
  const [displayValue, setDisplayValue] = useState(formatter(0));
  const [ref, isInView] = useInView();
  const animating = useRef(false);

  useEffect(() => {
    if (!isInView || animating.current) return;
    animating.current = true;

    const start = performance.now();
    let rafId: number;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * target;
      setDisplayValue(formatter(current));

      if (progress < 1) {
        rafId = requestAnimationFrame(tick);
      }
    }

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [isInView, target, duration, formatter]);

  return (
    <span ref={ref} className={className} style={{ fontVariantNumeric: "tabular-nums", position: "relative", display: "inline-block" }}>
      {/* Reserve space for final value */}
      <span style={{ visibility: "hidden" }} aria-hidden="true">{formatter(target)}</span>
      <span style={{ position: "absolute", left: 0, top: 0 }}>{displayValue}</span>
    </span>
  );
}
