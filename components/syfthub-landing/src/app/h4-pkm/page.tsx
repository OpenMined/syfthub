import { TerminalAnimated } from "@/components/mockups/terminal-animated";
import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { GraphAnimated } from "./graph-animated";
import { SearchDemoAnimated } from "./search-demo-animated";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Query Your Vault Privately",
  description:
    "AI-powered search across your Obsidian vault — completely private, completely local. 15 minutes to set up.",
};

/* ---------- SVG icons (inline, no emoji) ---------- */

function ShieldIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M12 2l7 4v5c0 5.25-3.5 9.74-7 11-3.5-1.26-7-5.75-7-11V6l7-4z" />
    </svg>
  );
}

function LockIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0110 0v4" />
    </svg>
  );
}

function ServerIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect x="2" y="2" width="20" height="8" rx="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" />
      <circle cx="6" cy="6" r="1" fill="currentColor" />
      <circle cx="6" cy="18" r="1" fill="currentColor" />
    </svg>
  );
}

/* ---------- Graph background (static knowledge graph aesthetic) ---------- */

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

function GraphBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* SVG lines connecting some nodes */}
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <line x1="12%" y1="20%" x2="28%" y2="35%" stroke="rgb(107 33 168 / 0.28)" strokeWidth="1" />
        <line x1="28%" y1="35%" x2="45%" y2="15%" stroke="rgb(107 33 168 / 0.22)" strokeWidth="1" />
        <line x1="45%" y1="15%" x2="62%" y2="40%" stroke="rgb(107 33 168 / 0.25)" strokeWidth="1" />
        <line x1="62%" y1="40%" x2="78%" y2="22%" stroke="rgb(107 33 168 / 0.22)" strokeWidth="1" />
        <line x1="78%" y1="22%" x2="88%" y2="45%" stroke="rgb(107 33 168 / 0.28)" strokeWidth="1" />
        <line x1="35%" y1="55%" x2="55%" y2="60%" stroke="rgb(107 33 168 / 0.25)" strokeWidth="1" />
        <line x1="45%" y1="15%" x2="35%" y2="55%" stroke="rgb(107 33 168 / 0.2)" strokeWidth="1" />
        <line x1="62%" y1="40%" x2="55%" y2="60%" stroke="rgb(107 33 168 / 0.22)" strokeWidth="1" />
        <line x1="20%" y1="65%" x2="35%" y2="55%" stroke="rgb(107 33 168 / 0.22)" strokeWidth="1" />
        <line x1="55%" y1="60%" x2="72%" y2="70%" stroke="rgb(107 33 168 / 0.25)" strokeWidth="1" />
        <line x1="28%" y1="35%" x2="20%" y2="65%" stroke="rgb(107 33 168 / 0.2)" strokeWidth="1" />
        <line x1="88%" y1="45%" x2="72%" y2="70%" stroke="rgb(107 33 168 / 0.22)" strokeWidth="1" />
      </svg>
      {/* Nodes */}
      {graphNodes.map((node, i) => (
        <div
          key={i}
          className={`absolute rounded-full bg-purple-500/20 ${node.size}`}
          style={{ left: node.x, top: node.y }}
        />
      ))}
    </div>
  );
}

/* ---------- Sections ---------- */

function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <SyftHubLogo size="md" dark />
        <a
          href="#install"
          className="rounded-lg border border-purple-500 px-4 py-2 text-sm text-purple-400 transition-colors hover:bg-purple-500/10"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-57px)] items-center py-16">
      <GraphAnimated />
      <div className="relative mx-auto w-full max-w-6xl px-6 text-center">
        <div className="relative mx-auto h-16 w-16 opacity-0 animate-fade-in-up">
          <ShieldIcon className="h-16 w-16 text-purple-500/30" />
          <div className="absolute inset-0 animate-radar-ping rounded-full border border-purple-500/30" />
        </div>
        <h1 className="opacity-0 animate-fade-in-up animation-delay-100 mt-6 text-5xl font-bold tracking-tight text-white">
          Query your entire vault.
          <br />
          Nothing leaves your machine.
        </h1>
        <p className="opacity-0 animate-fade-in-up animation-delay-200 mx-auto mt-4 max-w-lg text-lg text-gray-400">
          AI-powered search across your Obsidian vault. Completely private.
          Completely local.
        </p>
        <a
          href="#install"
          className="opacity-0 animate-fade-in-up animation-delay-300 mt-8 inline-block rounded-lg bg-purple-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-purple-500"
        >
          Get Started &rarr;
        </a>
        <p className="opacity-0 animate-fade-in-up animation-delay-400 mt-4 text-xs text-gray-500">
          Works with Obsidian, Logseq, and any .md collection
        </p>
      </div>
    </section>
  );
}

