import { Terminal } from "@/components/mockups/terminal";
import { TerminalAnimated } from "@/components/mockups/terminal-animated";
import { AnimatedSection } from "@/components/animations/animated-section";
import { StaggeredList } from "@/components/animations/staggered-list";
import { Footer } from "@/components/landing/footer";
import { SyftHubLogo } from "@/components/brand/syfthub-logo";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SyftHub — Connect AI Agents to Private Data via MCP",
  description:
    "Add Syft as an MCP server. Your agents query live data through access-controlled endpoints. Set up in 10 minutes.",
};

/* ─── Navbar ─── */
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-lg">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <SyftHubLogo size="md" />
        <a
          href="#get-started"
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-gray-800 hover:shadow-md"
        >
          Get Started
        </a>
      </div>
    </nav>
  );
}

/* ─── Hero ─── */
function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-53px)] items-center overflow-hidden">
      {/* Subtle radial glow */}
      <div className="pointer-events-none absolute right-0 top-0 h-[600px] w-[600px] -translate-y-1/4 translate-x-1/4 rounded-full bg-indigo-100/40 blur-3xl animate-glow-drift" />

      <div className="relative mx-auto grid w-full max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
        {/* Left — copy */}
        <div>
          <span className="opacity-0 animate-fade-in-up inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-pulse-soft" />
            For MCP Developers
          </span>
          <h1 className="opacity-0 animate-fade-in-up animation-delay-100 mt-7 text-[2.75rem] font-extrabold leading-[1.08] tracking-[-0.03em] text-gray-900 sm:text-5xl lg:text-[3.5rem]">
            Connect AI&nbsp;agents
            <br />
            to private data.
          </h1>
          <p className="opacity-0 animate-fade-in-up animation-delay-200 mt-5 max-w-md text-[17px] leading-relaxed text-gray-500">
            Zero copying. Zero ingestion. Add a Syft MCP server and query
            live data through access-controlled endpoints.
          </p>
          <a
            href="#get-started"
            className="group opacity-0 animate-fade-in-up animation-delay-300 mt-8 inline-flex items-center gap-2 rounded-xl bg-gray-900 px-6 py-3.5 font-mono text-[15px] text-white shadow-[0_1px_2px_rgba(0,0,0,0.05),0_4px_12px_rgba(0,0,0,0.15)] transition-all hover:bg-gray-800 hover:shadow-[0_1px_2px_rgba(0,0,0,0.05),0_8px_20px_rgba(0,0,0,0.2)]"
          >
            npx syft-mcp init
            <span className="text-gray-500 transition-transform group-hover:translate-x-1">&rarr;</span>
          </a>
        </div>

        {/* Right — terminal with glow */}
        <div className="relative">
          <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-indigo-200/20 blur-2xl" />
          <div className="relative">
            <TerminalAnimated
              title="~"
              startDelay={400}
              lines={[
                { prompt: true, text: "npx syft-mcp init" },
                { text: '<span class="text-green-400">&#10003;</span> Connected to SyftHub' },
                { text: '<span class="text-green-400">&#10003;</span> Found 3 data sources' },
                { text: '<span class="text-green-400">&#10003;</span> MCP server running on port 3001' },
                { text: "" },
                {
                  text: "Ready. Query from Claude, Cursor, or any MCP client.",
                  dimmed: true,
                },
              ]}
            />
          </div>
        </div>
      </div>
    </section>
  );
}


/* ─── Syntax-highlighted Code Blocks ─── */

