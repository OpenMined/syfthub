# SyftHub Landing Pages — Implementation Plan

## Overview
7 landing pages for SyftHub hypothesis testing, each with unique copy/branding but shared structural components. Built with Next.js 15 App Router + Tailwind CSS v4 + shadcn/ui.

## Design System

### Colors (dark-mode-first, each page has accent gradient)
- Base background: `#030712` (gray-950)
- Card backgrounds: `white/5` with `backdrop-blur`
- Border: `white/10`
- Primary text: `white`
- Secondary text: `gray-400`
- Each page has its own gradient accent pair

### Typography (Geist Sans already configured)
- Hero headline: `text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight`
- Section headline: `text-3xl md:text-4xl font-bold tracking-tight`
- Body: `text-lg text-gray-400 leading-relaxed`
- Badge: `text-xs font-semibold uppercase tracking-widest`

### Spacing
- Section: `py-24 md:py-32`
- Max content: `max-w-6xl mx-auto px-6`
- Card gaps: `gap-6 md:gap-8`
- Component padding: `p-6 md:p-8`

### Component Patterns
- Cards: `bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl`
- Primary CTA: gradient background, `rounded-full px-8 py-4 text-lg font-semibold`
- Secondary CTA: `border border-white/20 rounded-full px-8 py-4`

---

## File Structure

```
src/
├── app/
│   ├── layout.tsx              (update: dark class, metadata)
│   ├── globals.css             (update: dark theme vars, custom utilities)
│   ├── page.tsx                (index: links to all pages)
│   ├── h1-mcp/page.tsx
│   ├── h2-twins/page.tsx
│   ├── h3-context-url/page.tsx
│   ├── h4-pkm/page.tsx
│   ├── h5-agent-perms/page.tsx
│   ├── h7-consultants/page.tsx
│   └── h8-publishers/page.tsx
├── components/
│   ├── ui/                     (shadcn - already installed)
│   └── landing/
│       ├── navbar.tsx
│       ├── hero-section.tsx
│       ├── problem-section.tsx
│       ├── features-grid.tsx
│       ├── how-it-works.tsx
│       ├── cta-banner.tsx
│       └── footer.tsx
└── lib/
    ├── utils.ts                (already exists)
    └── landing-data.ts         (page content/copy data)
```

---

## Wave 1: Foundation (no dependencies)

### File: `src/app/globals.css`
- Override dark theme to use near-black background
- Add custom gradient animation keyframes
- Add glass morphism utilities

### File: `src/app/layout.tsx`
- Add `dark` class to html element
- Update metadata
- Set `bg-gray-950 text-white` on body

### File: `src/lib/landing-data.ts`
- TypeScript interfaces for page content
- All 7 page data objects with copy, colors, features, steps

---

## Wave 2: Shared Components (depends on Wave 1)

### File: `src/components/landing/navbar.tsx`
- Sticky top navbar, transparent bg with backdrop-blur on scroll
- Logo text "SyftHub" + CTA button
- Props: ctaText, ctaHref, accentColor

### File: `src/components/landing/hero-section.tsx`
- Full viewport hero with gradient blob backgrounds
- Badge pill, headline, subheadline, primary + secondary CTA
- Props: badge, headline, subheadline, primaryCTA, secondaryCTA, gradientFrom, gradientTo

### File: `src/components/landing/problem-section.tsx`
- Dark section with "The Problem" badge
- Large quote-style text describing the pain point
- Props: badge, quote, description

### File: `src/components/landing/features-grid.tsx`
- 3-column responsive grid of glass cards
- Each card: icon (emoji/text), title, description
- Props: headline, features[], accentColor

### File: `src/components/landing/how-it-works.tsx`
- 3 numbered steps with connecting visual
- Props: steps[], accentColor

### File: `src/components/landing/cta-banner.tsx`
- Full-width gradient section
- Large headline + CTA button
- Props: headline, subheadline, ctaText, gradientFrom, gradientTo

### File: `src/components/landing/footer.tsx`
- Minimal: SyftHub logo, copyright, link row

---

## Wave 3: Landing Pages (depends on Wave 2)

Each page file imports shared components and passes unique content from landing-data.ts.

