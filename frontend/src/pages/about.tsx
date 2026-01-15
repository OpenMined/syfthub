import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';

/**
 * About page - Information about SyftHub and how it works.
 */
export default function AboutPage() {
  return (
    <div className="min-h-screen bg-syft-background">
      {/* Sticky Header */}
      <div className="sticky top-0 z-30 flex w-full items-center border-b border-syft-border bg-syft-background/95 px-6 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <h2 className="font-rubik text-xl font-medium text-syft-primary">About</h2>
          <div className="font-mono text-xs text-syft-muted hidden sm:block opacity-60">
            ~/about
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-12 md:py-16">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-16"
        >
          <h1 className="font-rubik text-3xl md:text-4xl font-medium text-syft-primary mb-12">
            The directory for <span className="bg-gradient-to-r from-syft-secondary via-syft-purple to-syft-green bg-clip-text text-transparent">collective intelligence</span>
          </h1>
          
          <div className="max-w-2xl space-y-12">
            {/* Why */}
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="font-mono text-xs text-syft-secondary bg-syft-surface px-2 py-1 border border-syft-border">
                  [0x01]
                </div>
                <h2 className="font-mono text-lg font-medium text-syft-primary">Why</h2>
              </div>
              <div className="space-y-3 text-base leading-relaxed text-syft-muted border-l-2 border-syft-border pl-4 ml-8">
                <p className="font-rubik">
                  Every major leap in AI has been fueled by more data. But today's leading models train on a few hundred terabytes, while the world has digitized over 180 zettabytes.
                </p>
                <p className="font-rubik text-syft-secondary font-medium">
                  &gt; That's a million times more data sitting unused.
                </p>
                <p className="font-rubik">
                  The problem isn't scarcity. It's access.
                </p>
                <p className="font-rubik">
                  Hospitals, publishers, research institutions, governments: they have the data AI needs, but no sane incentive to share it. The moment data is copied into a training run, the owner loses control.
                </p>
                <p className="font-rubik text-syft-secondary">
                  This is the architectural flaw at the center of modern AI.
                </p>
              </div>
            </div>

            {/* ASCII art decoration */}
            <div className="flex justify-center">
              <div className="font-mono text-xs text-syft-muted border border-syft-border bg-syft-surface px-4 py-3 rounded-lg">
                <pre className="text-center leading-tight">{`╔═══════════════════════════════════════╗
║  DECENTRALIZED • SOVEREIGN • OPEN     ║
╚═══════════════════════════════════════╝`}</pre>
              </div>
            </div>

            {/* What */}
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="font-mono text-xs text-syft-purple bg-syft-surface px-2 py-1 border border-syft-border">
                  [0x02]
                </div>
                <h2 className="font-mono text-lg font-medium text-syft-primary">What</h2>
              </div>
              <div className="space-y-3 text-base leading-relaxed text-syft-muted border-l-2 border-syft-border pl-4 ml-8">
                <p className="font-rubik font-medium text-syft-primary">
                  SyftHub is built on a different premise: data doesn't need to move to be useful, and it doesn't need an intermediary to broker access.
                </p>
                <p className="font-rubik">
                  Syft Spaces are decentralized nodes operated by anyone with knowledge to share: a publisher, a research lab, a journalist, an institution, or just an individual.
                </p>
                <p className="font-rubik">
                  Each Space holds data locally and makes it queryable on terms the operator defines: attribution, control, traceability, payments, or extra layers of security and privacy-preserving tools if sensitive.
                </p>
                <p className="font-rubik text-syft-secondary">
                  SyftHub is the registry: a map of who has knowledge, what they're willing to share, and how to reach them.
                </p>
              </div>
            </div>

            {/* How */}
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="font-mono text-xs text-syft-green bg-syft-surface px-2 py-1 border border-syft-border">
                  [0x03]
                </div>
                <h2 className="font-mono text-lg font-medium text-syft-primary">How: Attribution-Based Control</h2>
              </div>
              <div className="space-y-6 text-base leading-relaxed border-l-2 border-syft-border pl-4 ml-8">
                <div>
                  <h3 className="font-rubik text-base font-medium text-syft-secondary mb-3">&gt; Two-sided agency</h3>
                  <p className="font-rubik text-syft-muted text-base">
                    Users decide which sources inform them, data owners which predictions they support. Today's AI systems make these choices for you: what data trained them, whose knowledge shapes your answers, what gets surfaced and what gets buried. Syft doesn't. When both sides have agency, data can flow in abundance.
                  </p>
                </div>
                
                <div>
                  <h3 className="font-rubik text-base font-medium text-syft-secondary mb-3">&gt; Knowledge should flow without being extracted</h3>
                  <p className="font-rubik text-syft-muted text-base">
                    Today's AI is built on copying. Data gets scraped, blended into weights, and owners lose control the moment it's taken. There's a better way: knowledge stays at the source, AI queries it in place.
                  </p>
                </div>
                
                <div>
                  <h3 className="font-rubik text-base font-medium text-syft-secondary mb-3">&gt; Attribution should be structural, not cosmetic</h3>
                  <p className="font-rubik text-syft-muted text-base">
                    A citation after the fact is decoration. Real attribution means provenance is embedded in the architecture, not appended by policy.
                  </p>
                </div>
                
                <div>
                  <h3 className="font-rubik text-base font-medium text-syft-secondary mb-3">&gt; Control should be continuous, not one-time</h3>
                  <p className="font-rubik text-syft-muted text-base">
                    Consent isn't a checkbox. Data owners can set terms, adjust them, revoke access, price different uses, at any point, for any query.
                  </p>
                </div>
                
                <div>
                  <h3 className="font-rubik text-base font-medium text-syft-secondary mb-3">&gt; The network should resist concentration</h3>
                  <p className="font-rubik text-syft-muted text-base">
                    Intelligence gets better as more Spaces join. But the architecture matters. We're building on open protocols so that no single entity-including us-controls the whole. The infrastructure belongs to everyone who participates.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Roadmap Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="bg-white rounded-xl p-8 md:p-12 border border-syft-border shadow-sm"
        >
          <div className="flex items-center gap-3 mb-8">
            <h2 className="font-rubik text-3xl font-medium text-syft-primary">Roadmap</h2>
          </div>

          <div className="space-y-12 relative before:absolute before:left-[19px] before:top-4 before:bottom-4 before:w-[2px] before:bg-syft-border">
            
            {/* Upcoming / Current */}
            <div className="relative pl-12">
              <div className="absolute left-0 top-1 w-10 h-10 bg-white border-4 border-syft-green rounded-full flex items-center justify-center z-10">
                <div className="w-2 h-2 bg-syft-green rounded-full"></div>
              </div>
              <h3 className="font-rubik text-xl font-medium text-syft-primary mb-4">In Progress & Upcoming</h3>
              <ul className="space-y-3">
                {[
                  "Self-forming collectives + Syft Collectives",
                  "Full launch Payments",
                  "CLI Client (Syft Space equivalent)",
                  "Extended analytics in Syft Space",
                  "Connecting local models in Syft Space"
                ].map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-syft-muted font-rubik">
                    <div className="w-1.5 h-1.5 rounded-full bg-syft-green mt-2.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Q2 */}
            <div className="relative pl-12">
              <div className="absolute left-0 top-1 w-10 h-10 bg-white border-4 border-syft-purple rounded-full flex items-center justify-center z-10">
                <div className="w-2 h-2 bg-syft-purple rounded-full"></div>
              </div>
              <h3 className="font-rubik text-xl font-medium text-syft-primary mb-4">Targeting Q2</h3>
              <ul className="space-y-3">
                {[
                  "Manual approval policy",
                  "Collectively shared policies",
                  "Output privacy policies",
                  "Syft for Research (using non-public data sources beyond querying)",
                  "SyftBox & Syft Client integration"
                ].map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-syft-muted font-rubik">
                    <div className="w-1.5 h-1.5 rounded-full bg-syft-purple mt-2.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="mt-12 pt-8 border-t border-syft-border text-center">
             <p className="font-rubik text-syft-muted mb-6">The future of collective intelligence is built by its users.</p>
             <button className="font-rubik rounded-xl bg-syft-primary hover:bg-syft-secondary text-syft-background px-8 h-12 text-base shadow-sm hover:shadow-md transition-all">
               Shape the Roadmap
               <ArrowRight size={16} className="ml-2 inline" />
             </button>
          </div>
        </motion.div>

        {/* FAQ Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mt-16 mb-24"
        >
          <h2 className="font-rubik text-3xl font-medium text-syft-primary mb-8">FAQ</h2>
          
          <div className="space-y-4">
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                What's the difference between SyftHub and the Syft protocol?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  The Syft protocol is the underlying infrastructure-how Syft Spaces communicate, how queries are routed, how attribution flows. SyftHub is a directory built on top of that protocol. It helps you find and understand Spaces. You don't need SyftHub to use Syft, but it makes discovery easier.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                Who can run a Syft Space?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  Anyone. A newspaper, a research lab, a hospital, an individual with a dataset. If you have knowledge you want to make queryable-on your terms-you can run a Space. The protocol is open.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                How is this different from DRM?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <div className="space-y-3">
                  <p className="font-rubik text-syft-muted leading-relaxed">
                    DRM tries to stop copying. ABC doesn't need to-because data never leaves your Space in the first place.
                  </p>
                  <p className="font-rubik text-syft-muted leading-relaxed">
                    DRM is static: you set it once and hope it holds. ABC is live: you can change terms, revoke access, price different uses differently, all in real time.
                  </p>
                  <p className="font-rubik text-syft-muted leading-relaxed">
                    DRM is adversarial-it treats users as threats. ABC is generative-it assumes you want your knowledge to be useful, you just want to control how and to whom. In short: DRM tries to stop the flow of information. ABC makes the flow accountable.
                  </p>
                </div>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                How does attribution actually work?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  When you query the network, your request is routed to specific Syft Spaces. Each Space that contributes to the answer is tracked. The response comes back with provenance attached-not as metadata you have to trust, but as a structural property of how the system works.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                Can Spaces charge for access?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  Yes. Each Space sets its own terms. Some may be free for research and paid for commercial use. Some may be open to everyone. Some may require approval. The protocol supports all of these models.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                What stops someone from just copying the answers?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <div className="space-y-3">
                  <p className="font-rubik text-syft-muted leading-relaxed">
                    If someone queries a Space and gets an answer, they have that answer-just like if you ask an expert a question, you have their response. What they don't have is the underlying dataset, the ability to re-query at will, or the context that makes future queries valuable. The knowledge stays at the source.
                  </p>
                  <p className="font-rubik text-syft-muted leading-relaxed">
                    For cases where even the response itself is sensitive, we're launching secure enclave aggregation in Q2-end-to-end encryption so that answers from multiple sources can be combined without anyone in the middle seeing the contents.
                  </p>
                </div>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                Is this only for text? What about images, code, structured data?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  The architecture is modality-agnostic. If it can be embedded and queried, it can live in a Space. However, the protocol does not support handling other formats today. Whilst it is on our roadmap, please get involved in the community and tell us if we should do it faster.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                Who builds this?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  SyftHub and the Syft protocol are built by OpenMined, a non-profit focused on privacy-preserving AI and equitable access to information. The code is open source. The protocol is open. We're building infrastructure, not a platform we control.
                </p>
              </div>
            </details>
            
            <details className="border border-syft-border rounded-lg">
              <summary className="cursor-pointer px-6 py-4 font-rubik text-lg text-syft-primary hover:bg-syft-surface transition-colors">
                How do I set up a Syft Space?
              </summary>
              <div className="px-6 py-4 border-t border-syft-border">
                <p className="font-rubik text-syft-muted leading-relaxed">
                  Check the protocol documentation for technical details, or reach out if you're an organization exploring deployment.
                </p>
              </div>
            </details>
          </div>
        </motion.div>

        {/* Read More Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mb-24"
        >
          <h2 className="font-rubik text-2xl font-medium text-syft-primary mb-6">Read More</h2>
          
          <div className="space-y-4">
            <a
              href="https://openmined.org/attribution-based-control/"
              target="_blank"
              rel="noopener noreferrer"
              className="block p-4 border border-syft-border rounded-lg hover:bg-syft-surface transition-colors"
            >
              <div className="font-rubik text-lg text-syft-primary hover:underline">
                Attribution-Based Control Framework
              </div>
              <div className="font-rubik text-base text-syft-muted mt-1">
                openmined.org
              </div>
            </a>
            
            <a
              href="https://ifp.org/unlocking-a-million-times-more-data-for-ai/"
              target="_blank"
              rel="noopener noreferrer"
              className="block p-4 border border-syft-border rounded-lg hover:bg-syft-surface transition-colors"
            >
              <div className="font-rubik text-lg text-syft-primary hover:underline">
                Unlocking a Million Times More Data for AI
              </div>
              <div className="font-rubik text-base text-syft-muted mt-1">
                ifp.org
              </div>
            </a>
            
            <a
              href="https://www.noemamag.com/the-progress-paradox/"
              target="_blank"
              rel="noopener noreferrer"
              className="block p-4 border border-syft-border rounded-lg hover:bg-syft-surface transition-colors"
            >
              <div className="font-rubik text-lg text-syft-primary hover:underline">
                The Progress Paradox
              </div>
              <div className="font-rubik text-base text-syft-muted mt-1">
                noemamag.com
              </div>
            </a>
          </div>
        </motion.div>

      </div>
    </div>
  );
}