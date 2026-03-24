import { DashboardMock } from "@/components/mockups/dashboard-mock";
import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Share Your AI Agent, Control Everything",
  description:
    "Generate access links with scoped permissions. Monitor every query. Revoke instantly.",
};

/* ─── Navbar ─── */
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <SyftHubLogo size="md" dark />
        <a
          href="#get-started"
          className="rounded-lg border border-emerald-500 px-4 py-2 text-sm font-medium text-emerald-400 transition-colors hover:bg-emerald-500/10"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

/* ─── Hero ─── */
function Hero() {
  const tokens = [
    {
      name: "Acme Corp",
      scope: "read:reports",
      queries: "1,247",
      status: "active" as const,
      expires: "Apr 15, 2026",
    },
    {
      name: "Jane (Contractor)",
      scope: "read:summaries",
      queries: "89",
      status: "active" as const,
      expires: "Mar 30, 2026",
    },
    {
      name: "Old Partner",
      scope: "read:all",
      queries: "2,451",
      status: "revoked" as const,
      expires: "\u2014",
    },
    {
      name: "Demo Access",
      scope: "read:public",
      queries: "12",
      status: "expired" as const,
      expires: "Mar 1, 2026",
    },
  ];

  return (
    <section className="flex min-h-[calc(100vh-57px)] items-center">
      <div className="mx-auto grid w-full max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-5 lg:gap-12">
        {/* Left copy */}
        <div className="lg:col-span-2">
          <span className="opacity-0 animate-fade-in-up text-xs font-medium uppercase tracking-[0.15em] text-emerald-400">
            Agent Security
          </span>
          <h1 className="opacity-0 animate-fade-in-up animation-delay-100 mt-4 text-4xl font-bold leading-[1.1] tracking-tight text-white">
            Share your agent. Control everything.
          </h1>
          <p className="opacity-0 animate-fade-in-up animation-delay-200 mt-4 text-lg text-gray-400">
            Generate access links with scoped permissions. Monitor every query.
            Revoke instantly.
          </p>
          <a
            href="#get-started"
            className="opacity-0 animate-fade-in-up animation-delay-300 mt-8 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
          >
            Get Started &rarr;
          </a>
        </div>

        {/* Right dashboard */}
        <AnimatedSection delay={300} className="lg:col-span-3">
          <DashboardMock tokens={tokens} />
        </AnimatedSection>
      </div>
    </section>
  );
}

/* ─── The Problem (Scary Slack Message) ─── */
function ProblemSection() {
  return (
    <section className="px-6">
      <AnimatedSection className="mx-auto my-20 max-w-5xl rounded-2xl bg-gray-900 px-6 py-16">
        {/* Slack-style message */}
        <div className="mx-auto max-w-2xl">
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gray-500/20 text-xs font-bold text-gray-400">
                JD
              </div>
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-semibold text-gray-200">
                    John Developer
                  </span>
                  <span className="text-xs text-gray-600">2:34 PM</span>
                </div>
                <p className="mt-1 text-sm leading-relaxed text-gray-400">
                  Hey{" "}
                  <span className="rounded bg-blue-500/10 px-1 text-blue-400">
                    @client
                  </span>
                  , here&apos;s the API key for the agent:{" "}
                  <code className="rounded bg-gray-800 px-1.5 py-0.5 font-[family-name:var(--font-geist-mono)] text-xs text-red-400 animate-danger-flash animation-delay-800" style={{ animationIterationCount: 2 }}>
                    sk-proj-a8f3...kx9m
                  </code>{" "}
                  &mdash; just use it directly, no restrictions
                </p>
              </div>
            </div>
          </div>

          {/* Warning callout */}
          <AnimatedSection delay={1200} className="mt-4 rounded-lg border-l-4 border-red-500 bg-red-500/10 p-4">
            <p className="text-base font-medium leading-relaxed text-red-200">
              This is how most agents get shared today. Full access. No scoping.
              No audit trail. No revocation.
            </p>
          </AnimatedSection>
        </div>
      </AnimatedSection>
    </section>
  );
}

/* ─── Copy icon (inline SVG) ─── */
function CopyIcon() {
  return (
    <svg
      className="h-4 w-4 text-gray-500"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75"
      />
    </svg>
  );
}

