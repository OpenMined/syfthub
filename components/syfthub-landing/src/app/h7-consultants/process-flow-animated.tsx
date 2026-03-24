"use client";

import { useState, useEffect } from "react";
import { useInView } from "@/components/animations/use-in-view";

const steps = [
  {
    number: "1",
    icon: (
      <svg width="24" height="24" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5">
        <ellipse cx="16" cy="8" rx="10" ry="4" />
        <path d="M6 8v16c0 2.21 4.477 4 10 4s10-1.79 10-4V8" />
        <path d="M6 16c0 2.21 4.477 4 10 4s10-1.79 10-4" />
      </svg>
    ),
    title: "Connect data",
    description:
      "Point a Syft Space at the client's dataset. Nothing gets copied — the data never leaves their infrastructure.",
    color: "bg-blue-50 text-blue-600 border-blue-100",
  },
  {
    number: "2",
    icon: (
      <svg width="24" height="24" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="12" cy="18" r="6" />
        <path d="M16.5 13.5L25 5m0 0v4m0-4h-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    title: "Set permissions",
    description:
      "Define who can query, what they can access, and for how long. Granular controls for every engagement.",
    color: "bg-amber-50 text-amber-600 border-amber-100",
  },
  {
    number: "3",
    icon: (
      <svg width="24" height="24" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="22" cy="8" r="4" />
        <circle cx="10" cy="16" r="4" />
        <circle cx="22" cy="24" r="4" />
        <path d="M13.5 14L18.5 10M13.5 18l5 2" strokeLinecap="round" />
      </svg>
    ),
    title: "Share the link",
    description:
      "Client asks questions in plain language. They get answers with citations. You stop being the bottleneck.",
    color: "bg-emerald-50 text-emerald-600 border-emerald-100",
  },
];

export function ProcessFlowAnimated() {
  const [ref, isInView] = useInView();
  const [visibleStep, setVisibleStep] = useState(-1);

  useEffect(() => {
    if (!isInView) return;
    if (visibleStep >= steps.length - 1) return;

    const timer = setTimeout(() => {
      setVisibleStep((s) => s + 1);
    }, visibleStep < 0 ? 0 : 500);

    return () => clearTimeout(timer);
  }, [isInView, visibleStep]);

  return (
    <section className="bg-gray-50 px-6 py-24">
      <div className="mx-auto max-w-5xl" ref={ref}>
        <div className="text-center">
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-400">
            How it works
          </p>
          <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
            Three steps. Five minutes.
          </h2>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {steps.map((step, i) => (
            <div
              key={step.title}
              className={`relative rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-all duration-500 ${
                i <= visibleStep
                  ? "opacity-100 translate-y-0"
                  : "opacity-0 translate-y-6"
              }`}
            >
              {/* Step number */}
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl border ${step.color}`}>
                {step.icon}
              </div>

              {/* Connector line between cards */}
              {i < steps.length - 1 && (
                <div
                  className={`absolute -right-3 top-10 hidden h-px w-6 bg-gray-300 md:block transition-opacity duration-500 ${
                    i < visibleStep ? "opacity-100" : "opacity-0"
                  }`}
                />
              )}

              <h3 className="mt-5 text-[15px] font-bold text-gray-900">
                <span className="mr-2 text-gray-300">{step.number}.</span>
                {step.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-gray-500">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
