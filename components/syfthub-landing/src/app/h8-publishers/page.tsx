import { BrowserFrame } from "@/components/mockups/browser-frame";
import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { CountUp } from "@/components/animations/count-up";
import { AttributionAnimated } from "./attribution-animated";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Your Writing Has Value. Keep It Attributed.",
  description:
    "Publish your body of work as a queryable endpoint. Every answer cites your original source.",
};

/* ------------------------------------------------------------------ */
/*  Section break ornament — a thin rule with a centered section mark */
/* ------------------------------------------------------------------ */
function SectionBreak() {
  return (
    <div className="relative my-12 flex items-center justify-center">
      <div className="w-full border-t border-amber-300" />
      <span className="absolute bg-white px-3 font-serif text-amber-300 select-none">
        &sect;
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Navbar                                                             */
/* ------------------------------------------------------------------ */
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-100 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <SyftHubLogo size="md" />
        <a
          href="#get-started"
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/*  Hero                                                               */
/* ------------------------------------------------------------------ */
function Hero() {
  return (
    <section className="flex min-h-[calc(100vh-57px)] flex-col items-center justify-center bg-white px-6 text-center">
      <p className="opacity-0 animate-fade-in-up text-sm font-medium text-amber-600">
        For writers &amp; researchers
      </p>

      <h1 className="mx-auto mt-5 max-w-3xl font-serif text-5xl leading-[1.12] text-gray-900 md:text-6xl">
        <span className="block overflow-hidden">
          <span className="block opacity-0 animate-fade-in-up">Your writing has value.</span>
        </span>
        <br />
        <span className="block overflow-hidden">
          <span className="block opacity-0 animate-fade-in-up animation-delay-200">Keep it attributed.</span>
        </span>
      </h1>

      <p className="opacity-0 animate-fade-in-up animation-delay-400 mx-auto mt-6 max-w-2xl font-serif text-xl leading-relaxed text-gray-500">
        AI companies train on your work without credit. Take back control. Publish a
        queryable endpoint with full attribution on every answer.
      </p>

      <div className="opacity-0 animate-fade-in-up animation-delay-500 mt-10">
        <a
          href="#get-started"
          className="inline-block rounded-lg bg-amber-600 px-6 py-3 font-medium text-white transition-colors hover:bg-amber-700"
        >
          Publish your brain endpoint &rarr;
        </a>
      </div>

      <SectionBreak />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  How it works — three visual moves                                  */
/* ------------------------------------------------------------------ */
function HowItWorks() {
  return (
    <section className="bg-amber-50/50 px-6 py-20">
      <div className="mx-auto max-w-5xl">
        <h2 className="text-center font-serif text-2xl text-gray-900">
          From corpus to queryable endpoint in three moves
        </h2>

        {/* Move 1 — Upload */}
        <div className="mt-16 flex flex-col items-center gap-10 md:flex-row">
          <div className="flex-1">
            <p className="font-serif text-3xl text-amber-600">1.</p>
            <h3 className="mt-2 text-lg font-bold text-gray-900">
              Upload your body of work
            </h3>
            <p className="mt-2 leading-relaxed text-gray-500">
              PDFs, blog archives, research papers — anything you&apos;ve
              published. We index it, you own it.
            </p>
          </div>
          <div className="w-full flex-1 md:max-w-sm">
            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-400">
                Uploaded files
              </p>
              <StaggeredList staggerMs={200} animation="animate-slide-in-right" className="space-y-2.5 text-sm text-gray-700">
                <div className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2">
                  <span>newsletter-archive.pdf</span>
                  <span className="text-emerald-600 animate-pop-in animation-delay-300">&#10003;</span>
                </div>
                <div className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2">
                  <span>research-papers/ (47 files)</span>
                  <span className="text-emerald-600 animate-pop-in animation-delay-300">&#10003;</span>
                </div>
                <div className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2">
                  <span>blog-posts.zip</span>
                  <span className="text-emerald-600 animate-pop-in animation-delay-300">&#10003;</span>
                </div>
              </StaggeredList>
            </div>
          </div>
        </div>

        {/* Move 2 — Control access */}
        <div className="mt-16 flex flex-col-reverse items-center gap-10 md:flex-row">
          <div className="w-full flex-1 md:max-w-sm">
            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-400">
                Access controls
              </p>
              <StaggeredList staggerMs={200} className="space-y-3 text-sm">
                <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
                  <span className="text-gray-700">Who can query</span>
                  <span className="font-medium text-gray-900">You decide</span>
                </div>
                <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
                  <span className="text-gray-700">Query scope</span>
                  <span className="font-medium text-gray-900">Configurable</span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-gray-700">Revoke access</span>
                  <span className="font-medium text-gray-900">Anytime</span>
                </div>
              </StaggeredList>
            </div>
          </div>
          <div className="flex-1">
            <p className="font-serif text-3xl text-amber-600">2.</p>
            <h3 className="mt-2 text-lg font-bold text-gray-900">
              Control who queries your work
            </h3>
            <p className="mt-2 leading-relaxed text-gray-500">
              Set access permissions, define query scope, and revoke anytime. Your
              content, your terms.
            </p>
          </div>
        </div>

        {/* Move 3 — Attribution */}
        <div className="mt-16 flex flex-col items-center gap-10 md:flex-row">
          <div className="flex-1">
            <p className="font-serif text-3xl text-amber-600">3.</p>
            <h3 className="mt-2 text-lg font-bold text-gray-900">
              Get cited on every answer
            </h3>
            <p className="mt-2 leading-relaxed text-gray-500">
              Every response cites your original work by name. Your ideas stay
              attributed.
            </p>
          </div>
          <div className="w-full flex-1 md:max-w-sm">
            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-400">
                Usage — March 2026
              </p>
              <CountUp target={16940} duration={1500} className="font-serif text-3xl font-bold text-gray-900 block" />
              <p className="text-sm text-gray-500">queries this month</p>
              <div className="mt-4 space-y-2 text-base text-gray-600">
                <div className="flex justify-between">
                  <span>Top article</span>
                  <span className="text-gray-700">
                    &lsquo;Why Distributed Systems Fail&rsquo;
                  </span>
                </div>
                <p className="pt-1 text-sm text-gray-400">
                  3,200 queries on top article this month
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Attribution example — the key product proof                        */
/* ------------------------------------------------------------------ */
function AttributionExample() {
  return (
    <section className="px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <h2 className="text-center font-serif text-2xl text-gray-900">
          Every answer cites you
        </h2>

        <div className="mt-10">
          <BrowserFrame url="syfthub.com/query/@yourname">
            <div className="p-6 md:p-8">
              {/* Query */}
              <div className="rounded-lg bg-gray-50 px-4 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  Query
                </p>
                <p className="mt-1 text-sm text-gray-700">
                  What are the main failure modes in distributed consensus?
                </p>
              </div>

              {/* Response */}
              <div className="mt-5">
                <p className="text-sm leading-relaxed text-gray-700">
                  Distributed consensus protocols primarily fail through three
                  mechanisms: network partitions that prevent quorum formation,
                  Byzantine faults where nodes provide conflicting information to
                  different peers, and liveness failures where the system
                  sacrifices availability to maintain consistency. In practice,
                  most production outages stem from partial partitions rather
                  than clean network splits.
                </p>
              </div>

              {/* Citations */}
              <div className="mt-6 border-t border-gray-100 pt-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  Sources from @elena-researcher
                </p>
                <div className="mt-3 space-y-1.5">
                  <p className="text-sm text-amber-700 underline decoration-amber-300 underline-offset-2">
                    &rarr; &lsquo;Why Distributed Systems Fail&rsquo; (2024) —
                    Chapter 3
                  </p>
                  <p className="text-sm text-amber-700 underline decoration-amber-300 underline-offset-2">
                    &rarr; &lsquo;Consensus Under Partition&rsquo; — Newsletter,
                    Issue #47
                  </p>
                  <p className="text-sm text-amber-700 underline decoration-amber-300 underline-offset-2">
                    &rarr; &lsquo;CAP Theorem Revisited&rsquo; — Research paper,
                    p.12-15
                  </p>
                </div>
                <p className="mt-4 text-sm text-amber-600">
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

/* ------------------------------------------------------------------ */
/*  Social proof — writer testimonial                                  */
/* ------------------------------------------------------------------ */
function Testimonial() {
  return (
    <section className="mx-6 rounded-2xl bg-amber-50/30 px-6 py-16 text-center">
      <div className="mx-auto max-w-2xl">
        <AnimatedSection>
        <blockquote className="font-serif text-xl italic leading-relaxed text-gray-700">
          &ldquo;I spent 10 years writing about distributed systems. Now those
          10 years get properly cited every time someone queries my expertise — with my
          name attached.&rdquo;
        </blockquote>
        </AnimatedSection>
        <AnimatedSection animation="animate-slide-in-left" delay={300}>
        <p className="mt-6 text-sm text-gray-400">
          — Elena R., independent researcher
        </p>
        </AnimatedSection>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Manifesto — "Take back control"                                    */
/* ------------------------------------------------------------------ */
function Manifesto() {
  return (
    <section className="px-6 py-16">
      <div className="mx-auto max-w-xl">
        <StaggeredList staggerMs={400} className="space-y-8">
          <div>
            <AnimatedSection animation="animate-clip-reveal-ltr">
              <p className="font-serif font-bold text-gray-900">
                Your work is already being used.
              </p>
            </AnimatedSection>
            <AnimatedSection delay={300}>
              <p className="mt-1 leading-relaxed text-gray-500">
                Every major AI model was trained on publicly available writing.
                Yours included.
              </p>
            </AnimatedSection>
          </div>
          <div>
            <AnimatedSection animation="animate-clip-reveal-ltr">
              <p className="font-serif font-bold text-gray-900">
                You deserve attribution.
              </p>
            </AnimatedSection>
            <AnimatedSection delay={300}>
              <p className="mt-1 leading-relaxed text-gray-500">
                SyftHub ensures every answer cites your original work — by name, with
                full source links.
              </p>
            </AnimatedSection>
          </div>
          <div>
            <AnimatedSection animation="animate-clip-reveal-ltr">
              <p className="font-serif font-bold text-gray-900">And you keep control.</p>
            </AnimatedSection>
            <AnimatedSection delay={300}>
              <p className="mt-1 leading-relaxed text-gray-500">
                Take your endpoint offline anytime. Control access. See who&apos;s
                querying what.
              </p>
            </AnimatedSection>
          </div>
        </StaggeredList>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Final CTA                                                          */
/* ------------------------------------------------------------------ */
function FinalCTA() {
  return (
    <section className="px-6 pb-12">
      <div id="get-started">
      <AnimatedSection
        className="mx-auto max-w-5xl rounded-2xl bg-amber-50 px-6 py-16 text-center"
      >
        <h2 className="font-serif text-3xl text-gray-900">
          Your ideas deserve attribution.
        </h2>
        <p className="mt-3 text-gray-500">
          Join writers and researchers who are making their work queryable — with
          proper citation on every answer.
        </p>
        <div className="mt-8">
          <a
            href="#"
            className="inline-block rounded-lg bg-gray-900 px-6 py-3 font-medium text-white transition-colors hover:bg-gray-800 animate-cta-glow"
            style={{ "--glow-color": "217 119 6" } as React.CSSProperties}
          >
            Get Started &rarr;
          </a>
        </div>
      </AnimatedSection>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
export default function H8PublishersPage() {
  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <Hero />
      <HowItWorks />
      <AttributionAnimated />
      <Testimonial />
      <SectionBreak />
      <Manifesto />
      <FinalCTA />
      <Footer dark={false} />
    </div>
  );
}
