interface CTABannerProps {
  headline: string;
  subheadline: string;
  ctaText: string;
  gradientFromHex: string;
  gradientToHex: string;
}

export function CTABanner({
  headline,
  subheadline,
  ctaText,
  gradientFromHex,
  gradientToHex,
}: CTABannerProps) {
  return (
    <section className="relative py-24 md:py-32">
      <div className="mx-auto max-w-4xl px-6">
        <div
          className="relative overflow-hidden rounded-3xl p-12 md:p-16 text-center"
          style={{
            background: `linear-gradient(135deg, ${gradientFromHex}15, ${gradientToHex}15)`,
          }}
        >
          {/* Border glow */}
          <div
            className="pointer-events-none absolute inset-0 rounded-3xl"
            style={{
              border: "1px solid",
              borderImage: `linear-gradient(135deg, ${gradientFromHex}40, ${gradientToHex}40) 1`,
            }}
          />
          {/* Use a proper border overlay */}
          <div
            className="pointer-events-none absolute inset-0 rounded-3xl border border-white/10"
          />

          {/* Background glow */}
          <div
            className="pointer-events-none absolute -top-20 left-1/2 h-40 w-80 -translate-x-1/2 rounded-full opacity-30 blur-[80px]"
            style={{
              background: `linear-gradient(90deg, ${gradientFromHex}, ${gradientToHex})`,
            }}
          />

          <div className="relative z-10">
            <h2 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
              {headline}
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-gray-400">
              {subheadline}
            </p>
            <div className="mt-8">
              <button
                className="inline-flex items-center gap-2 rounded-full px-8 py-4 text-base font-semibold text-white transition-all hover:scale-[1.02] hover:shadow-2xl active:scale-[0.98]"
                style={{
                  background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
                }}
              >
                {ctaText}
                <svg
                  className="h-4 w-4"
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
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
