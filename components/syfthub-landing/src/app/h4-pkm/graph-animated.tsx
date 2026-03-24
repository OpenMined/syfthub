"use client";

import { useInView } from "@/components/animations/use-in-view";

const graphNodes = [
  { x: "12%", y: "20%", size: "w-3.5 h-3.5" },
  { x: "28%", y: "35%", size: "w-3 h-3" },
  { x: "45%", y: "15%", size: "w-4 h-4" },
  { x: "62%", y: "40%", size: "w-3.5 h-3.5" },
  { x: "78%", y: "22%", size: "w-3 h-3" },
  { x: "88%", y: "45%", size: "w-3.5 h-3.5" },
  { x: "35%", y: "55%", size: "w-3 h-3" },
  { x: "55%", y: "60%", size: "w-3.5 h-3.5" },
  { x: "20%", y: "65%", size: "w-3.5 h-3.5" },
  { x: "72%", y: "70%", size: "w-3 h-3" },
];

const graphLines = [
  { x1: "12%", y1: "20%", x2: "28%", y2: "35%", opacity: 0.28 },
  { x1: "28%", y1: "35%", x2: "45%", y2: "15%", opacity: 0.22 },
  { x1: "45%", y1: "15%", x2: "62%", y2: "40%", opacity: 0.25 },
  { x1: "62%", y1: "40%", x2: "78%", y2: "22%", opacity: 0.22 },
  { x1: "78%", y1: "22%", x2: "88%", y2: "45%", opacity: 0.28 },
  { x1: "35%", y1: "55%", x2: "55%", y2: "60%", opacity: 0.25 },
  { x1: "45%", y1: "15%", x2: "35%", y2: "55%", opacity: 0.2 },
  { x1: "62%", y1: "40%", x2: "55%", y2: "60%", opacity: 0.22 },
  { x1: "20%", y1: "65%", x2: "35%", y2: "55%", opacity: 0.22 },
  { x1: "55%", y1: "60%", x2: "72%", y2: "70%", opacity: 0.25 },
  { x1: "28%", y1: "35%", x2: "20%", y2: "65%", opacity: 0.2 },
  { x1: "88%", y1: "45%", x2: "72%", y2: "70%", opacity: 0.22 },
];

const driftNodeIndices = [0, 4, 9];

export function GraphAnimated() {
  const [ref, isInView] = useInView({ threshold: 0.1 });

  return (
    <div
      ref={ref}
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      {/* SVG lines */}
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        {graphLines.map((line, i) => (
          <line
            key={i}
            x1={line.x1}
            y1={line.y1}
            x2={line.x2}
            y2={line.y2}
            stroke={`rgb(107 33 168 / ${line.opacity})`}
            strokeWidth="1"
            strokeDasharray="200"
            strokeDashoffset={isInView ? "0" : "200"}
            style={{
              transition: "stroke-dashoffset 1s ease-out",
              transitionDelay: `${i * 80}ms`,
            }}
          />
        ))}
      </svg>
      {/* Nodes */}
      {graphNodes.map((node, i) => (
        <div
          key={i}
          className={`absolute rounded-full bg-purple-500/20 ${node.size} ${
            isInView ? "animate-pulse-soft" : ""
          } ${
            isInView && driftNodeIndices.includes(i)
              ? "animate-glow-drift"
              : ""
          }`}
          style={{
            left: node.x,
            top: node.y,
            animationDelay: `${i * 200}ms`,
          }}
        />
      ))}
    </div>
  );
}
