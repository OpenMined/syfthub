export interface Feature {
  icon: string;
  title: string;
  description: string;
}

export interface Step {
  number: number;
  title: string;
  description: string;
}

export interface LandingPageData {
  slug: string;
  badge: string;
  headline: string;
  subheadline: string;
  primaryCTA: string;
  secondaryCTA?: string;
  problemBadge?: string;
  problemQuote: string;
  problemDescription?: string;
  features: Feature[];
  featuresHeadline?: string;
  steps: Step[];
  ctaHeadline: string;
  ctaSubheadline: string;
  gradientFrom: string;
  gradientTo: string;
  gradientFromHex: string;
  gradientToHex: string;
}

export const pages: Record<string, LandingPageData> = {
  "h1-mcp": {
    slug: "h1-mcp",
    badge: "FOR MCP DEVELOPERS",
    headline: "Connect AI Agents to Private Data.\nZero Data Copying.",
    subheadline:
      "Add Syft as an MCP server. Your agents query live data through access-controlled endpoints. Set up in 10 minutes.",
    primaryCTA: "Add Your First Private Data Source",
    secondaryCTA: "See Documentation",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "MCP made tool integration easy. But when the data is sensitive, you're still copying files, managing ingestion pipelines, and trusting third parties with your most valuable assets.",
    features: [
      {
        icon: "🔗",
        title: "Live Data Access",
        description:
          "No copying, no ingestion. Your agents query data where it lives — in real time, through a secure endpoint.",
      },
      {
        icon: "🔒",
        title: "Granular Permissions",
        description:
          "Scope who can query what. Rate limits, time-boxing, and instant revocation — all from one dashboard.",
      },
      {
        icon: "⚡",
        title: "Any MCP Client",
        description:
          "Works with Claude Desktop, Cursor, VS Code, and any MCP-compatible agent out of the box.",
      },
    ],
    featuresHeadline: "Everything your agents need. Nothing they shouldn't have.",
    steps: [
      {
        number: 1,
        title: "Install",
        description: "Install the Syft MCP server package via npm or pip.",
      },
      {
        number: 2,
        title: "Connect",
        description:
          "Point it at your data source and configure access controls.",
      },
      {
        number: 3,
        title: "Query",
        description: "Start querying from any MCP-compatible AI client.",
      },
    ],
    ctaHeadline: "Ready to connect your first data source?",
    ctaSubheadline:
      "Join thousands of developers building secure AI integrations with SyftHub.",
    gradientFrom: "from-indigo-500",
    gradientTo: "to-blue-500",
    gradientFromHex: "#6366f1",
    gradientToHex: "#3b82f6",
  },

  "h2-twins": {
    slug: "h2-twins",
    badge: "AI-POWERED RESEARCH",
    headline: "Convene an Expert Panel\nin 60 Seconds",
    subheadline:
      "Ask a question. Get differentiated, attributed responses from digital twins grounded in real published work.",
    primaryCTA: "Build Your Expert Panel",
    secondaryCTA: "Watch Demo",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "Reading everything a thinker has published takes months. Reaching them directly? Impossible. Generic AI gives you generic answers — not the specific, nuanced positions of the experts you actually want to hear from.",
    features: [
      {
        icon: "🎭",
        title: "Multi-Expert Debate",
        description:
          "3–5 experts respond to a single question with differentiated perspectives. Not summaries — actual positions.",
      },
      {
        icon: "📚",
        title: "Grounded in Real Work",
        description:
          "Every response cites source material from the expert's actual publications, papers, and interviews.",
      },
      {
        icon: "⚔️",
        title: "Adversarial Mode",
        description:
          "Have experts debate each other. See where they agree, where they diverge, and why.",
      },
    ],
    featuresHeadline: "Your research team, assembled in seconds.",
    steps: [
      {
        number: 1,
        title: "Choose Experts",
        description:
          "Select from public figures or create twins from any published corpus.",
      },
      {
        number: 2,
        title: "Ask Your Question",
        description: "Type a question. The panel convenes instantly.",
      },
      {
        number: 3,
        title: "Get Attributed Answers",
        description:
          "Receive differentiated responses, each grounded in real published work.",
      },
    ],
    ctaHeadline: "What would you ask your expert panel?",
    ctaSubheadline:
      "Start with any question. Get answers grounded in decades of published expertise.",
    gradientFrom: "from-violet-500",
    gradientTo: "to-purple-500",
    gradientFromHex: "#8b5cf6",
    gradientToHex: "#a855f7",
  },

  "h3-context-url": {
    slug: "h3-context-url",
    badge: "FOR ENGINEERING TEAMS",
    headline: "Stop Being Your Team's\nHuman Search Engine",
    subheadline:
      "Turn your team's docs into a single URL. Anyone pastes it into their AI and asks. The AI knows your docs. You stop being the bottleneck.",
    primaryCTA: "Create Your Context URL",
    secondaryCTA: "See How It Works",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "Your team has a wiki nobody reads. A Confluence graveyard. A Google Drive labyrinth. So they Slack you instead — because you're faster than search. Meanwhile, everyone uses AI daily, but the AI doesn't know your internal docs.",
    features: [
      {
        icon: "🔗",
        title: "One URL, All Your Docs",
        description:
          "Notion, Confluence, Google Drive — consolidated into a single queryable link.",
      },
      {
        icon: "🤖",
        title: "Works in Any AI",
        description:
          "ChatGPT, Claude, Cursor — your team uses whatever they already use. Zero new tools to learn.",
      },
      {
        icon: "🔄",
        title: "Always Current",
        description:
          "Changes to your docs automatically update the context. No manual re-syncing.",
      },
    ],
    featuresHeadline: "Your team's knowledge, in every AI conversation.",
    steps: [
      {
        number: 1,
        title: "Connect Sources",
        description: "Link your Notion, Confluence, or Google Drive docs.",
      },
      {
        number: 2,
        title: "Generate URL",
        description:
          "Get a single shareable Context URL for your knowledge base.",
      },
      {
        number: 3,
        title: "Share in Slack",
        description:
          "Your team pastes it into any AI chat and asks away.",
      },
    ],
    ctaHeadline: "Free yourself from being the answer machine.",
    ctaSubheadline:
      "Create a Context URL for your team's docs in minutes. Your knowledge, always accessible.",
    gradientFrom: "from-cyan-500",
    gradientTo: "to-teal-500",
    gradientFromHex: "#06b6d4",
    gradientToHex: "#14b8a6",
  },

  "h4-pkm": {
    slug: "h4-pkm",
    badge: "PRIVATE & LOCAL",
    headline: "Query Your Entire Vault.\nNothing Leaves Your Machine.",
    subheadline:
      "AI-powered search across your Obsidian vault — or any personal knowledge base. Completely private. Completely local. 15 minutes to set up.",
    primaryCTA: "Query Your Vault Privately",
    secondaryCTA: "Learn More",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "1,000+ notes. Years of curated thinking. Folders, tags, backlinks — you built an intricate system. But when you need a specific answer, you still can't find it without manually searching through everything.",
    features: [
      {
        icon: "🏠",
        title: "100% Local",
        description:
          "No cloud. No uploads. No third-party services. Your data never leaves your machine.",
      },
      {
        icon: "📝",
        title: "Works with Obsidian",
        description:
          "Native support for .md files, frontmatter, and any folder structure you've built.",
      },
      {
        icon: "📍",
        title: "Source Citations",
        description:
          "Every answer points to the specific notes and passages it drew from.",
      },
    ],
    featuresHeadline: "Your second brain, finally searchable.",
    steps: [
      {
        number: 1,
        title: "Install Syft Space",
        description: "One command. Runs entirely on your machine.",
      },
      {
        number: 2,
        title: "Connect Your Vault",
        description:
          "Point it at your Obsidian vault or any folder of documents.",
      },
      {
        number: 3,
        title: "Start Querying",
        description:
          "Ask questions in natural language. Get answers grounded in your notes.",
      },
    ],
    ctaHeadline: "Your vault has the answers. Now you can find them.",
    ctaSubheadline:
      "Set up in 15 minutes. Query in natural language. Everything stays on your machine.",
    gradientFrom: "from-purple-500",
    gradientTo: "to-fuchsia-500",
    gradientFromHex: "#a855f7",
    gradientToHex: "#d946ef",
  },

  "h5-agent-perms": {
    slug: "h5-agent-perms",
    badge: "AGENT SECURITY",
    headline: "Share Your AI Agent.\nControl Everything.",
    subheadline:
      "Generate shareable access links with query-only, rate-limited, time-boxed permissions. See who queries what. Revoke instantly.",
    primaryCTA: "Secure Your First Agent",
    secondaryCTA: "View Pricing",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "You built a powerful AI agent. Your client wants access. But handing over an API key means handing over everything — every data source, every tool, every capability. There's no middle ground between 'full access' and 'no access.'",
    features: [
      {
        icon: "🔑",
        title: "Scoped Access Links",
        description:
          "Query-only, time-boxed, rate-limited. Each link is its own permission boundary.",
      },
      {
        icon: "📊",
        title: "Real-Time Dashboard",
        description:
          "See every query, every user, every timestamp. Know exactly how your agent is being used.",
      },
      {
        icon: "🚫",
        title: "Instant Revocation",
        description:
          "One click to cut access. No waiting, no ambiguity, no lingering keys.",
      },
    ],
    featuresHeadline: "Fine-grained control for every agent interaction.",
    steps: [
      {
        number: 1,
        title: "Connect Your Agent",
        description:
          "Link your MCP agent, API, or custom tool to SyftHub.",
      },
      {
        number: 2,
        title: "Generate Access Links",
        description:
          "Set permissions: who can query, what they can access, for how long.",
      },
      {
        number: 3,
        title: "Monitor & Control",
        description:
          "Watch usage in real-time. Revoke access the moment you need to.",
      },
    ],
    ctaHeadline: "Stop choosing between sharing and security.",
    ctaSubheadline:
      "Give your clients exactly the access they need — and not a byte more.",
    gradientFrom: "from-indigo-500",
    gradientTo: "to-emerald-500",
    gradientFromHex: "#6366f1",
    gradientToHex: "#10b981",
  },

  "h7-consultants": {
    slug: "h7-consultants",
    badge: "FOR DATA CONSULTANTS",
    headline: "Give Clients Query Access.\nKeep Every Byte.",
    subheadline:
      "Deploy a private endpoint on NDA-protected client data. They ask questions, get answers. Raw data never moves.",
    primaryCTA: "Deploy Your First Private Endpoint",
    secondaryCTA: "See Use Cases",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "Every engagement, same friction: the NDA says data can't move. The client needs answers yesterday. So you become the human API — running queries manually, delivering insights by email, scheduling calls to walk through results.",
    features: [
      {
        icon: "🛡️",
        title: "NDA-Compliant by Architecture",
        description:
          "Data stays where it is. Not a policy — a technical guarantee that holds up to any audit.",
      },
      {
        icon: "🔗",
        title: "Client-Facing Query Link",
        description:
          "Send your client a link. They ask questions in plain language. No technical setup on their end.",
      },
      {
        icon: "📋",
        title: "Full Audit Trail",
        description:
          "Every query logged with timestamps. Demonstrate compliance to any stakeholder, anytime.",
      },
    ],
    featuresHeadline: "The data doesn't move. The insights do.",
    steps: [
      {
        number: 1,
        title: "Connect Client Data",
        description:
          "Point Syft Space at the client's dataset. Nothing gets copied or uploaded.",
      },
      {
        number: 2,
        title: "Set Permissions",
        description:
          "Define what can be queried, by whom, and for how long.",
      },
      {
        number: 3,
        title: "Share the Link",
        description:
          "Send your client a query link. They self-serve. You stop being the bottleneck.",
      },
    ],
    ctaHeadline: "Win the deal. Keep the data.",
    ctaSubheadline:
      "Deploy a private, queryable endpoint for your next client engagement.",
    gradientFrom: "from-slate-400",
    gradientTo: "to-blue-500",
    gradientFromHex: "#94a3b8",
    gradientToHex: "#3b82f6",
  },

  "h8-publishers": {
    slug: "h8-publishers",
    badge: "FOR WRITERS & RESEARCHERS",
    headline: "Your Writing Has Value.\nNow It Can Earn.",
    subheadline:
      "Publish your body of work as a queryable endpoint. Set your price. Get attribution-based revenue. Keep full control.",
    primaryCTA: "Publish Your Brain Endpoint",
    secondaryCTA: "See How It Works",
    problemBadge: "THE PROBLEM",
    problemQuote:
      "AI companies train on your work without permission. You get nothing — not credit, not compensation, not even a notification. Your 10 years of published thinking is being consumed for free.",
    features: [
      {
        icon: "🧠",
        title: "Queryable Brain Endpoint",
        description:
          "Your entire corpus, live and searchable. Readers and AI agents query your actual published thinking.",
      },
      {
        icon: "💰",
        title: "You Set the Price",
        description:
          "Per-query pricing or bundled access packages. Your content, your terms, your revenue.",
      },
      {
        icon: "📎",
        title: "Full Attribution",
        description:
          "Every response cites your original work. Your name stays on your ideas — always.",
      },
    ],
    featuresHeadline: "Your expertise, monetized and attributed.",
    steps: [
      {
        number: 1,
        title: "Upload Your Corpus",
        description:
          "PDFs, blog posts, papers — anything you've published goes in.",
      },
      {
        number: 2,
        title: "Set Your Price",
        description:
          "Choose per-query pricing or offer bundled access packages.",
      },
      {
        number: 3,
        title: "Start Earning",
        description:
          "Get paid every time someone queries your expertise. Full attribution included.",
      },
    ],
    ctaHeadline: "Your ideas deserve compensation.",
    ctaSubheadline:
      "Join the creators who are turning their published work into a revenue stream.",
    gradientFrom: "from-amber-500",
    gradientTo: "to-orange-500",
    gradientFromHex: "#f59e0b",
    gradientToHex: "#f97316",
  },
};

export const allPages = Object.values(pages);
