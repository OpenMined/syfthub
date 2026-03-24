"use client";

import { useState, useEffect, useRef } from "react";
import { useInView } from "./use-in-view";

interface StreamingTextProps {
  text: string;
  groupSize?: number;
  intervalMs?: number;
  delay?: number;
  className?: string;
  onComplete?: () => void;
}

export function StreamingText({
  text,
  groupSize = 2,
  intervalMs = 80,
  delay = 0,
  className,
  onComplete,
}: StreamingTextProps) {
  const words = text.split(" ");
  const [visibleWordCount, setVisibleWordCount] = useState(0);
  const [started, setStarted] = useState(false);
  const [ref, isInView] = useInView();
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (isInView && !started) {
      const timer = setTimeout(() => setStarted(true), delay);
      return () => clearTimeout(timer);
    }
  }, [isInView, started, delay]);

  useEffect(() => {
    if (!started) return;
    if (visibleWordCount >= words.length) {
      onCompleteRef.current?.();
      return;
    }

    const timer = setTimeout(() => {
      setVisibleWordCount((c) => Math.min(c + groupSize, words.length));
    }, intervalMs);

    return () => clearTimeout(timer);
  }, [started, visibleWordCount, words.length, groupSize, intervalMs]);

  return (
    <span ref={ref} className={className}>
      {words.map((word, i) => (
        <span
          key={i}
          style={{
            opacity: i < visibleWordCount ? 1 : 0,
            transition: "opacity 0.15s ease-out",
          }}
        >
          {word}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
}
