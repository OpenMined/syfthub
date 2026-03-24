"use client";

import { useState, useEffect, useRef } from "react";
import { useInView } from "./use-in-view";

interface TypewriterProps {
  text: string;
  speed?: number;
  delay?: number;
  onComplete?: () => void;
  showCursor?: boolean;
  className?: string;
  triggerOnView?: boolean;
}

export function Typewriter({
  text,
  speed = 40,
  delay = 0,
  onComplete,
  showCursor = true,
  className,
  triggerOnView = true,
}: TypewriterProps) {
  const [displayedCount, setDisplayedCount] = useState(0);
  const [cursorVisible, setCursorVisible] = useState(true);
  const [started, setStarted] = useState(!triggerOnView);
  const [ref, isInView] = useInView();
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (triggerOnView && isInView && !started) {
      setStarted(true);
    }
  }, [triggerOnView, isInView, started]);

  useEffect(() => {
    if (!started) return;

    const delayTimer = setTimeout(() => {
      if (displayedCount < text.length) {
        const timer = setTimeout(() => {
          setDisplayedCount((c) => c + 1);
        }, speed);
        return () => clearTimeout(timer);
      } else {
        onCompleteRef.current?.();
        if (showCursor) {
          const cursorTimer = setTimeout(() => {
            setCursorVisible(false);
          }, 1400);
          return () => clearTimeout(cursorTimer);
        }
      }
    }, displayedCount === 0 ? delay : 0);

    return () => clearTimeout(delayTimer);
  }, [started, displayedCount, text.length, speed, delay, showCursor]);

  return (
    <span ref={triggerOnView ? ref : undefined} className={className} style={{ position: "relative", display: "inline-block" }}>
      {/* Invisible full text to reserve space */}
      <span style={{ visibility: "hidden" }} aria-hidden="true">{text}</span>
      {/* Visible typing overlay */}
      <span style={{ position: "absolute", left: 0, top: 0 }}>
        {text.slice(0, displayedCount)}
        {showCursor && cursorVisible && (
          <span className="animate-cursor-blink">|</span>
        )}
      </span>
    </span>
  );
}