function SearchDemo() {
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

  return (
    <section className="py-20">
      <div className="mx-auto max-w-2xl px-6">
        <h2 className="mb-10 text-center text-2xl font-semibold text-white">
          Search like you think
        </h2>

        {/* Search input mockup */}
        <div className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-900 px-4 py-3">
          <span className="flex-1 font-mono text-sm text-gray-300">
            What were my key insights about distributed systems from Q4?
          </span>
          <button className="shrink-0 rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white">
            Search
          </button>
        </div>

        {/* Response card */}
        <div className="mt-4 rounded-lg border border-gray-800 bg-gray-900 p-6">
          <p className="text-sm leading-relaxed text-gray-300">
            Your Q4 notes highlight three main insights: (1) Raft consensus
            is preferred over Paxos for practical implementations due to its
            understandability, (2) CRDTs eliminate coordination overhead for
            eventually-consistent workloads, and (3) your team&apos;s migration
            to event sourcing reduced write contention by 40%.
          </p>

          <div className="mt-5 border-t border-gray-800 pt-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Sources
            </p>
            <div className="space-y-1.5">
              {citations.map((c, i) => (
                <p key={i} className="font-mono text-base text-purple-400">
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
    </section>
  );
}

function PrivacySection() {
  const guarantees = [
    {
      icon: <ShieldIcon className="h-8 w-8 text-purple-400" />,
      title: "100% Local",
      description:
        "Your data never leaves your machine. Not even metadata.",
    },
    {
      icon: <LockIcon className="h-8 w-8 text-purple-400" />,
      title: "No Cloud Required",
      description:
        "Runs entirely on your hardware. No account needed.",
    },
    {
      icon: <ServerIcon className="h-8 w-8 text-purple-400" />,
      title: "Open Protocol",
      description:
        "Standard MCP interface. No vendor lock-in.",
    },
  ];

  return (
    <section className="py-20">
      <div className="mx-6 rounded-2xl bg-gray-900 px-8 py-16 md:px-12">
        <StaggeredList staggerMs={200} className="mx-auto grid max-w-4xl gap-8 md:grid-cols-3">
          {guarantees.map((g, i) => (
            <div
              key={i}
              className={`flex flex-col items-center text-center ${
                i < guarantees.length - 1
                  ? "md:border-r md:border-gray-800"
                  : ""
              }`}
            >
              {g.icon}
              <h3 className="mt-4 text-base font-semibold text-white">
                {g.title}
              </h3>
              <p className="mt-2 max-w-xs text-sm text-gray-400">
                {g.description}
              </p>
            </div>
          ))}
        </StaggeredList>
      </div>
    </section>
  );
}

function CompatibilitySection() {
  const tools = ["Obsidian", "Logseq", "Roam", "Any .md folder"];

  return (
    <section className="py-16">
      <div className="mx-auto max-w-6xl px-6 text-center">
        <h2 className="text-2xl font-semibold text-white">
          Compatible with your stack
        </h2>
        <StaggeredList staggerMs={150} animation="animate-pop-in" className="mt-6 flex flex-wrap items-center justify-center gap-3">
          {tools.map((tool) => (
            <span
              key={tool}
              className="rounded-full border border-gray-600 px-4 py-1.5 text-sm text-gray-400"
            >
              {tool}
            </span>
          ))}
        </StaggeredList>
      </div>
    </section>
  );
}

function InstallSection() {
  return (
    <section id="install" className="py-20">
      <div className="mx-auto max-w-2xl px-6">
        <h2 className="mb-10 text-center text-2xl font-semibold text-white">
          Up and running in 3 commands
        </h2>
        <TerminalAnimated
          title="~"
          lines={[
            {
              prompt: true,
              text: "curl -fsSL https://get.syfthub.com/space | sh",
            },
            {
              text: '<span class="text-green-400">&#10003;</span> Syft Space installed',
            },
            { text: "" },
            {
              prompt: true,
              text: "syft-space connect ~/Documents/ObsidianVault",
            },
            { text: "Indexing 1,247 notes...", dimmed: true },
            {
              text: '<span class="text-green-400">&#10003;</span> Vault indexed. Ready to query.',
            },
            { text: "" },
            {
              prompt: true,
              text: 'syft-space query "What did I learn about..."',
            },
          ]}
        />
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section className="py-20">
      <div className="mx-auto max-w-6xl px-6 text-center">
        <h2 className="text-2xl font-bold text-white">
          Your vault has the answers.
        </h2>
        <p className="mt-2 text-gray-500">
          Set up in 15 minutes. Everything stays on your machine.
        </p>
        <a
          href="#install"
          className="mt-8 inline-block rounded-lg bg-purple-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-purple-500 animate-cta-glow"
          style={{ "--glow-color": "147 51 234" } as React.CSSProperties}
        >
          Get Started &rarr;
        </a>
      </div>
    </section>
  );
}

/* ---------- Page ---------- */

export default function H4PkmPage() {
  return (
    <div className="min-h-screen bg-gray-950 font-[family-name:var(--font-geist-sans)]">
      <Navbar />
      <Hero />
      <SearchDemoAnimated />
      <PrivacySection />
      <CompatibilitySection />
      <InstallSection />
      <CtaSection />
      <Footer dark />
    </div>
  );
}
