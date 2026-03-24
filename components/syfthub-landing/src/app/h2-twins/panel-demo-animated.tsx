"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useInView } from "@/components/animations/use-in-view";

const experts = [
  {
    initials: "YL",
    name: "Yann LeCun",
    avatarColor: "bg-amber-100 text-amber-700",
    nameColor: "text-amber-700",
    response:
      "Open-source models will dominate enterprise AI within three years. The competitive moat shifts from model access to data curation and deployment infrastructure.",
    source: "A Path Towards Autonomous Machine Intelligence, 2022",
  },
  {
    initials: "SA",
    name: "Sam Altman",
    avatarColor: "bg-blue-100 text-blue-700",
    nameColor: "text-blue-700",
    response:
      "Frontier capabilities will remain concentrated in scaled systems requiring billions in compute. Enterprises choosing open-source face a capability gap that widens over time.",
    source: "Planning for AGI and Beyond, OpenAI Blog, 2023",
  },
  {
    initials: "DH",
    name: "Demis Hassabis",
    avatarColor: "bg-emerald-100 text-emerald-700",
    nameColor: "text-emerald-700",
    response:
      "The framing is incomplete. Enterprise adoption depends less on open vs. closed and more on whether models demonstrate verifiable reasoning over domain-specific knowledge.",
    source: "Towards a Unified Model of Prediction and Understanding, 2023",
  },
];

const question =
  "How will open-source AI models affect enterprise adoption over the next 5 years?";

const synthesis = {
  agreements: [
    "Data quality matters more than raw model scale",
    "Trust and verifiable outputs are prerequisites for deployment",
  ],
  divergences: [
    "Whether open-source can match frontier capabilities",
    "The key bottleneck: data, compute, or scientific grounding",
  ],
};

interface AnimState {
  headerVisible: boolean;
  questionVisible: boolean;
  typingExpert: number;
  responseVisible: boolean[];
  synthesisVisible: boolean;
  done: boolean;
}