/* ─── Feature 1: Scoped Access Links ─── */
function FeatureScopedLinks() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        {/* Left copy */}
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">
            Generate scoped access links
          </h2>
          <p className="mt-3 max-w-md leading-relaxed text-gray-400">
            Define exactly what each client can access. Set rate limits and
            expiration dates. Share a single link — not raw API keys.
          </p>
        </div>

        {/* Right mockup: Generate Link form */}
        <AnimatedSection className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <p className="mb-4 text-xs font-medium uppercase tracking-wider text-gray-500">
            Generate Access Link
          </p>
          <StaggeredList staggerMs={150} className="space-y-3">
            {/* Scope dropdown */}
            <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5">
              <span className="text-xs text-gray-500">Permission scope</span>
              <span className="font-[family-name:var(--font-geist-mono)] text-xs text-gray-300">
                read:reports
              </span>
            </div>
            {/* Rate limit dropdown */}
            <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5">
              <span className="text-xs text-gray-500">Rate limit</span>
              <span className="font-[family-name:var(--font-geist-mono)] text-xs text-gray-300">
                100 queries/day
              </span>
            </div>
            {/* Expires dropdown */}
            <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5">
              <span className="text-xs text-gray-500">Expires</span>
              <span className="font-[family-name:var(--font-geist-mono)] text-xs text-gray-300">
                30 days
              </span>
            </div>
            {/* Generate button */}
            <button className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white">
              Generate
            </button>
          </StaggeredList>
          {/* Generated link */}
          <AnimatedSection delay={600} className="mt-4 flex items-center justify-between rounded-lg border border-gray-700 bg-gray-950 px-4 py-2.5 shadow-[0_0_12px_rgba(16,185,129,0.15)]">
            <code className="font-[family-name:var(--font-geist-mono)] text-xs text-emerald-400">
              https://syft.hub/access/ak_7f2x...9m
            </code>
            <CopyIcon />
          </AnimatedSection>
        </AnimatedSection>
      </div>
    </section>
  );
}

/* ─── Feature 2: Monitor Queries ─── */
function FeatureMonitor() {
  const logs = [
    {
      time: "10:32 AM",
      client: "Acme Corp",
      query: "Q4 revenue summary",
      ms: "230ms",
    },
    {
      time: "10:31 AM",
      client: "Acme Corp",
      query: "Compare Q3 vs Q4 margins",
      ms: "185ms",
    },
    {
      time: "10:28 AM",
      client: "Jane (Contractor)",
      query: "Team headcount by dept",
      ms: "312ms",
    },
    {
      time: "10:15 AM",
      client: "Acme Corp",
      query: "Customer churn rate YTD",
      ms: "198ms",
    },
    {
      time: "09:47 AM",
      client: "Jane (Contractor)",
      query: "Onboarding completion stats",
      ms: "275ms",
    },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        {/* Left mockup: Activity log */}
        <div className="order-2 lg:order-1">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="mb-4 flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse-soft" />
              <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                Live Activity
              </span>
            </div>
            <StaggeredList staggerMs={120} animation="animate-log-entry" className="space-y-0">
              {logs.map((log, i) => (
                <div
                  key={i}
                  className="flex items-baseline gap-3 border-b border-gray-800/50 py-2 last:border-0 font-[family-name:var(--font-geist-mono)] text-sm"
                >
                  <span className="shrink-0 text-emerald-400">{log.time}</span>
                  <span className="shrink-0 text-gray-500">&mdash;</span>
                  <span className="shrink-0 text-gray-300">{log.client}</span>
                  <span className="shrink-0 text-gray-500">&mdash;</span>
                  <span className="min-w-0 truncate text-gray-400">
                    &apos;{log.query}&apos;
                  </span>
                  <span className="ml-auto shrink-0 text-gray-600">
                    {log.ms}
                  </span>
                </div>
              ))}
            </StaggeredList>
          </div>
        </div>

        {/* Right copy */}
        <div className="order-1 lg:order-2">
          <h2 className="text-2xl font-bold tracking-tight text-white">
            Monitor every query in real-time
          </h2>
          <p className="mt-3 max-w-md leading-relaxed text-gray-400">
            See who queries what, when, and how fast. Complete audit trail for
            compliance. Spot anomalies before they become problems.
          </p>
        </div>
      </div>
    </section>
  );
}

