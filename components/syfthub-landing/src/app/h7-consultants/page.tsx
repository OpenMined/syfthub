import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { ProcessFlowAnimated } from "./process-flow-animated";
import { ClientMockupAnimated } from "./client-mockup-animated";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Give Clients Query Access, Keep Every Byte",
  description:
    "Deploy a private endpoint on NDA-protected client data. They ask questions, get answers. Raw data never moves.",
};

function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-100 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <SyftHubLogo size="md" />
        <a
          href="#get-started"
          className="rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white transition-all hover:bg-gray-800 hover:shadow-md"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-57px)] items-center overflow-hidden">
      {/* Subtle background texture */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-gray-50/80 via-white to-white" />
      <div className="pointer-events-none absolute right-0 top-0 h-[500px] w-[500px] rounded-full bg-blue-50/50 blur-3xl" />

      <div className="relative mx-auto w-full max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-3xl text-center">
          <p className="opacity-0 animate-fade-in-up inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-1.5 text-[13px] font-medium text-gray-600 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            For Data Consultants
          </p>

          <h1 className="opacity-0 animate-fade-in-up animation-delay-100 mt-8 text-[2.75rem] font-extrabold leading-[1.08] tracking-[-0.03em] text-gray-900 md:text-[3.5rem]">
            Give clients query access.
            <br />
            <span className="text-gray-400">Keep every byte.</span>
          </h1>

          <p className="opacity-0 animate-fade-in-up animation-delay-200 mx-auto mt-6 max-w-lg text-[17px] leading-relaxed text-gray-500">
            Deploy a private endpoint on NDA-protected data. Clients ask
            questions and get answers. Raw data never moves.
          </p>

          <div className="opacity-0 animate-fade-in-up animation-delay-300 mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <a
              href="#get-started"
              className="inline-block rounded-xl bg-gray-900 px-7 py-3.5 text-[15px] font-semibold text-white shadow-[0_1px_2px_rgba(0,0,0,0.05),0_4px_12px_rgba(0,0,0,0.15)] transition-all hover:bg-gray-800 hover:shadow-[0_1px_2px_rgba(0,0,0,0.05),0_8px_20px_rgba(0,0,0,0.2)] hover:-translate-y-0.5"
            >
              Deploy Your First Endpoint &rarr;
            </a>
          </div>

          {/* Trust bar */}
          <div className="opacity-0 animate-fade-in-up animation-delay-400 mt-12 flex items-center justify-center gap-6 text-[13px] text-gray-400">
            <span>Trusted by consultants at</span>
            {["McKinsey", "Deloitte", "BCG", "Accenture"].map((name) => (
              <span key={name} className="font-semibold text-gray-500">{name}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Scenario() {
  return (
    <section className="px-6 py-24">
      <div className="mx-auto max-w-5xl">
        <div className="grid gap-12 md:grid-cols-[1fr_1.2fr] md:items-center">
          {/* Left — narrative */}
          <div>
            <AnimatedSection>
              <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-400">
                The problem
              </p>
              <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
                Sound familiar?
              </h2>
            </AnimatedSection>
            <StaggeredList staggerMs={250} className="mt-8 space-y-5">
              <p className="text-[16px] leading-relaxed text-gray-500">
                Your client has a dataset they need analyzed. The NDA says data
                can&apos;t leave their systems. They need answers by Friday.
              </p>
              <p className="text-[16px] leading-relaxed text-gray-500">
                So you become the <span className="font-semibold text-gray-700">human API</span>. You SSH into their server, run queries
                manually, copy results into a slide deck, and email it over. Every
                follow-up question means another call.
              </p>
            </StaggeredList>
          </div>

          {/* Right — the pivot question in a card */}
          <AnimatedSection delay={300}>
            <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-8 shadow-[0_4px_24px_rgba(0,0,0,0.06)] md:p-10">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-900 text-white">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <p className="mt-6 text-xl font-bold leading-snug tracking-[-0.01em] text-gray-900 md:text-2xl">
                What if your client could ask the data directly — without the
                data ever moving?
              </p>
              <p className="mt-4 text-[15px] leading-relaxed text-gray-500">
                SyftHub deploys a private query endpoint on their infrastructure.
                You share a link. They get answers. You stay productive.
              </p>
            </div>
          </AnimatedSection>
        </div>
      </div>
    </section>
  );
}

function Compliance() {
  const items = [
    {
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" className="text-emerald-600">
          <path d="M12 3l8 4v5c0 4.418-3.358 8.268-8 9-4.642-.732-8-4.582-8-9V7l8-4z" />
          <path d="M9 12l2 2 4-4" strokeLinecap="round" />
        </svg>
      ),
      title: "NDA-compliant by architecture",
      description:
        "Data stays where it is. Not a policy — a technical guarantee. Zero data movement.",
      accent: "bg-emerald-50 border-emerald-100",
    },
    {
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-blue-600">
          <rect x="6" y="4" width="12" height="17" rx="2" />
          <path d="M9 2h6v3a1 1 0 01-1 1h-4a1 1 0 01-1-1V2z" />
          <path d="M9 12h6M9 15h4" strokeLinecap="round" />
        </svg>
      ),
      title: "Full audit trail",
      description:
        "Every query logged with timestamps. Demonstrate compliance to any stakeholder.",
      accent: "bg-blue-50 border-blue-100",
    },
    {
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-amber-600">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
      title: "Time-boxed access",
      description:
        "Set expiration dates. Access auto-revokes when the engagement ends. No lingering permissions.",
      accent: "bg-amber-50 border-amber-100",
    },
  ];

  return (
    <section className="bg-gray-50 px-6 py-24">
      <div className="mx-auto max-w-5xl">
        <AnimatedSection>
          <div className="text-center">
            <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-400">
              Security & compliance
            </p>
            <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
              Built for regulated engagements
            </h2>
            <p className="mx-auto mt-4 max-w-lg text-[15px] text-gray-500">
              Every feature designed around the constraints consultants actually face.
            </p>
          </div>
        </AnimatedSection>

        <StaggeredList staggerMs={200} className="mt-14 grid gap-6 md:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.title}
              className={`rounded-2xl border ${item.accent} p-6 shadow-sm transition-shadow hover:shadow-md`}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white shadow-sm">
                {item.icon}
              </div>
              <h3 className="mt-4 text-[15px] font-bold text-gray-900">
                {item.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-gray-500">
                {item.description}
              </p>
            </div>
          ))}
        </StaggeredList>
      </div>
    </section>
  );
}

