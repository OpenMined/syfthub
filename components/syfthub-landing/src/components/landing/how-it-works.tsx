import type { Step } from "@/lib/landing-data";

interface HowItWorksProps {
  steps: Step[];
  gradientFromHex: string;
  gradientToHex: string;
}

export function HowItWorks({
  steps,
  gradientFromHex,
  gradientToHex,
}: HowItWorksProps) {
  return (
    <section className="relative py-24 md:py-32">
      <div className="mx-auto max-w-5xl px-6">
        <h2 className="mb-16 text-center text-3xl font-bold tracking-tight text-white md:text-4xl">
          How it works
        </h2>

        <div className="relative grid gap-12 md:grid-cols-3 md:gap-8">
          {/* Connecting line (desktop) */}
          <div
            className="pointer-events-none absolute top-10 left-[16.67%] right-[16.67%] hidden h-px opacity-20 md:block"
            style={{
              background: `linear-gradient(90deg, ${gradientFromHex}, ${gradientToHex})`,
            }}
          />

          {steps.map((step, i) => (
            <div key={i} className="relative text-center">
              {/* Step number */}
              <div className="relative mx-auto mb-6 flex h-20 w-20 items-center justify-center">
                <div
                  className="absolute inset-0 rounded-2xl opacity-20 blur-xl"
                  style={{
                    background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
                  }}
                />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                  <span
                    className="text-2xl font-bold"
                    style={{
                      background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                    }}
                  >
                    {step.number}
                  </span>
                </div>
              </div>

              <h3 className="text-xl font-semibold text-white">{step.title}</h3>
              <p className="mt-3 leading-relaxed text-gray-400">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