/* ─── Feature 3: Revoke Access ─── */
function FeatureRevoke() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        {/* Left copy */}
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">
            Revoke access in one click
          </h2>
          <p className="mt-3 max-w-md leading-relaxed text-gray-400">
            No more rotating API keys and breaking every integration. Revoke a
            single token. Everyone else keeps working.
          </p>
        </div>

        {/* Right mockup: Token row with revoke */}
        <div className="space-y-3">
          {/* Active token row */}
          <AnimatedSection className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div>
                  <p className="text-sm font-medium text-gray-200">
                    Old Partner
                  </p>
                  <p className="mt-0.5 font-[family-name:var(--font-geist-mono)] text-xs text-gray-500">
                    read:all &middot; 2,451 queries
                  </p>
                </div>
              </div>
              <button className="rounded-md bg-red-500/20 px-3 py-1.5 text-sm font-medium text-red-400">
                Revoke
              </button>
            </div>
          </AnimatedSection>

          {/* Revoked state */}
          <AnimatedSection animation="animate-slide-in-left" delay={400} className="rounded-xl border border-red-500/20 bg-gray-900 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-red-500/10">
                  <svg
                    className="h-4 w-4 text-red-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6 18 18 6M6 6l12 12"
                    />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-200">
                    Access revoked
                  </p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    0 active sessions
                  </p>
                </div>
              </div>
              <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-medium text-red-400">
                revoked
              </span>
            </div>
          </AnimatedSection>
        </div>
      </div>
    </section>
  );
}

/* ─── Comparison Table ─── */
function ComparisonSection() {
  const rows = [
    { before: "Shared API keys", after: "Scoped access links" },
    { before: "Full unrestricted access", after: "Granular permissions" },
    { before: "No query logs", after: "Complete audit trail" },
    {
      before: "Can\u2019t revoke without rotating keys",
      after: "One-click revocation",
    },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <h2 className="mb-12 text-center text-2xl font-bold tracking-tight text-white">
        Before SyftHub / After SyftHub
      </h2>
      <div className="mx-auto max-w-3xl overflow-hidden rounded-xl border border-gray-800">
        {/* Table header */}
        <div className="grid grid-cols-2 border-b border-gray-800 bg-gray-900">
          <div className="px-6 py-3 text-xs font-medium uppercase tracking-wider text-red-400">
            Before
          </div>
          <div className="border-l border-gray-800 px-6 py-3 text-xs font-medium uppercase tracking-wider text-emerald-400">
            After
          </div>
        </div>
        {/* Table rows */}
        <StaggeredList staggerMs={200}>
        {rows.map((row, i) => (
          <div
            key={i}
            className="grid grid-cols-2 border-b border-gray-800/50 last:border-0"
          >
            <div className="flex items-center gap-3 px-6 py-4">
              <span className="text-red-400">&times;</span>
              <span className="text-sm text-gray-400">{row.before}</span>
            </div>
            <div className="flex items-center gap-3 border-l border-gray-800/50 px-6 py-4">
              <span className="text-emerald-400">&#10003;</span>
              <span className="text-sm text-gray-300">{row.after}</span>
            </div>
          </div>
        ))}
        </StaggeredList>
      </div>
    </section>
  );
}

/* ─── CTA ─── */
function CtaSection() {
  return (
    <section id="get-started" className="px-6 pb-12">
      <div className="mx-auto max-w-6xl rounded-2xl border border-gray-800 bg-gray-900 px-6 py-16 text-center">
        <h2 className="text-2xl font-bold text-white">
          Stop choosing between sharing and security.
        </h2>
        <p className="mt-3 text-gray-400">
          Give clients exactly the access they need.
        </p>
        <a
          href="#"
          className="mt-8 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-emerald-700 animate-cta-glow"
          style={{ "--glow-color": "16 185 129" } as React.CSSProperties}
        >
          Generate Your First Access Link &rarr;
        </a>
      </div>
    </section>
  );
}

/* ─── Page ─── */
export default function H5AgentPermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 font-[family-name:var(--font-geist-sans)]">
      <Navbar />
      <Hero />
      <ProblemSection />
      <FeatureScopedLinks />
      <FeatureMonitor />
      <FeatureRevoke />
      <ComparisonSection />
      <CtaSection />
      <Footer dark={true} />
    </div>
  );
}