### Pages:
1. `src/app/h1-mcp/page.tsx` — MCP Permissioning (indigo→blue)
2. `src/app/h2-twins/page.tsx` — Digital Twin Panels (violet→purple)
3. `src/app/h3-context-url/page.tsx` — Context URL Internal Knowledge (cyan→teal)
4. `src/app/h4-pkm/page.tsx` — Private PKM (purple→fuchsia)
5. `src/app/h5-agent-perms/page.tsx` — Agent Permissioning (indigo→emerald)
6. `src/app/h7-consultants/page.tsx` — Consultant Endpoints (slate→blue)
7. `src/app/h8-publishers/page.tsx` — Publisher Monetization (amber→orange)

### File: `src/app/page.tsx`
- Index page with cards linking to each landing page
- Shows hypothesis name + one-line description

---

## Wave 4: Validation
- `npm run build` to verify no type errors
- Visual check instructions

---

## Per-Page Content

### H1 — MCP Permissioning Layer
- Badge: "FOR MCP DEVELOPERS"
- Headline: "Connect AI Agents to Private Data. Zero Data Copying."
- Sub: "Add Syft as an MCP server. Your agents query live data through access-controlled endpoints. Set up in 10 minutes."
- Problem: "MCP made tool integration easy. But when the data is sensitive, you're still copying files, managing ingestion pipelines, and trusting third parties with your most valuable assets."
- Features:
  1. 🔗 Live Data Access — "No copying, no ingestion. Your agents query data where it lives."
  2. 🔒 Granular Permissions — "Scope who can query what. Rate limits, time-boxing, instant revocation."
  3. ⚡ Any MCP Client — "Works with Claude Desktop, Cursor, VS Code, and any MCP-compatible agent."
- Steps:
  1. Install — "Install the Syft MCP server package via npm or pip."
  2. Connect — "Point it at your data source and configure access controls."
  3. Query — "Start querying from any MCP-compatible AI client."
- CTA: "Add Your First Private Data Source"

### H2 — Digital Twin Expert Panels
- Badge: "AI-POWERED RESEARCH"
- Headline: "Convene an Expert Panel in 60 Seconds"
- Sub: "Ask a question. Get differentiated, attributed responses from digital twins grounded in real published work."
- Problem: "Reading everything a thinker has published takes months. Reaching them directly? Impossible. Generic AI gives you generic answers — not the specific, nuanced positions of the experts you actually want to hear from."
- Features:
  1. 🎭 Multi-Expert Debate — "3–5 experts respond to a single question with differentiated perspectives."
  2. 📚 Grounded in Real Work — "Every response cites source material from the expert's actual publications."
  3. ⚔️ Adversarial Mode — "Have experts debate each other. See where they agree and where they diverge."
- Steps:
  1. Choose Experts — "Select from public figures or create twins from any published corpus."
  2. Ask Your Question — "Type a question. The panel convenes instantly."
  3. Get Attributed Answers — "Receive differentiated responses, each grounded in real published work."
- CTA: "Build Your Expert Panel"

### H3.1 — Context URL (Internal Knowledge)
- Badge: "FOR ENGINEERING TEAMS"
- Headline: "Stop Being Your Team's Human Search Engine"
- Sub: "Turn your team's docs into a single URL. Anyone pastes it into their AI and asks. The AI knows your docs. You stop being the bottleneck."
- Problem: "Your team has a wiki nobody reads. A Confluence graveyard. A Google Drive labyrinth. So they Slack you instead — because you're faster than search. Meanwhile, everyone on the team uses AI daily, but the AI doesn't know your internal docs."
- Features:
  1. 🔗 One URL, All Your Docs — "Notion, Confluence, Google Drive — consolidated into a single queryable link."
  2. 🤖 Works in Any AI — "ChatGPT, Claude, Cursor — your team uses whatever they already use."
  3. 🔄 Always Current — "Changes to your docs automatically update the context."
- Steps:
  1. Connect Sources — "Link your Notion, Confluence, or Google Drive docs."
  2. Generate URL — "Get a single shareable Context URL for your knowledge base."
  3. Share in Slack — "Your team pastes it into any AI chat and asks away."
- CTA: "Create Your Context URL"

