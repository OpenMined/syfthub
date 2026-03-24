import Link from "next/link";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";

const pages = [
  {
    slug: "h1-mcp",
    badge: "For MCP Developers",
    badgeColor: "bg-gray-100 text-gray-600",
    headline: "Connect AI agents to private data.",
    sub: "Light mode, terminal mockups, developer-first aesthetic.",
    mode: "Light",
  },
  {
    slug: "h2-twins",
    badge: "AI-Powered Research",
    badgeColor: "bg-stone-100 text-stone-600",
    headline: "Convene an expert panel in 60 seconds",
    sub: "Editorial/serif typography, warm stone palette, panel mockup.",
    mode: "Light (cream)",
  },
  {
    slug: "h3-context-url",
    badge: "For Engineering Teams",
    badgeColor: "bg-blue-50 text-blue-600",
    headline: "Stop being your team's human search engine",
    sub: "Slack-like chat mockup, before/after comparison, workplace palette.",
    mode: "Light (blue)",
  },
  {
    slug: "h4-pkm",
    badge: "Private & Local",
    badgeColor: "bg-purple-100 text-purple-600",
    headline: "Query your entire vault. Nothing leaves.",
    sub: "Dark mode, knowledge graph background, search demo, Obsidian vibes.",
    mode: "Dark (purple)",
  },
  {
    slug: "h5-agent-perms",
    badge: "Agent Security",
    badgeColor: "bg-emerald-100 text-emerald-700",
    headline: "Share your AI agent. Control everything.",
    sub: "Dark mode, permissions dashboard, scary Slack message, before/after table.",
    mode: "Dark (emerald)",
  },
  {
    slug: "h7-consultants",
    badge: "For Data Consultants",
    badgeColor: "bg-gray-100 text-gray-600",
    headline: "Give clients query access. Keep every byte.",
    sub: "Clean white professional, narrative storytelling, browser frame mockup.",
    mode: "Light (white)",
  },
  {
    slug: "h8-publishers",
    badge: "For Writers & Researchers",
    badgeColor: "bg-amber-50 text-amber-700",
    headline: "Your writing has value. Keep it attributed.",
    sub: "Serif editorial, warm amber, attribution mockup, writer manifesto.",
    mode: "Light (warm)",
  },
];

export default function IndexPage() {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <div className="mx-auto max-w-4xl px-6 py-20">
        <div className="mb-16">
          <div className="mb-4">
            <SyftHubLogo size="lg" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            Landing Page Hypotheses
          </h1>
          <p className="mt-2 text-gray-500">
            7 bespoke pages — each with its own personality, layout, and visual language.
          </p>
        </div>

        <div className="space-y-4">
          {pages.map((page) => (
            <Link
              key={page.slug}
              href={`/${page.slug}`}
              className="group flex items-start gap-6 rounded-lg border border-gray-100 p-5 transition-colors hover:border-gray-200 hover:bg-gray-50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${page.badgeColor}`}>
                    {page.badge}
                  </span>
                  <span className="text-xs text-gray-400">{page.mode}</span>
                </div>
                <h2 className="text-base font-semibold text-gray-900">
                  {page.headline}
                </h2>
                <p className="mt-1 text-sm text-gray-500">{page.sub}</p>
              </div>
              <div className="shrink-0 pt-1 text-sm text-gray-400 transition-colors group-hover:text-gray-600">
                &rarr;
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