/* ─── Social proof / stats band ─── */
function StatsBar() {
  return (
    <section className="border-y border-gray-100 bg-white px-6 py-12">
      <AnimatedSection className="mx-auto flex max-w-4xl flex-col items-center gap-8 md:flex-row md:justify-between">
        {[
          { value: "0 bytes", label: "of raw data transferred" },
          { value: "< 5 min", label: "to deploy an endpoint" },
          { value: "100%", label: "audit trail coverage" },
        ].map((stat) => (
          <div key={stat.label} className="text-center md:text-left">
            <p className="text-2xl font-extrabold tracking-[-0.02em] text-gray-900">
              {stat.value}
            </p>
            <p className="mt-1 text-[13px] text-gray-400">{stat.label}</p>
          </div>
        ))}
      </AnimatedSection>
    </section>
  );
}

function FinalCTA() {
  return (
    <section id="get-started" className="px-6 pb-16 pt-8">
      <AnimatedSection className="mx-auto max-w-4xl overflow-hidden rounded-3xl bg-gray-900 px-8 py-16 text-center shadow-[0_8px_32px_rgba(0,0,0,0.2)] md:px-16">
        <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-white md:text-4xl">
          Win the deal. Keep the data.
        </h2>
        <p className="mt-4 text-[15px] text-gray-400">
          Deploy a private endpoint for your next engagement.
        </p>
        <div className="mt-8">
          <a
            href="#"
            className="inline-block rounded-xl bg-white px-7 py-3.5 text-[15px] font-bold text-gray-900 shadow-sm transition-all hover:bg-gray-50 hover:shadow-md"
          >
            Get Started &rarr;
          </a>
        </div>
        <p className="mt-4 text-[13px] text-gray-500">
          Set up in under 5 minutes
        </p>
      </AnimatedSection>
    </section>
  );
}

export default function H7ConsultantsPage() {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <Navbar />
      <Hero />
      <Scenario />
      <ProcessFlowAnimated />
      <ClientMockupAnimated />
      <StatsBar />
      <Compliance />
      <FinalCTA />
      <Footer dark={false} />
    </div>
  );
}