### H4 — Private Local PKM
- Badge: "PRIVATE & LOCAL"
- Headline: "Query Your Entire Vault. Nothing Leaves Your Machine."
- Sub: "AI-powered search across your Obsidian vault — or any personal knowledge base. Completely private. Completely local. 15 minutes to set up."
- Problem: "1,000+ notes. Years of curated thinking. Folders, tags, backlinks — you built an intricate system. But when you need a specific answer, you still can't find it without manually searching through everything."
- Features:
  1. 🏠 100% Local — "No cloud. No uploads. No third-party services. Your data never leaves your machine."
  2. 📝 Works with Obsidian — "Native support for .md files, frontmatter, and any folder structure."
  3. 📍 Source Citations — "Every answer points to the specific notes and passages it drew from."
- Steps:
  1. Install Syft Space — "One command. Runs entirely on your machine."
  2. Connect Your Vault — "Point it at your Obsidian vault or any folder of documents."
  3. Start Querying — "Ask questions in natural language. Get answers grounded in your notes."
- CTA: "Query Your Vault Privately"

### H5 — Agent Permissioning
- Badge: "AGENT SECURITY"
- Headline: "Share Your AI Agent. Control Everything."
- Sub: "Generate shareable access links with query-only, rate-limited, time-boxed permissions. See who queries what. Revoke instantly."
- Problem: "You built a powerful AI agent. Your client wants access. But handing over an API key means handing over everything — every data source, every tool, every capability. There's no middle ground between 'full access' and 'no access.'"
- Features:
  1. 🔑 Scoped Access Links — "Query-only, time-boxed, rate-limited. Each link is its own permission boundary."
  2. 📊 Real-Time Dashboard — "See every query, every user, every timestamp. Know exactly how your agent is being used."
  3. 🚫 Instant Revocation — "One click to cut access. No waiting, no ambiguity."
- Steps:
  1. Connect Your Agent — "Link your MCP agent, API, or custom tool to SyftHub."
  2. Generate Access Links — "Set permissions: who can query, what they can access, for how long."
  3. Monitor & Control — "Watch usage in real-time. Revoke access the moment you need to."
- CTA: "Secure Your First Agent"

### H7 — Consultants
- Badge: "FOR DATA CONSULTANTS"
- Headline: "Give Clients Query Access. Keep Every Byte."
- Sub: "Deploy a private endpoint on NDA-protected client data. They ask questions, get answers. Raw data never moves."
- Problem: "Every engagement, same friction: the NDA says data can't move. The client needs answers yesterday. So you become the human API — running queries manually, delivering insights by email, scheduling calls to walk through results."
- Features:
  1. 🛡️ NDA-Compliant by Architecture — "Data stays where it is. Not a policy — a technical guarantee."
  2. 🔗 Client-Facing Query Link — "Send your client a link. They ask questions. No technical setup required."
  3. 📋 Full Audit Trail — "Every query logged. Demonstrate compliance to any stakeholder."
- Steps:
  1. Connect Client Data — "Point Syft Space at the client's dataset. Nothing gets copied."
  2. Set Permissions — "Define what can be queried, by whom, and for how long."
  3. Share the Link — "Send your client a query link. They self-serve. You stop being the bottleneck."
- CTA: "Deploy Your First Private Endpoint"

### H8 — Niche Publishers
- Badge: "FOR WRITERS & RESEARCHERS"
- Headline: "Your Writing Has Value. Now It Can Earn."
- Sub: "Publish your body of work as a queryable endpoint. Set your price. Get attribution-based revenue. Keep full control."
- Problem: "AI companies train on your work without permission. You get nothing — not credit, not compensation, not even a notification. Your 10 years of published thinking is being consumed for free."
- Features:
  1. 🧠 Queryable Brain Endpoint — "Your entire corpus, live and searchable. Readers and AI agents query your actual published thinking."
  2. 💰 You Set the Price — "Per-query pricing or bundled access. Your content, your terms."
  3. 📎 Full Attribution — "Every response cites your original work. Your name stays on your ideas."
- Steps:
  1. Upload Your Corpus — "PDFs, blog posts, papers — anything you've published."
  2. Set Your Price — "Choose per-query pricing or offer bundled access packages."
  3. Start Earning — "Get paid every time someone queries your expertise. Full attribution included."
- CTA: "Publish Your Brain Endpoint"
