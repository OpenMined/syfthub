import type { LandingPageData } from "@/lib/landing-data";
import { Navbar } from "./navbar";
import { HeroSection } from "./hero-section";
import { ProblemSection } from "./problem-section";
import { FeaturesGrid } from "./features-grid";
import { HowItWorks } from "./how-it-works";
import { CTABanner } from "./cta-banner";
import { Footer } from "./footer";

interface LandingPageProps {
  data: LandingPageData;
}

export function LandingPage({ data }: LandingPageProps) {
  return (
    <div className="relative min-h-screen bg-gray-950">
      <Navbar ctaText={data.primaryCTA} />

      <HeroSection
        badge={data.badge}
        headline={data.headline}
        subheadline={data.subheadline}
        primaryCTA={data.primaryCTA}
        secondaryCTA={data.secondaryCTA}
        gradientFromHex={data.gradientFromHex}
        gradientToHex={data.gradientToHex}
      />

      <ProblemSection
        badge={data.problemBadge}
        quote={data.problemQuote}
        gradientFromHex={data.gradientFromHex}
        gradientToHex={data.gradientToHex}
      />

      <FeaturesGrid
        headline={data.featuresHeadline}
        features={data.features}
        gradientFromHex={data.gradientFromHex}
        gradientToHex={data.gradientToHex}
      />

      <HowItWorks
        steps={data.steps}
        gradientFromHex={data.gradientFromHex}
        gradientToHex={data.gradientToHex}
      />

      <CTABanner
        headline={data.ctaHeadline}
        subheadline={data.ctaSubheadline}
        ctaText={data.primaryCTA}
        gradientFromHex={data.gradientFromHex}
        gradientToHex={data.gradientToHex}
      />

      <Footer />
    </div>
  );
}
