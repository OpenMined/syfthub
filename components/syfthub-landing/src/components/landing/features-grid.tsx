import type { Feature } from "@/lib/landing-data";

interface FeaturesGridProps {
  headline?: string;
  features: Feature[];
  gradientFromHex: string;
  gradientToHex: string;
}

export function FeaturesGrid({
  headline,
  features,
  gradientFromHex,
  gradientToHex,
}: FeaturesGridProps) {
  return (
    <section className="relative py-24 md:py-32">
      {/* Subtle gradient divider */}
      <div
        className="pointer-events-none absolute left-1/2 top-0 h-px w-2/3 -translate-x-1/2 opacity-30"
        style={{
          background: `linear-gradient(90deg, transparent, ${gradientFromHex}, ${gradientToHex}, transparent)`,
        }}
      />

      <div className="mx-auto max-w-6xl px-6">
        {headline && (
          <h2 className="mb-16 text-center text-3xl font-bold tracking-tight text-white md:text-4xl">
            {headline}
          </h2>
        )}

        <div className="grid gap-6 md:grid-cols-3 md:gap-8">
          {features.map((feature, i) => (
            <div
              key={i}
              className="group relative rounded-2xl border border-white/10 bg-white/[0.03] p-8 backdrop-blur-sm transition-all duration-300 hover:border-white/20 hover:bg-white/[0.06] hover:-translate-y-1"
            >
              {/* Hover glow */}
              <div
                className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                style={{
                  background: `radial-gradient(400px circle at top, ${gradientFromHex}08, transparent)`,
                }}
              />

              <div className="relative z-10">
                <span className="text-4xl">{feature.icon}</span>
                <h3 className="mt-5 text-xl font-semibold text-white">
                  {feature.title}
                </h3>
                <p className="mt-3 leading-relaxed text-gray-400">
                  {feature.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
