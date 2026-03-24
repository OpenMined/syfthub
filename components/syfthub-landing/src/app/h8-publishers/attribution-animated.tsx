"use client";

import { useState } from "react";
import { BrowserFrame } from "@/components/mockups/browser-frame";
import { useInView } from "@/components/animations/use-in-view";
import { Typewriter } from "@/components/animations/typewriter";
import { StreamingText } from "@/components/animations/streaming-text";

export function AttributionAnimated() {
  const [ref, isInView] = useInView();
  const [phase, setPhase] = useState<
    "idle" | "typing" | "streaming" | "citations" | "source"
  >("idle");

  if (isInView && phase === "idle") {
    setPhase("typing");
  }

  const past = (target: string) => {
    const order = ["idle", "typing", "streaming", "citations", "source"];
    return order.indexOf(phase) >= order.indexOf(target);
  };

  return (
    <section className="px-6 py-20">
      <div className="mx-auto max-w-3xl" ref={ref}>
        <h2 className="text-center font-serif text-2xl text-gray-900">
          Every answer cites you
        </h2>

        <div
          className="mt-10"
          style={{
            opacity: isInView ? 1 : 0,
            transition: "opacity 0.5s ease-out",
          }}
        >
          <BrowserFrame url="syfthub.com/query/@yourname">
            <div className="p-6 md:p-8">
              {/* Query */}
              <div className="rounded-lg bg-gray-50 px-4 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  Query
                </p>
                <div className="mt-1 text-sm text-gray-700">
                  {phase === "idle" ? (
                    <span className="text-gray-400">Ask a question...</span>
                  ) : (
                    <Typewriter
                      text="What are the main failure modes in distributed consensus?"
                      speed={25}
                      onComplete={() =>
                        setTimeout(() => setPhase("streaming"), 300)
                      }
                      showCursor={phase === "typing"}
                      triggerOnView={false}
                    />
                  )}
                </div>
              </div>

              {/* Response — always in DOM */}
              <div
                className="mt-5"
                style={{
                  opacity: past("streaming") ? 1 : 0,
                  transform: past("streaming") ? "translateY(0)" : "translateY(6px)",
                  transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
                }}
              >
                <StreamingText
                  text="Distributed consensus protocols primarily fail through three mechanisms: network partitions that prevent quorum formation, Byzantine faults where nodes provide conflicting information to different peers, and liveness failures where the system sacrifices availability to maintain consistency. In practice, most production outages stem from partial partitions rather than clean network splits."
                  groupSize={3}
                  intervalMs={60}
                  className="text-sm leading-relaxed text-gray-700"
                  onComplete={() =>
                    setTimeout(() => setPhase("citations"), 400)
                  }
                />
              </div>

              {/* Citations — always in DOM */}
              <div
                className="mt-6 border-t border-gray-100 pt-4"
                style={{
                  opacity: past("citations") ? 1 : 0,
                  transform: past("citations") ? "translateY(0)" : "translateY(4px)",
                  transition: "opacity 0.4s ease-out 0.1s, transform 0.4s ease-out 0.1s",
                }}
              >
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  Sources from @elena-researcher
                </p>
                <div className="mt-3 space-y-1.5">
                  {[
                    "\u2192 \u2018Why Distributed Systems Fail\u2019 (2024) \u2014 Chapter 3",
                    "\u2192 \u2018Consensus Under Partition\u2019 \u2014 Newsletter, Issue #47",
                    "\u2192 \u2018CAP Theorem Revisited\u2019 \u2014 Research paper, p.12-15",
                  ].map((cite, i) => (
                    <p
                      key={i}
                      className="text-sm text-amber-700 underline decoration-amber-300 underline-offset-2"
                      style={{
                        opacity: past("citations") ? 1 : 0,
                        transition: `opacity 0.3s ease-out ${i * 250}ms`,
                      }}
                    >
                      {cite}
                    </p>
                  ))}
                </div>
                <p
                  className="mt-4 text-sm text-amber-600"
                  style={{
                    opacity: past("source") ? 1 : 0,
                    transition: "opacity 0.4s ease-out",
                  }}
                  onTransitionEnd={() => {
                    if (phase === "citations") {
                      setTimeout(() => setPhase("source"), 600);
                    }
                  }}
                >
                  Source: @elena-researcher &middot; 3 citations
                </p>
              </div>
            </div>
          </BrowserFrame>
        </div>
      </div>
    </section>
  );
}