function JsonBlock() {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute -inset-2 rounded-3xl bg-indigo-500/5 blur-xl" />
      <div className="relative overflow-hidden rounded-2xl border border-gray-800/80 bg-[#0d1117] shadow-[0_4px_24px_rgba(0,0,0,0.25)]">
        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-gray-800/80 px-4 py-2.5">
          <div className="flex gap-1.5">
            <div className="h-3 w-3 rounded-full bg-[#ff5f57]" />
            <div className="h-3 w-3 rounded-full bg-[#febc2e]" />
            <div className="h-3 w-3 rounded-full bg-[#28c840]" />
          </div>
          <span className="ml-2 font-mono text-[11px] text-gray-500">mcp.json</span>
        </div>
        {/* Code with syntax highlighting */}
        <StaggeredList staggerMs={80} animation="animate-fade-in-up" className="px-5 py-5 font-mono text-[13px] leading-7">
          <div><span className="text-gray-600">{'{'}</span></div>
          <div className="pl-4"><span className="text-indigo-400">&quot;mcpServers&quot;</span><span className="text-gray-500">: </span><span className="text-gray-600">{'{'}</span></div>
          <div className="pl-8"><span className="text-indigo-400">&quot;syft&quot;</span><span className="text-gray-500">: </span><span className="text-gray-600">{'{'}</span></div>
          <div className="pl-12"><span className="text-indigo-400">&quot;command&quot;</span><span className="text-gray-500">: </span><span className="text-green-400">&quot;npx&quot;</span><span className="text-gray-600">,</span></div>
          <div className="pl-12"><span className="text-indigo-400">&quot;args&quot;</span><span className="text-gray-500">: </span><span className="text-gray-600">[</span><span className="text-green-400">&quot;syft-mcp&quot;</span><span className="text-gray-600">, </span><span className="text-green-400">&quot;--source&quot;</span><span className="text-gray-600">, </span><span className="text-green-400">&quot;./data&quot;</span><span className="text-gray-600">]</span></div>
          <div className="pl-8"><span className="text-gray-600">{'}'}</span></div>
          <div className="pl-4"><span className="text-gray-600">{'}'}</span></div>
          <div><span className="text-gray-600">{'}'}</span></div>
        </StaggeredList>
      </div>
    </div>
  );
}

function YamlBlock() {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute -inset-2 rounded-3xl bg-indigo-500/5 blur-xl" />
      <div className="relative overflow-hidden rounded-2xl border border-gray-800/80 bg-[#0d1117] shadow-[0_4px_24px_rgba(0,0,0,0.25)]">
        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-gray-800/80 px-4 py-2.5">
          <div className="flex gap-1.5">
            <div className="h-3 w-3 rounded-full bg-[#ff5f57]" />
            <div className="h-3 w-3 rounded-full bg-[#febc2e]" />
            <div className="h-3 w-3 rounded-full bg-[#28c840]" />
          </div>
          <span className="ml-2 font-mono text-[11px] text-gray-500">permissions.yaml</span>
        </div>
        {/* Code with syntax highlighting */}
        <StaggeredList staggerMs={80} animation="animate-fade-in-up" className="px-5 py-5 font-mono text-[13px] leading-7">
          <div><span className="text-indigo-400">clients</span><span className="text-gray-500">:</span></div>
          <div className="pl-4"><span className="text-gray-500">- </span><span className="text-indigo-400">name</span><span className="text-gray-500">: </span><span className="text-green-400">&quot;cursor-dev&quot;</span></div>
          <div className="pl-8"><span className="text-indigo-400">collections</span><span className="text-gray-500">: </span><span className="text-gray-600">[</span><span className="text-green-400">&quot;docs&quot;</span><span className="text-gray-600">, </span><span className="text-green-400">&quot;api-specs&quot;</span><span className="text-gray-600">]</span></div>
          <div className="pl-8"><span className="text-indigo-400">rate_limit</span><span className="text-gray-500">: </span><span className="text-amber-400">100</span><span className="text-gray-500">/hour</span></div>
          <div className="pl-8"><span className="text-indigo-400">expires</span><span className="text-gray-500">: </span><span className="text-green-400">&quot;2025-12-31&quot;</span></div>
          <div className="h-4" />
          <div className="pl-4"><span className="text-gray-500">- </span><span className="text-indigo-400">name</span><span className="text-gray-500">: </span><span className="text-green-400">&quot;claude-analyst&quot;</span></div>
          <div className="pl-8"><span className="text-indigo-400">collections</span><span className="text-gray-500">: </span><span className="text-gray-600">[</span><span className="text-green-400">&quot;metrics&quot;</span><span className="text-gray-600">]</span></div>
          <div className="pl-8"><span className="text-indigo-400">rate_limit</span><span className="text-gray-500">: </span><span className="text-amber-400">50</span><span className="text-gray-500">/hour</span></div>
          <div className="pl-8"><span className="text-indigo-400">log</span><span className="text-gray-500">: </span><span className="text-purple-400">true</span></div>
        </StaggeredList>
      </div>
    </div>
  );
}

