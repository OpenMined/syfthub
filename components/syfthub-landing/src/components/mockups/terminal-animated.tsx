"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useInView } from "@/components/animations/use-in-view";

interface TerminalLine {
  prompt?: boolean;
  text: string;
  /** Plain command to type (without comments/HTML). If omitted, types the full stripped text. */
  typingText?: string;
  dimmed?: boolean;
}

interface TerminalAnimatedProps {
  lines: TerminalLine[];
  title?: string;
  typingSpeed?: number;
  lineDelay?: number;
  startDelay?: number;
}

/** Strip HTML tags and decode common entities to get plain text for typing */
function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, "\u00A0")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#10003;/g, "\u2713")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

interface AnimState {
  lineVisible: boolean[];
  lineComplete: boolean[];
  typedCount: number[];
  cursorLine: number; // -1 = final cursor, -2 = no cursor yet
  done: boolean;
}

export function TerminalAnimated({
  lines,
  title = "Terminal",
  typingSpeed = 30,
  lineDelay = 300,
  startDelay = 0,
}: TerminalAnimatedProps) {
  const [viewRef, isInView] = useInView();
  const [, setTick] = useState(0);
  const rerender = useCallback(() => setTick((t) => t + 1), []);

  const plainTexts = useMemo(
    () => lines.map((l) => (l.prompt ? (l.typingText ?? stripHtml(l.text)) : l.text)),
    [lines]
  );

  const stateRef = useRef<AnimState>({
    lineVisible: lines.map(() => false),
    lineComplete: lines.map(() => false),
    typedCount: lines.map(() => 0),
    cursorLine: -2,
    done: false,
  });

  const cancelledRef = useRef(false);
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!isInView || startedRef.current) return;
    startedRef.current = true;
    cancelledRef.current = false;

    function wait(ms: number): Promise<void> {
      return new Promise((resolve) => {
        timeoutIdRef.current = setTimeout(() => {
          if (!cancelledRef.current) resolve();
        }, ms);
      });
    }

    async function run() {
      const s = stateRef.current;

      await wait(startDelay);
      if (cancelledRef.current) return;

      for (let i = 0; i < lines.length; i++) {
        if (cancelledRef.current) return;

        const line = lines[i];
        const plain = plainTexts[i];

        // Make line visible
        s.lineVisible[i] = true;

        if (line.prompt) {
          // Show cursor on this line
          s.cursorLine = i;
          rerender();

          // Type each character
          for (let c = 0; c < plain.length; c++) {
            if (cancelledRef.current) return;
            await wait(typingSpeed);
            if (cancelledRef.current) return;
            s.typedCount[i] = c + 1;
            rerender();
          }

          // Typing done — show full HTML version
          s.lineComplete[i] = true;
          s.cursorLine = -2; // hide cursor during delay
          rerender();

          // Pause before next line
          await wait(lineDelay);
          if (cancelledRef.current) return;
        } else {
          // Output line — appear instantly
          s.lineComplete[i] = true;
          rerender();

          // Short pause (empty lines get minimal delay)
          await wait(line.text === "" ? 50 : lineDelay);
          if (cancelledRef.current) return;
        }
      }

      // Animation complete — show final cursor
      s.cursorLine = -1;
      s.done = true;
      rerender();
    }

    run();

    return () => {
      cancelledRef.current = true;
      if (timeoutIdRef.current) clearTimeout(timeoutIdRef.current);
    };
  }, [isInView, lines, plainTexts, typingSpeed, lineDelay, startDelay, rerender]);

  const s = stateRef.current;

  return (
    <div
      ref={viewRef}
      className="w-full overflow-hidden rounded-xl border border-gray-200 bg-gray-950 shadow-2xl dark:border-gray-800"
    >
      {/* Title bar */}
      <div className="flex items-center gap-2 border-b border-gray-800 px-4 py-3">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/80" />
          <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
          <div className="h-3 w-3 rounded-full bg-green-500/80" />
        </div>
        <span className="ml-2 text-xs text-gray-500 font-mono">{title}</span>
      </div>

      {/* Content — all lines pre-rendered for stable height */}
      <div className="p-5 font-mono text-sm leading-7">
        {lines.map((line, i) => {
          const visible = s.lineVisible[i];
          const complete = s.lineComplete[i];
          const typed = s.typedCount[i];
          const plain = plainTexts[i];
          const hasCursor = s.cursorLine === i;

          return (
            <div
              key={i}
              className={line.dimmed ? "text-gray-600" : "text-gray-300"}
              style={{ visibility: visible ? "visible" : "hidden" }}
            >
              {line.prompt && (
                <span className="text-green-400 mr-2">$</span>
              )}
              {line.prompt ? (
                complete ? (
                  <span dangerouslySetInnerHTML={{ __html: line.text }} />
                ) : (
                  <span>
                    {plain.slice(0, typed)}
                    {hasCursor && (
                      <span className="inline-block h-4 w-2 bg-green-400 animate-cursor-blink ml-0.5" />
                    )}
                  </span>
                )
              ) : (
                <span dangerouslySetInnerHTML={{ __html: line.text }} />
              )}
            </div>
          );
        })}

        {/* Final blinking cursor after all lines complete */}
        {s.done && (
          <span className="inline-block h-4 w-2 bg-green-400 animate-cursor-blink" />
        )}
      </div>
    </div>
  );
}
