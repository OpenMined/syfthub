import { Badge } from "@/components/ui/badge";

interface HeroSectionProps {
  badge: string;
  headline: string;
  subheadline: string;
  primaryCTA: string;
  secondaryCTA?: string;
  gradientFromHex: string;
  gradientToHex: string;
}

export function HeroSection({
  badge,
  headline,
  subheadline,
  primaryCTA,
  secondaryCTA,
  gradientFromHex,
  gradientToHex,
}: HeroSectionProps) {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden pt-20">
      {/* Gradient blobs */}
      <div
        className="pointer-events-none absolute -top-40 -left-40 h-[500px] w-[500px] rounded-full opacity-20 blur-[120px] animate-gradient-shift"
        style={{ background: gradientFromHex }}
      />
      <div
        className="pointer-events-none absolute -right-40 -bottom-40 h-[500px] w-[500px] rounded-full opacity-15 blur-[120px] animate-gradient-shift"
        style={{ background: gradientToHex, animationDelay: "4s" }}
      />
      <div
        className="pointer-events-none absolute top-1/3 left-1/2 h-[300px] w-[300px] -translate-x-1/2 rounded-full opacity-10 blur-[100px]"
        style={{
          background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
        }}
      />

      {/* Grid pattern overlay */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      <div className="relative z-10 mx-auto max-w-4xl px-6 text-center">
        <div className="animate-fade-in-up">
          <Badge
            variant="outline"
            className="mb-8 border-white/20 bg-white/5 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-white/70"
          >
            {badge}
          </Badge>
        </div>

        <h1 className="animate-fade-in-up animation-delay-200 text-5xl font-bold leading-[1.08] tracking-tight text-white md:text-6xl lg:text-7xl whitespace-pre-line">
          {headline}
        </h1>

        <p className="mx-auto mt-8 max-w-2xl animate-fade-in-up animation-delay-400 text-lg leading-relaxed text-gray-400 md:text-xl">
          {subheadline}
        </p>

        <div className="mt-10 flex animate-fade-in-up animation-delay-600 flex-col items-center justify-center gap-4 sm:flex-row">
          <button
            className="group relative inline-flex items-center gap-2 rounded-full px-8 py-4 text-base font-semibold text-white transition-all hover:scale-[1.02] hover:shadow-2xl active:scale-[0.98]"
            style={{
              background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
            }}
          >
            {primaryCTA}
            <svg
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M13 7l5 5m0 0l-5 5m5-5H6"
              />
            </svg>
          </button>

          {secondaryCTA && (
            <button className="inline-flex items-center gap-2 rounded-full border border-white/20 px-8 py-4 text-base font-medium text-white/80 transition-all hover:border-white/40 hover:text-white">
              {secondaryCTA}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