export function PanelDemoAnimated() {
  const [viewRef, isInView] = useInView({ threshold: 0.1 });
  const [tick, setTick] = useState(0);
  const rerender = useCallback(() => setTick((t) => t + 1), []);
  const chatAreaRef = useRef<HTMLDivElement>(null);

  const stateRef = useRef<AnimState>({
    headerVisible: false,
    questionVisible: false,
    typingExpert: -1,
    responseVisible: [false, false, false],
    synthesisVisible: false,
    done: false,
  });

  const cancelledRef = useRef(false);
  const startedRef = useRef(false);

  // Auto-scroll chat area to bottom after each animation step.
  // Scrolls twice: once immediately and once after the grid-template-rows
  // transition (500ms) so that expanding content is fully accounted for.
  useEffect(() => {
    if (tick === 0) return;
    const el = chatAreaRef.current;
    if (!el) return;

    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });

    const delayed = setTimeout(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }, 550);

    return () => clearTimeout(delayed);
  }, [tick]);

  useEffect(() => {
    if (!isInView || startedRef.current) return;
    startedRef.current = true;
    cancelledRef.current = false;

    const timeouts: ReturnType<typeof setTimeout>[] = [];

    function wait(ms: number): Promise<void> {
      return new Promise((resolve) => {
        const id = setTimeout(() => {
          if (!cancelledRef.current) resolve();
        }, ms);
        timeouts.push(id);
      });
    }

    async function run() {
      const s = stateRef.current;

      await wait(200);
      if (cancelledRef.current) return;
      s.headerVisible = true;
      rerender();

      await wait(500);
      if (cancelledRef.current) return;
      s.questionVisible = true;
      rerender();

      await wait(800);
      if (cancelledRef.current) return;

      for (let i = 0; i < experts.length; i++) {
        if (cancelledRef.current) return;
        s.typingExpert = i;
        rerender();

        await wait(600 + i * 100);
        if (cancelledRef.current) return;

        s.typingExpert = -1;
        s.responseVisible[i] = true;
        rerender();

        await wait(400);
        if (cancelledRef.current) return;
      }

      await wait(500);
      if (cancelledRef.current) return;
      s.synthesisVisible = true;
      s.done = true;
      rerender();
    }

    run();

    return () => {
      cancelledRef.current = true;
      timeouts.forEach(clearTimeout);
    };
  }, [isInView, rerender]);

  const s = stateRef.current;

  return (
    <div
      ref={viewRef}
      className="flex h-[480px] md:h-[540px] flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-[0_4px_32px_rgba(0,0,0,0.06)]"
    >
      {/* Chat header */}
      <div
        className="flex items-center gap-3 border-b border-stone-100 px-5 py-3.5 shrink-0 transition-all duration-500"
        style={{
          opacity: s.headerVisible ? 1 : 0,
          transform: s.headerVisible ? "translateY(0)" : "translateY(-4px)",
        }}
      >
        <div className="flex -space-x-1.5">
          {experts.map((expert) => (
            <div
              key={expert.initials}
              className={`flex h-8 w-8 items-center justify-center rounded-full text-[10px] font-bold ring-2 ring-white ${expert.avatarColor}`}
            >
              {expert.initials}
            </div>
          ))}
        </div>
        <div>
          <p className="text-[14px] font-semibold text-stone-900">
            Expert Panel
          </p>
          <p className="text-[11px] text-stone-400">3 panelists</p>
        </div>
      </div>

      {/* Chat area — scrollable, fixed height via flex-1 */}
      <div
        ref={chatAreaRef}
        className="flex-1 overflow-y-auto bg-stone-50/70 px-5 py-5"
      >
        {/* User question — right-aligned bubble */}
        <div
          style={{
            display: "grid",
            gridTemplateRows: s.questionVisible ? "1fr" : "0fr",
            transition: "grid-template-rows 0.4s ease-out",
          }}
        >
          <div style={{ overflow: "hidden" }}>
            <div className="flex justify-end mb-5">
              <div
                className="max-w-[85%] rounded-2xl rounded-br-md bg-stone-800 px-4 py-3 text-[13px] leading-relaxed text-stone-100 shadow-sm"
                style={{
                  opacity: s.questionVisible ? 1 : 0,
                  transform: s.questionVisible
                    ? "translateX(0)"
                    : "translateX(12px)",
                  transition:
                    "opacity 0.4s ease-out 0.1s, transform 0.4s ease-out 0.1s",
                }}
              >
                {question}
              </div>
            </div>
          </div>
        </div>

        {/* Expert responses */}
        {experts.map((expert, i) => (
          <div key={expert.initials}>
            {/* Typing indicator */}
            <div
              style={{
                display: "grid",
                gridTemplateRows: s.typingExpert === i ? "1fr" : "0fr",
                transition: "grid-template-rows 0.25s ease-out",
              }}
            >
              <div style={{ overflow: "hidden" }}>
                <div className="flex items-end gap-2.5 mb-3">
                  <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${expert.avatarColor}`}
                  >
                    {expert.initials}
                  </div>
                  <div className="rounded-2xl rounded-bl-md bg-white border border-stone-200 px-4 py-2.5 shadow-sm">
                    <div className="flex gap-1">
                      <span className="h-2 w-2 rounded-full bg-stone-300 animate-pulse-soft" />
                      <span
                        className="h-2 w-2 rounded-full bg-stone-300 animate-pulse-soft"
                        style={{ animationDelay: "200ms" }}
                      />
                      <span
                        className="h-2 w-2 rounded-full bg-stone-300 animate-pulse-soft"
                        style={{ animationDelay: "400ms" }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Response bubble */}
            <div
              style={{
                display: "grid",
                gridTemplateRows: s.responseVisible[i] ? "1fr" : "0fr",
                transition: "grid-template-rows 0.5s ease-out",
              }}
            >
              <div style={{ overflow: "hidden" }}>
                <div className="flex items-start gap-2.5 mb-4">
                  <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[9px] font-bold mt-0.5 ${expert.avatarColor}`}
                  >
                    {expert.initials}
                  </div>
                  <div
                    className="max-w-[85%] rounded-2xl rounded-bl-md bg-white border border-stone-200 px-4 py-3 shadow-sm"
                    style={{
                      opacity: s.responseVisible[i] ? 1 : 0,
                      transform: s.responseVisible[i]
                        ? "translateX(0)"
                        : "translateX(-8px)",
                      transition:
                        "opacity 0.4s ease-out 0.1s, transform 0.4s ease-out 0.1s",
                    }}
                  >
                    <p
                      className={`text-[11px] font-semibold ${expert.nameColor} mb-1`}
                    >
                      {expert.name}
                    </p>
                    <p className="text-[13px] leading-relaxed text-stone-700">
                      {expert.response}
                    </p>
                    <p className="text-[11px] text-stone-400 italic mt-2">
                      {expert.source}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}

        {/* Synthesis — system message */}
        <div
          style={{
            display: "grid",
            gridTemplateRows: s.synthesisVisible ? "1fr" : "0fr",
            transition: "grid-template-rows 0.5s ease-out",
          }}
        >
          <div style={{ overflow: "hidden" }}>
            <div className="pt-2">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-px flex-1 bg-stone-200" />
                <span className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Synthesis
                </span>
                <div className="h-px flex-1 bg-stone-200" />
              </div>
              <div
                className="rounded-xl bg-white border border-stone-200 px-4 py-3.5 shadow-sm"
                style={{
                  opacity: s.synthesisVisible ? 1 : 0,
                  transition: "opacity 0.5s ease-out 0.15s",
                }}
              >
                <div className="grid gap-4 grid-cols-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 mb-1.5">
                      Agree
                    </p>
                    <ul className="space-y-1">
                      {synthesis.agreements.map((point, idx) => (
                        <li
                          key={idx}
                          className="flex gap-1.5 text-[12px] text-stone-600 leading-relaxed"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-orange-600 mb-1.5">
                      Diverge
                    </p>
                    <ul className="space-y-1">
                      {synthesis.divergences.map((point, idx) => (
                        <li
                          key={idx}
                          className="flex gap-1.5 text-[12px] text-stone-600 leading-relaxed"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-400" />
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Input bar */}
      <div className="flex items-center gap-2 border-t border-stone-100 px-4 py-3 bg-white shrink-0">
        <div className="flex-1 rounded-full bg-stone-100 px-4 py-2 text-[13px] text-stone-400">
          Ask the panel&hellip;
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-800 text-white shrink-0">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M22 2L11 13" />
            <path d="M22 2L15 22L11 13L2 9L22 2Z" />
          </svg>
        </div>
      </div>
    </div>
  );
}
