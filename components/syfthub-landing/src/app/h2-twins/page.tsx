import { AnimatedSection } from "@/components/animations/animated-section";
import { CyclicPlaceholder } from "./cyclic-placeholder";
import { PanelDemoAnimated } from "./panel-demo-animated";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Convene an Expert Panel in 60 Seconds",
  description:
    "Ask a question. Get differentiated, attributed responses from digital twins grounded in real published work.",
};

export default function H2TwinsPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      {/* Navbar */}
      <nav className="sticky top-0 z-50 border-b border-stone-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <a href="/">
            <SyftHubLogo size="md" />
          </a>
          <a
            href="#try"
            className="text-sm text-stone-600 underline underline-offset-4 decoration-stone-300 hover:decoration-stone-600 transition-colors"
          >
            Get Started
          </a>
        </div>
      </nav>

      {/* Hero — two-column: copy + messenger */}
      <section className="relative flex min-h-[calc(100vh-57px)] items-center overflow-hidden px-6">
        <div className="mx-auto w-full max-w-6xl grid items-center gap-12 py-12 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
          {/* Left — copy */}
          <div className="text-center lg:text-left">
            <p className="opacity-0 animate-fade-in-up text-xs tracking-[0.2em] uppercase text-stone-400 mb-6">
              A new kind of research tool
            </p>
            <h1 className="opacity-0 animate-fade-in-up animation-delay-100 font-serif text-4xl md:text-5xl lg:text-[3.25rem] leading-[1.15] text-stone-900 mb-6">
              What if you could ask the world&rsquo;s best
              thinkers&nbsp;&mdash;&nbsp;all at once?
            </h1>
            <p className="opacity-0 animate-fade-in-up animation-delay-200 font-serif text-lg text-stone-500 max-w-md mx-auto lg:mx-0 mb-8 leading-relaxed">
              Digital twins grounded in real published work. Differentiated
              perspectives. Full source attribution.
            </p>
            <a
              href="#try"
              className="opacity-0 animate-fade-in-up animation-delay-300 inline-block text-lg text-stone-900 underline underline-offset-4 decoration-stone-300 hover:decoration-stone-900 transition-colors"
            >
              Build your first panel&nbsp;&rarr;
            </a>
          </div>

          {/* Right — messenger demo */}
          <div className="opacity-0 animate-fade-in-up animation-delay-200">
            <PanelDemoAnimated />
          </div>
        </div>
      </section>

      {/* Value strip */}
      <section className="px-6 py-20">
        <AnimatedSection className="mx-auto max-w-4xl">
          <div className="grid gap-10 md:grid-cols-3 md:gap-8 text-center">
            {[
              {
                title: "Grounded in published work",
                description:
                  "Each twin is built on real papers, books, and recorded talks.",
              },
              {
                title: "Full source attribution",
                description:
                  "Every claim cites the original work. No hallucinated positions.",
              },
              {
                title: "Real disagreements surfaced",
                description:
                  "Where experts diverge, you see exactly how and why.",
              },
            ].map((item) => (
              <div key={item.title}>
                <h3 className="text-[15px] font-semibold text-stone-900">
                  {item.title}
                </h3>
                <p className="mt-2 text-[13px] leading-relaxed text-stone-500">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </AnimatedSection>
      </section>

      {/* CTA */}
      <section id="try" className="bg-stone-100 px-6 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-3xl text-stone-900 mb-8">
            What would you ask your panel?
          </h2>
          <div className="mx-auto max-w-lg flex items-center border border-stone-300 bg-white rounded-xl overflow-hidden shadow-sm">
            <CyclicPlaceholder />
            <div className="px-5 py-4 text-stone-900 font-medium border-l border-stone-200 hover:bg-stone-50 transition-colors cursor-pointer">
              Submit&nbsp;&rarr;
            </div>
          </div>
          <p className="text-sm text-stone-400 mt-4">No sign-up required.</p>
        </div>
      </section>

      <Footer dark={false} />
    </div>
  );
}
