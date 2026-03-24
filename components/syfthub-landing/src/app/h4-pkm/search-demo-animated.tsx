"use client";

import { useState } from "react";
import { useInView } from "@/components/animations/use-in-view";
import { Typewriter } from "@/components/animations/typewriter";

const citations = [
  {
    icon: "\u{1F4C4}",
    file: "distributed-systems/consensus-protocols.md",
    line: 45,
  },
  {
    icon: "\u{1F4C4}",
    file: "reading-notes/designing-data-intensive-apps.md",
    line: 112,
  },
  {
    icon: "\u{1F4C4}",
    file: "weekly-reviews/2024-Q4-review.md",
    line: 23,
  },
];

export function SearchDemoAnimated() {
  const [ref, isInView] = useInView();
  const [phase, setPhase] = useState<
    "idle" | "typing" | "thinking" | "response" | "citations"
  >("idle");

  if (isInView && phase === "idle") {
    setPhase("typing");
  }

  const handleTypingComplete = () => {
    setPhase("thinking");
    setTimeout(() => setPhase("response"), 500);
  };

  const handleResponseShown = () => {
    setTimeout(() => setPhase("citations"), 300);
  };

  const showResponse = phase === "response" || phase === "citations";
  const showThinking = phase === "thinking";

  return (
    <section className="py-20">
      <div className="mx-auto max-w-2xl px-6" ref={ref}>
        <h2 className="mb-10 text-center text-2xl font-semibold text-white">
          Search like you think
        </h2>

        {/* Search input mockup */}
        <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-900 px-4 py-3">
          <span className="flex-1 font-mono text-sm text-gray-300">
            {phase === "idle" ? (
              <span className="text-gray-600">Ask anything...</span>
            ) : (
              <Typewriter
                text="What were my key insights about distributed systems from Q4?"
                speed={35}
                onComplete={handleTypingComplete}
                showCursor={phase === "typing"}
                triggerOnView={false}
              />
            )}
          </span>
          <button className="shrink-0 rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white">
            Search
          </button>
        </div>

        {/* Response card — always in DOM to reserve space */}
        <div className="mt-4 rounded-lg border border-gray-800 bg-gray-900 p-6"
          style={{
            opacity: showThinking || showResponse ? 1 : 0,
            transform: showThinking || showResponse ? "translateY(0)" : "translateY(8px)",
            transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
          }}
        >
          {/* Thinking indicator */}
          <div
            style={{
              height: showThinking ? "auto" : 0,
              opacity: showThinking ? 1 : 0,
              overflow: "hidden",
              transition: "opacity 0.3s ease-out",
            }}
          >
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-purple-400 animate-pulse-soft" />
              <span
                className="h-2 w-2 rounded-full bg-purple-400 animate-pulse-soft"
                style={{ animationDelay: "200ms" }}
              />
              <span
                className="h-2 w-2 rounded-full bg-purple-400 animate-pulse-soft"
                style={{ animationDelay: "400ms" }}
              />
              <span className="ml-2 text-xs text-gray-500">
                Searching your vault...
              </span>
            </div>
          </div>

          {/* Response text */}
          <div
            style={{
              opacity: showResponse ? 1 : 0,
              transition: "opacity 0.4s ease-out",
            }}
            onTransitionEnd={() => {
              if (showResponse && phase === "response") handleResponseShown();
            }}
          >
            <p className="text-sm leading-relaxed text-gray-300">
              Your Q4 notes highlight three main insights: (1) Raft consensus is
              preferred over Paxos for practical implementations due to its
              understandability, (2) CRDTs eliminate coordination overhead for
              eventually-consistent workloads, and (3) your team&apos;s
              migration to event sourcing reduced write contention by 40%.
            </p>

            {/* Citations */}
            <div
              className="mt-5 border-t border-gray-800 pt-4"
              style={{
                opacity: phase === "citations" ? 1 : 0,
                transform: phase === "citations" ? "translateY(0)" : "translateY(4px)",
                transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
              }}
            >
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                Sources
              </p>
              <div className="space-y-1.5">
                {citations.map((c, i) => (
                  <p
                    key={i}
                    className="font-mono text-base text-purple-400"
                    style={{
                      opacity: phase === "citations" ? 1 : 0,
                      transform: phase === "citations" ? "translateY(0)" : "translateY(4px)",
                      transition: `opacity 0.3s ease-out ${i * 200}ms, transform 0.3s ease-out ${i * 200}ms`,
                    }}
                  >
                    {c.icon}{" "}
                    <span className="underline decoration-purple-400/30 underline-offset-2">
                      {c.file}
                    </span>
                    <span className="text-gray-500"> — line {c.line}</span>
                  </p>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