/* ─── Feature Sections ─── */
function FeatureSections() {
  return (
    <div>
      {/* Section A — Query data where it lives */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-20">
          <AnimatedSection>
            <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
              Query data where it lives
            </h2>
            <p className="mt-4 max-w-md text-[15px] leading-relaxed text-gray-500">
              Your agents connect to data sources through Syft&apos;s MCP
              server. No ETL pipelines, no copying data to third parties. The
              data stays in place.
            </p>
            <StaggeredList staggerMs={100} as="ul" className="mt-6 space-y-3">
              {["No data movement — ever", "Real-time query results", "Works with any file format"].map((item) => (
                <li key={item} className="flex items-center gap-2.5 text-[14px] text-gray-600">
                  <svg className="h-4 w-4 shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  {item}
                </li>
              ))}
            </StaggeredList>
          </AnimatedSection>
          <JsonBlock />
        </div>
      </section>

      {/* Section B — Granular access controls */}
      <section className="relative overflow-hidden bg-gray-50">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-200 to-transparent" />
        <div className="mx-auto max-w-6xl px-6 py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-20">
            <YamlBlock />
            <AnimatedSection>
              <h2 className="text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
                Granular access controls
              </h2>
              <p className="mt-4 max-w-md text-[15px] leading-relaxed text-gray-500">
                Scope permissions per client. Rate limits, time-boxing,
                collection-level access. Every query is logged.
              </p>
              <StaggeredList staggerMs={100} as="ul" className="mt-6 space-y-3">
                {["Per-client permission scopes", "Rate limiting & time-boxing", "Complete audit trail"].map((item) => (
                  <li key={item} className="flex items-center gap-2.5 text-[14px] text-gray-600">
                    <svg className="h-4 w-4 shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    {item}
                  </li>
                ))}
              </StaggeredList>
            </AnimatedSection>
          </div>
        </div>
      </section>

    </div>
  );
}

/* ─── Setup Section ─── */
function SetupSection() {
  return (
    <section className="relative overflow-hidden bg-gray-50">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-200 to-transparent" />
      <div className="mx-auto max-w-6xl px-6 py-24">
        <div className="text-center">
          <span className="text-[13px] font-semibold uppercase tracking-widest text-indigo-600">Quick start</span>
          <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.02em] text-gray-900">
            Set up in 3 commands
          </h2>
        </div>
        <div className="relative mx-auto mt-12 max-w-2xl">
          <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-indigo-200/20 blur-2xl" />
          <div className="relative">
            <TerminalAnimated
              title="Terminal"
              lines={[
                {
                  prompt: true,
                  typingText: "npm install -g syft-mcp",
                  text: 'npm install -g syft-mcp &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-gray-600"># Install globally</span>',
                },
                {
                  prompt: true,
                  typingText: "syft-mcp connect ./my-data",
                  text: 'syft-mcp connect ./my-data &nbsp;&nbsp;<span class="text-gray-600"># Connect your data</span>',
                },
                {
                  prompt: true,
                  typingText: "syft-mcp serve",
                  text: 'syft-mcp serve &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-gray-600"># Start the MCP server</span>',
                },
              ]}
            />
          </div>
        </div>
      </div>
    </section>
  );
}


/* ─── Page ─── */
export default function H1McpPage() {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <Navbar />
      <Hero />
      <FeatureSections />
      <SetupSection />
      <Footer dark={false} />
    </div>
  );
}
