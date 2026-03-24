"use client";

import { useState } from "react";
import { BrowserFrame } from "@/components/mockups/browser-frame";
import { useInView } from "@/components/animations/use-in-view";
import { Typewriter } from "@/components/animations/typewriter";
import { StreamingText } from "@/components/animations/streaming-text";

export function ClientMockupAnimated() {
  const [ref, isInView] = useInView();
  const [phase, setPhase] = useState<
    "idle" | "focus" | "typing" | "streaming" | "checkmark"
  >("idle");

  if (isInView && phase === "idle") {
    setPhase("focus");
    setTimeout(() => setPhase("typing"), 400);
  }

  const past = (target: string) => {
    const order = ["idle", "focus", "typing", "streaming", "checkmark"];
    return order.indexOf(phase) >= order.indexOf(target);
  };

  return (
    <section className="bg-white px-6 py-20">
      <div className="mx-auto max-w-3xl" ref={ref}>
        <h2 className="mb-8 text-2xl font-semibold text-gray-900">
          What your client sees
        </h2>
        <div
          style={{
            opacity: isInView ? 1 : 0,
            transition: "opacity 0.5s ease-out",
          }}
        >
          <BrowserFrame url="query.syfthub.com/acme-engagement">
            <div className="p-6 md:p-8">
              <div className="mb-6 text-sm font-medium text-gray-900">
                ACME Analytics — Secure Query
              </div>
              <div
                className={`rounded-lg border px-4 py-3 transition-all duration-300 ${
                  phase === "focus"
                    ? "border-blue-400 ring-2 ring-blue-100"
                    : "border-gray-200"
                } ${
                  phase === "idle" ? "text-gray-400" : "text-gray-700"
                }`}
              >
                {phase === "idle" && "Ask a question about the dataset..."}
                {phase === "focus" && (
                  <span className="animate-cursor-blink text-gray-400">|</span>
                )}
                {past("typing") && phase !== "idle" && phase !== "focus" && (
                  <Typewriter
                    text="What were the top 3 revenue drivers in Q3?"
                    speed={30}
                    onComplete={() =>
                      setTimeout(() => setPhase("streaming"), 300)
                    }
                    showCursor={phase === "typing"}
                    triggerOnView={false}
                    className="text-sm font-medium text-gray-500"
                  />
                )}
              </div>

              {/* Response area — always in DOM */}
              <div
                className="mt-8 border-t border-gray-100 pt-6"
                style={{
                  opacity: past("streaming") ? 1 : 0,
                  transform: past("streaming") ? "translateY(0)" : "translateY(6px)",
                  transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
                }}
              >
                <div className="space-y-2 text-sm leading-relaxed text-gray-700">
                  <StreamingText
                    text="Based on the Q3 dataset, the top three revenue drivers were:"
                    groupSize={3}
                    intervalMs={60}
                    onComplete={() => {}}
                  />
                  <p
                    className="pl-4"
                    style={{
                      opacity: past("checkmark") ? 1 : 0,
                      transition: "opacity 0.5s ease-out",
                    }}
                  >
                    1. Enterprise license renewals ($4.2M, +18% QoQ)
                    <br />
                    2. Platform usage-based billing ($2.8M, +31% QoQ)
                    <br />
                    3. Professional services engagements ($1.6M, +12% QoQ)
                  </p>
                  <StreamingText
                    text="Enterprise renewals accounted for 48% of total Q3 revenue, with the strongest growth in the EMEA region."
                    groupSize={3}
                    intervalMs={60}
                    delay={1200}
                    onComplete={() =>
                      setTimeout(() => setPhase("checkmark"), 400)
                    }
                  />
                </div>

                {/* Security checkmark — always in DOM */}
                <div
                  className="mt-6 flex items-center gap-1.5 text-xs text-green-700"
                  style={{
                    opacity: past("checkmark") ? 1 : 0,
                    transform: past("checkmark") ? "translateY(0)" : "translateY(4px)",
                    transition: "opacity 0.3s ease-out, transform 0.3s ease-out",
                  }}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    className={`inline-block text-green-600 ${past("checkmark") ? "draw-on-icon" : ""}`}
                  >
                    <path
                      d="M3 7l3 3 5-5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span>
                    Data accessed securely. Raw data has not been
                    transferred.
                  </span>
                </div>
              </div>
            </div>
          </BrowserFrame>
        </div>
      </div>
    </section>
  );
}
