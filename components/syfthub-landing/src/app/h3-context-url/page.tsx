import { BrowserFrame } from "@/components/mockups/browser-frame";
import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { Typewriter } from "@/components/animations/typewriter";
import { ChatAnimated } from "@/components/mockups/chat-animated";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Stop Being Your Team's Human Search Engine",
  description:
    "Turn your team's docs into a single URL. Anyone pastes it into their AI and asks. The AI knows your docs.",
};

/* ─── Navbar ─── */
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-lg">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <SyftHubLogo size="md" />
        <a
          href="#get-started"
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-gray-800 hover:shadow-md"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

/* ─── Hero ─── */
function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-53px)] items-center overflow-hidden">
      {/* Subtle gradient backdrop */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-blue-50/40 via-white to-white" />

      <div className="relative mx-auto w-full max-w-6xl px-6 py-16 lg:py-20">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
          {/* Left — copy */}
          <div>
            <span className="opacity-0 animate-fade-in-up inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              For engineering teams
            </span>

            <h1 className="opacity-0 animate-fade-in-up animation-delay-100 mt-7 text-[2.75rem] font-extrabold leading-[1.08] tracking-[-0.03em] text-gray-900 lg:text-[3.5rem]">
              Stop being your team&apos;s
              <span className="text-blue-600"> human search engine</span>
            </h1>

            <p className="opacity-0 animate-fade-in-up animation-delay-200 mt-5 max-w-md text-[17px] leading-relaxed text-gray-500">
              Turn your internal docs into a single URL. Anyone pastes it into
              any AI — and the AI knows your docs instantly.
            </p>

            {/* The Context URL — glowing emphasis */}
            <div className="opacity-0 animate-fade-in-up animation-delay-300 mt-8 inline-flex items-center gap-2.5 rounded-xl border border-blue-200 bg-white px-4 py-3 shadow-[0_0_0_4px_rgba(59,130,246,0.08),0_1px_3px_rgba(0,0,0,0.05)] animate-cta-glow" style={{ "--glow-color": "59 130 246" } as React.CSSProperties}>
              <svg className="h-4 w-4 shrink-0 text-blue-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m9.86-2.54a4.5 4.5 0 0 0-1.242-7.244l-4.5-4.5a4.5 4.5 0 0 0-6.364 6.364L4.34 8.374" />
              </svg>
              <code className="text-[13px] font-semibold text-gray-800 tracking-tight">
                ctx.syft.hub/acme-docs
              </code>
              <span className="ml-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11px] font-semibold text-white">
                Copy
              </span>
            </div>

            <div className="opacity-0 animate-fade-in-up animation-delay-400 mt-6 flex items-center gap-4">
              <a
                href="#get-started"
                className="rounded-xl bg-blue-600 px-6 py-3 text-[15px] font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.05),0_4px_12px_rgba(59,130,246,0.25)] transition-all hover:bg-blue-700 hover:shadow-[0_1px_2px_rgba(0,0,0,0.05),0_8px_20px_rgba(59,130,246,0.3)]"
              >
                Create your Context URL &rarr;
              </a>
            </div>
            <p className="mt-3 text-[13px] text-gray-400">
              Set up in under 5 minutes
            </p>
          </div>

          {/* Right — Slack mockup in browser frame */}
          <div className="relative">
            {/* Background glow behind the frame */}
            <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-blue-100/40 blur-2xl" />
            <div className="relative">
              <BrowserFrame url="slack.com — #engineering" className="shadow-2xl">
                <ChatAnimated
                  messages={[
                    {
                      avatar: "DP",
                      avatarColor: "bg-orange-100 text-orange-600",
                      name: "Dev Patel",
                      time: "10:32 AM",
                      content: (
                        <p className="text-[13px] leading-relaxed text-gray-600">
                          Hey <span className="rounded bg-blue-50 px-1 font-medium text-blue-700">@sarah</span>, how does the auth flow work for the new API?
                        </p>
                      ),
                      delay: 400,
                    },
                    {
                      avatar: "SJ",
                      avatarColor: "bg-emerald-100 text-emerald-600",
                      name: "Sarah Johnson",
                      time: "10:33 AM",
                      content: (
                        <p className="text-[13px] leading-relaxed text-gray-600">
                          Just paste this into Claude:{" "}
                          <code className="rounded bg-blue-50 px-1.5 py-0.5 text-[12px] font-semibold text-blue-700">
                            ctx.syft.hub/acme-docs
                          </code>
                        </p>
                      ),
                      delay: 900,
                    },
                    {
                      avatar: "AI",
                      avatarColor: "bg-indigo-600 text-white",
                      name: "Claude",
                      time: "10:33 AM",
                      isBot: true,
                      botBadge: "BOT",
                      bgClass: "bg-blue-50/30",
                      content: (
                        <div>
                          <p className="mt-1 text-[13px] leading-relaxed text-gray-700">
                            Based on your <strong>API Auth Guide</strong>: The auth flow uses OAuth 2.0 with PKCE.
                          </p>
                          <ol className="mt-2 space-y-1 text-[13px] leading-relaxed text-gray-600">
                            <li>1. Request auth code via <code className="text-[12px] text-gray-800">/auth/authorize</code></li>
                            <li>2. User approves in browser</li>
                            <li>3. Exchange code at <code className="text-[12px] text-gray-800">/auth/token</code></li>
                            <li>4. Access token returned (1hr TTL)</li>
                          </ol>
                          <p className="mt-2 flex items-center gap-1.5 text-[11px] text-gray-400">
                            <svg className="h-3 w-3 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                            </svg>
                            Sourced from <span className="font-medium text-blue-600">API Auth Guide</span> &middot; Notion
                          </p>
                        </div>
                      ),
                      delay: 1800,
                    },
                  ]}
                  typingIndicatorDelay={600}
                />
              </BrowserFrame>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─── Social Proof Bar ─── */
function SocialProof() {
  return (
    <section className="border-y border-gray-100 bg-gray-50/50">
      <AnimatedSection className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex flex-col items-center gap-6 md:flex-row md:justify-between">
          <div className="flex items-center gap-8">
            {[
              { value: "4 hrs", label: "saved / week" },
              { value: "5 min", label: "to set up" },
              { value: "0", label: "new tools" },
            ].map((m) => (
              <div key={m.label} className="flex items-baseline gap-2">
                <span className="text-2xl font-extrabold tracking-tight text-gray-900">{m.value}</span>
                <span className="text-xs text-gray-400">{m.label}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[13px] text-gray-400">
            Used by teams at
            {["Vercel", "Linear", "Notion", "Stripe"].map((co) => (
              <span key={co} className="ml-1 font-semibold text-gray-500">{co}</span>
            ))}
          </div>
        </div>
      </AnimatedSection>
    </section>
  );
}

/* ─── Before / After ─── */
function BeforeAfter() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24">
      <div className="text-center">
        <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
          The old way vs. the new way
        </h2>
      </div>

      <div className="mx-auto mt-14 grid max-w-4xl gap-6 md:grid-cols-2">
        {/* BEFORE */}
        <AnimatedSection animation="animate-slide-in-left" className="relative overflow-hidden rounded-2xl border border-gray-200 bg-white p-6 shadow-[0_2px_8px_rgba(0,0,0,0.04),0_8px_24px_rgba(0,0,0,0.06)]">
          <div className="mb-6 flex items-center justify-between">
            <span className="text-[13px] font-bold uppercase tracking-widest text-red-500">Before</span>
            <span className="rounded-full bg-red-50 px-3 py-1 text-[11px] font-bold text-red-500">
              ~5 interruptions / day
            </span>
          </div>
          <StaggeredList staggerMs={150} className="space-y-3">
            {[
              "How does the auth flow work?",
              "Where's the deploy runbook?",
              "What's the rate limit for /api/v2?",
            ].map((q, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg bg-red-50/70 px-4 py-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-100 text-[11px] font-bold text-red-500">
                  {["DP", "MB", "LC"][i]}
                </div>
                <p className="text-[13px] text-gray-600">
                  <span className="font-semibold text-red-600">@you</span> {q}
                </p>
              </div>
            ))}
          </StaggeredList>
          <p className="mt-5 text-center text-[13px] font-medium text-red-400">
            You&apos;re the bottleneck. Again.
          </p>
        </AnimatedSection>

        {/* AFTER */}
        <AnimatedSection animation="animate-slide-in-right" delay={200} className="relative overflow-hidden rounded-2xl border border-green-200 bg-white p-6 shadow-[0_2px_8px_rgba(0,0,0,0.04),0_8px_24px_rgba(16,185,129,0.08)]">
          <div className="mb-6 flex items-center justify-between">
            <span className="text-[13px] font-bold uppercase tracking-widest text-green-600">After</span>
            <span className="rounded-full bg-green-50 px-3 py-1 text-[11px] font-bold text-green-600">
              0 interruptions
            </span>
          </div>
          <StaggeredList staggerMs={200} className="space-y-3">
            <div className="rounded-lg bg-green-50/70 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-green-600">Dev pastes URL into Claude</p>
              <code className="mt-1 block text-[13px] font-semibold text-blue-700">ctx.syft.hub/acme-docs</code>
            </div>
            <div className="rounded-lg bg-green-50/70 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-green-600">AI answers instantly</p>
              <p className="mt-1 text-[13px] text-gray-600">&quot;The auth flow uses OAuth 2.0 with PKCE...&quot;</p>
            </div>
            <div className="rounded-lg bg-green-50/70 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-green-600">Cites the source</p>
              <p className="mt-1 text-[13px] text-gray-600">
                From: <span className="font-medium text-blue-600">API Auth Guide</span> — Notion
              </p>
            </div>
          </StaggeredList>
          <p className="mt-5 text-center text-[13px] font-medium text-green-600">
            You stay focused. AI handles the rest.
          </p>
        </AnimatedSection>
      </div>
    </section>
  );
}

/* ─── Product Demo — vertical flow ─── */
function ProductDemo() {
  return (
    <section className="relative overflow-hidden bg-gray-50">
      {/* Top gradient fade */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white to-transparent" />

      <div className="relative mx-auto max-w-5xl px-6 py-24">
        <div className="text-center">
          <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
            Set up in three steps
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[15px] text-gray-500">
            Connect your docs, get a URL, share it. Your team starts querying immediately.
          </p>
        </div>

        <div className="mt-16 space-y-16">
          {/* Step 1 */}
          <div className="grid items-center gap-10 md:grid-cols-[1fr_1.2fr]">
            <div>
              <div className="mb-3 flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white shadow-[0_2px_8px_rgba(59,130,246,0.3)]">1</span>
                <span className="text-lg font-bold text-gray-900">Connect your sources</span>
              </div>
              <p className="ml-11 text-[15px] leading-relaxed text-gray-500">
                Point SyftHub at your Notion workspace, Confluence, Google Drive, or GitHub repos. We index everything automatically.
              </p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Data Sources</span>
                <span className="flex items-center gap-1.5 text-[11px] font-medium text-green-600">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse-soft" /> All synced
                </span>
              </div>
              <div className="space-y-2">
                {[
                  { name: "Engineering Wiki", src: "Notion", docs: "312 pages" },
                  { name: "API Documentation", src: "Confluence", docs: "89 pages" },
                  { name: "README files", src: "GitHub", docs: "446 files" },
                ].map((s) => (
                  <div key={s.name} className="flex items-center justify-between rounded-xl bg-gray-50 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-[10px] font-bold text-gray-400 shadow-sm">
                        {s.src[0]}
                      </div>
                      <div>
                        <p className="text-[13px] font-medium text-gray-800">{s.name}</p>
                        <p className="text-[11px] text-gray-400">{s.src} &middot; {s.docs}</p>
                      </div>
                    </div>
                    <svg className="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Step 2 */}
          <div className="grid items-center gap-10 md:grid-cols-[1.2fr_1fr]">
            <AnimatedSection className="order-2 md:order-1">
              <div className="rounded-2xl border-2 border-blue-200 bg-gradient-to-br from-blue-50/80 to-white p-5 shadow-[0_0_0_4px_rgba(59,130,246,0.06),0_4px_16px_rgba(59,130,246,0.1)]">
                <div className="mb-3 text-[11px] font-bold uppercase tracking-widest text-blue-500">
                  Your Context URL
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-4 py-3 shadow-sm">
                  <svg className="h-4 w-4 shrink-0 text-blue-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m9.86-2.54a4.5 4.5 0 0 0-1.242-7.244l-4.5-4.5a4.5 4.5 0 0 0-6.364 6.364L4.34 8.374" />
                  </svg>
                  <code className="flex-1 text-[14px] font-bold tracking-tight text-gray-900">
                    <Typewriter text="ctx.syft.hub/acme-docs" speed={50} showCursor={false} />
                  </code>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button className="rounded-lg bg-blue-600 py-2.5 text-[13px] font-semibold text-white shadow-sm">
                    Copy URL
                  </button>
                  <button className="rounded-lg border border-gray-200 bg-white py-2.5 text-[13px] font-semibold text-gray-700 shadow-sm">
                    Share to Slack
                  </button>
                </div>
                <div className="mt-4 flex items-center justify-center gap-4 text-[11px] text-gray-400">
                  <span>3 sources</span>
                  <span className="h-0.5 w-0.5 rounded-full bg-gray-300" />
                  <span>847 documents</span>
                  <span className="h-0.5 w-0.5 rounded-full bg-gray-300" />
                  <span>Updated 2m ago</span>
                </div>
              </div>
            </AnimatedSection>
            <div className="order-1 md:order-2">
              <div className="mb-3 flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white shadow-[0_2px_8px_rgba(59,130,246,0.3)]">2</span>
                <span className="text-lg font-bold text-gray-900">Get your Context URL</span>
              </div>
              <p className="ml-11 text-[15px] leading-relaxed text-gray-500">
                One URL that represents your entire knowledge base. Share it in Slack, pin it in a channel, or bookmark it. That&apos;s it.
              </p>
            </div>
          </div>

          {/* Step 3 */}
          <div className="grid items-center gap-10 md:grid-cols-[1fr_1.2fr]">
            <div>
              <div className="mb-3 flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white shadow-[0_2px_8px_rgba(59,130,246,0.3)]">3</span>
                <span className="text-lg font-bold text-gray-900">Team queries any AI</span>
              </div>
              <p className="ml-11 text-[15px] leading-relaxed text-gray-500">
                Any team member pastes the URL into ChatGPT, Claude, Cursor — whatever they already use. The AI answers from your docs, with source links.
              </p>
            </div>
            <AnimatedSection className="rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
              <StaggeredList staggerMs={400}>
                <div className="mb-3 flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-600 text-[10px] font-bold text-white">C</div>
                  <span className="text-[13px] font-semibold text-gray-700">Claude</span>
                </div>
                <div className="rounded-xl bg-gray-50 px-4 py-3 text-[13px] text-gray-500">
                  What&apos;s the deploy process for staging?
                </div>
                <div className="mt-2 rounded-xl bg-blue-50/60 px-4 py-3">
                  <p className="text-[13px] leading-relaxed text-gray-700">
                    Based on your <strong>Deploy Runbook</strong>: SSH to{" "}
                    <code className="rounded bg-white px-1 py-0.5 text-[12px] font-medium text-gray-800 shadow-sm">staging-01</code>, run{" "}
                    <code className="rounded bg-white px-1 py-0.5 text-[12px] font-medium text-gray-800 shadow-sm">./deploy.sh --env staging</code>, then verify health at /status.
                  </p>
                </div>
                <p className="mt-2.5 flex items-center gap-1.5 text-[11px] text-gray-400">
                  <svg className="h-3 w-3 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  From <span className="font-medium text-blue-600">deploy-runbook.md</span> &middot; updated 3 days ago
                </p>
              </StaggeredList>
            </AnimatedSection>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─── Integrations Flow ─── */
function Integrations() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24">
      <div className="grid items-center gap-16 md:grid-cols-2">
        {/* Visual flow */}
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
          <p className="mb-5 text-[11px] font-bold uppercase tracking-widest text-gray-400">
            How it connects
          </p>
          {/* Sources */}
          <StaggeredList staggerMs={100} animation="animate-slide-in-left" className="flex flex-wrap gap-2">
            {["Notion", "Confluence", "Google Drive", "GitHub"].map((s) => (
              <span key={s} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-[13px] font-medium text-gray-600 shadow-sm">
                {s}
              </span>
            ))}
          </StaggeredList>
          {/* Hub connector */}
          <AnimatedSection animation="animate-pop-in" delay={500} className="my-4 flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-gray-200 to-blue-200" />
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white shadow-[0_2px_8px_rgba(59,130,246,0.3)]">
              S
            </div>
            <div className="h-px flex-1 bg-gradient-to-r from-blue-200 to-gray-200" />
          </AnimatedSection>
          {/* AI tools */}
          <StaggeredList staggerMs={100} animation="animate-slide-in-right" className="flex flex-wrap gap-2">
            {["ChatGPT", "Claude", "Cursor", "Copilot", "Windsurf"].map((t) => (
              <span key={t} className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[13px] font-medium text-blue-700 shadow-sm">
                {t}
              </span>
            ))}
          </StaggeredList>
        </div>

        <div>
          <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
            Works in every AI tool your team uses
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-gray-500">
            No plugins. No integrations to configure. A Context URL works
            anywhere — ChatGPT, Claude, Cursor, Copilot. Your team pastes it,
            asks a question, and gets an answer grounded in your actual docs.
          </p>
          <div className="mt-6 flex items-start gap-3">
            <svg className="mt-0.5 h-5 w-5 shrink-0 text-blue-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
            </svg>
            <p className="text-[15px] leading-relaxed text-gray-500">
              <strong className="text-gray-800">Always current.</strong> When you update a doc in Notion,
              the Context URL reflects the change automatically. No manual re-syncing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─── Testimonial ─── */
function Testimonial() {
  return (
    <section className="bg-gray-50">
      <div className="mx-auto max-w-4xl px-6 py-20">
        <div className="rounded-2xl border border-gray-200 bg-white p-8 shadow-[0_4px_16px_rgba(0,0,0,0.04)] md:p-10">
          <svg className="mb-4 h-8 w-8 text-blue-200" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.3 2.7c-.4-.4-1-.4-1.4 0L6 6.6c-.4.4-.4 1 0 1.4l.7.7c.4.4 1 .4 1.4 0l2.1-2.1v5.8c0 .6.4 1 1 1h1c.6 0 1-.4 1-1V6.6l2.1 2.1c.4.4 1 .4 1.4 0l.7-.7c.4-.4.4-1 0-1.4l-3.9-3.9zM4.6 14.3c-.5 0-1 .3-1.2.8l-1.2 3.5c-.3.8.3 1.6 1.2 1.6h2.3l-.4 1.2c-.2.5.2 1 .7 1h.3c.4 0 .7-.2.9-.5l.7-1.7h3.2c.5 0 1-.3 1.2-.8l1.2-3.5c.3-.8-.3-1.6-1.2-1.6H4.6z" opacity="0" />
            <path d="M4.583 17.321C3.553 16.227 3 15 3 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179zm10 0C13.553 16.227 13 15 13 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179z" />
          </svg>
          <blockquote className="text-lg leading-relaxed text-gray-700 md:text-xl md:leading-relaxed">
            I used to get 5-10 Slack pings a day asking about the same docs.
            Now I share the Context URL in the channel and the questions just stop.
            It&apos;s like cloning myself for the boring parts of the job.
          </blockquote>
          <div className="mt-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-600">
              AC
            </div>
            <div>
              <p className="text-[14px] font-semibold text-gray-900">Alex Chen</p>
              <p className="text-[13px] text-gray-500">Staff Engineer &middot; Series B startup</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─── CTA ─── */
function CtaSection() {
  return (
    <section id="get-started" className="px-6 pb-16 pt-8">
      <AnimatedSection className="mx-auto max-w-4xl overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 to-blue-700 px-8 py-16 text-center shadow-[0_8px_32px_rgba(59,130,246,0.25)] md:px-16">
        <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-white md:text-4xl">
          Free yourself from being<br />the answer machine.
        </h2>
        <p className="mt-4 text-[15px] text-blue-100">
          Create your first Context URL in 5 minutes. Your team will thank you.
        </p>
        <div className="mx-auto mt-8 flex max-w-md items-center gap-2 rounded-2xl bg-white/10 p-2 backdrop-blur-sm">
          <div className="flex-1 rounded-xl bg-white px-4 py-3 text-left text-[14px] text-gray-400 shadow-sm">
            <Typewriter text="https://notion.so/acme/engineering-wiki" speed={25} delay={500} showCursor={false} />
          </div>
          <button className="shrink-0 rounded-xl bg-white px-6 py-3 text-[14px] font-bold text-blue-600 shadow-sm transition-colors hover:bg-blue-50">
            Create URL &rarr;
          </button>
        </div>
        <p className="mt-5 text-[13px] text-blue-200">
          Set up in under 5 minutes
        </p>
      </AnimatedSection>
    </section>
  );
}

/* ─── Page ─── */
export default function H3ContextUrlPage() {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <Navbar />
      <Hero />
      <SocialProof />
      <BeforeAfter />
      <ProductDemo />
      <Integrations />
      <Testimonial />
      <CtaSection />
      <Footer dark={false} />
    </div>
  );
}
