import { Badge } from "@/components/ui/badge";

interface ProblemSectionProps {
  badge?: string;
  quote: string;
  gradientFromHex: string;
  gradientToHex: string;
}

export function ProblemSection({
  badge = "THE PROBLEM",
  quote,
  gradientFromHex,
  gradientToHex,
}: ProblemSectionProps) {
  return (
    <section className="relative py-24 md:py-32">
      <div className="mx-auto max-w-4xl px-6 text-center">
        <Badge
          variant="outline"
          className="mb-8 border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-white/50"
        >
          {badge}
        </Badge>

        <blockquote className="relative">
          {/* Decorative quote mark */}
          <span
            className="absolute -top-8 left-1/2 -translate-x-1/2 text-8xl font-bold leading-none opacity-10"
            style={{
              background: `linear-gradient(135deg, ${gradientFromHex}, ${gradientToHex})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            &ldquo;
          </span>
          <p className="relative text-2xl font-medium leading-relaxed text-gray-300 md:text-3xl md:leading-relaxed">
            {quote}
          </p>
        </blockquote>
      </div>
    </section>
  );
}
