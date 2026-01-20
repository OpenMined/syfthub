import { motion } from 'framer-motion';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';

import { PageHeader } from '@/components/ui/page-header';

/**
 * About page - Information about SyftHub and how it works.
 */
export default function AboutPage() {
  return (
    <div className='bg-syft-background min-h-screen'>
      <PageHeader title='About' path='~/about' />

      <div className='mx-auto max-w-3xl px-6 py-12 md:py-16'>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className='mb-16'
        >
          <h1 className='font-rubik text-syft-primary mb-12 text-3xl font-medium md:text-4xl'>
            The directory for{' '}
            <span className='from-syft-secondary via-syft-purple to-syft-green bg-gradient-to-r bg-clip-text text-transparent'>
              collective intelligence
            </span>
          </h1>

          <div className='max-w-2xl space-y-12'>
            {/* Why */}
            <div>
              <div className='mb-4 flex items-center gap-3'>
                <div className='text-syft-secondary bg-syft-surface border-syft-border border px-2 py-1 font-mono text-xs'>
                  [0x01]
                </div>
                <h2 className='text-syft-primary font-mono text-lg font-medium'>Why</h2>
              </div>
              <div className='text-syft-muted border-syft-border ml-8 space-y-3 border-l-2 pl-4 text-base leading-relaxed'>
                <p className='font-rubik'>
                  Every major leap in AI has been fueled by more data. But today's leading models
                  train on a few hundred terabytes, while the world has digitized over 180
                  zettabytes.
                </p>
                <p className='font-rubik text-syft-secondary font-medium'>
                  &gt; That's a million times more data sitting unused.
                </p>
                <p className='font-rubik'>The problem isn't scarcity. It's access.</p>
                <p className='font-rubik'>
                  Hospitals, publishers, research institutions, governments: they have the data AI
                  needs, but no sane incentive to share it. The moment data is copied into a
                  training run, the owner loses control.
                </p>
                <p className='font-rubik text-syft-secondary'>
                  This is the architectural flaw at the center of modern AI.
                </p>
              </div>
            </div>

            {/* ASCII art decoration */}
            <div className='flex justify-center'>
              <div className='text-syft-muted border-syft-border bg-syft-surface rounded-lg border px-4 py-3 font-mono text-xs'>
                <pre className='text-center leading-tight'>{`╔═══════════════════════════════════════╗
║  DECENTRALIZED • SOVEREIGN • OPEN     ║
╚═══════════════════════════════════════╝`}</pre>
              </div>
            </div>

            {/* What */}
            <div>
              <div className='mb-4 flex items-center gap-3'>
                <div className='text-syft-purple bg-syft-surface border-syft-border border px-2 py-1 font-mono text-xs'>
                  [0x02]
                </div>
                <h2 className='text-syft-primary font-mono text-lg font-medium'>What</h2>
              </div>
              <div className='text-syft-muted border-syft-border ml-8 space-y-3 border-l-2 pl-4 text-base leading-relaxed'>
                <p className='font-rubik text-syft-primary font-medium'>
                  SyftHub is built on a different premise: data doesn't need to move to be useful,
                  and it doesn't need an intermediary to broker access.
                </p>
                <p className='font-rubik'>
                  Syft Spaces are decentralized nodes operated by anyone with knowledge to share: a
                  publisher, a research lab, a journalist, an institution, or just an individual.
                </p>
                <p className='font-rubik'>
                  Each Space holds data locally and makes it queryable on terms the operator
                  defines: attribution, control, traceability, payments, or extra layers of security
                  and privacy-preserving tools if sensitive.
                </p>
                <p className='font-rubik text-syft-secondary'>
                  SyftHub is the registry: a map of who has knowledge, what they're willing to
                  share, and how to reach them.
                </p>
              </div>
            </div>

            {/* How */}
            <div>
              <div className='mb-4 flex items-center gap-3'>
                <div className='text-syft-green bg-syft-surface border-syft-border border px-2 py-1 font-mono text-xs'>
                  [0x03]
                </div>
                <h2 className='text-syft-primary font-mono text-lg font-medium'>
                  How: Attribution-Based Control
                </h2>
              </div>
              <div className='border-syft-border ml-8 space-y-6 border-l-2 pl-4 text-base leading-relaxed'>
                <div>
                  <h3 className='font-rubik text-syft-secondary mb-3 text-base font-medium'>
                    &gt; Two-sided agency
                  </h3>
                  <p className='font-rubik text-syft-muted text-base'>
                    Users decide which sources inform them, data owners which predictions they
                    support. Today's AI systems make these choices for you: what data trained them,
                    whose knowledge shapes your answers, what gets surfaced and what gets buried.
                    Syft doesn't. When both sides have agency, data can flow in abundance.
                  </p>
                </div>

                <div>
                  <h3 className='font-rubik text-syft-secondary mb-3 text-base font-medium'>
                    &gt; Knowledge should flow without being extracted
                  </h3>
                  <p className='font-rubik text-syft-muted text-base'>
                    Today's AI is built on copying. Data gets scraped, blended into weights, and
                    owners lose control the moment it's taken. There's a better way: knowledge stays
                    at the source, AI queries it in place.
                  </p>
                </div>

                <div>
                  <h3 className='font-rubik text-syft-secondary mb-3 text-base font-medium'>
                    &gt; Attribution should be structural, not cosmetic
                  </h3>
                  <p className='font-rubik text-syft-muted text-base'>
                    A citation after the fact is decoration. Real attribution means provenance is
                    embedded in the architecture, not appended by policy.
                  </p>
                </div>

                <div>
                  <h3 className='font-rubik text-syft-secondary mb-3 text-base font-medium'>
                    &gt; Control should be continuous, not one-time
                  </h3>
                  <p className='font-rubik text-syft-muted text-base'>
                    Consent isn't a checkbox. Data owners can set terms, adjust them, revoke access,
                    price different uses, at any point, for any query.
                  </p>
                </div>

                <div>
                  <h3 className='font-rubik text-syft-secondary mb-3 text-base font-medium'>
                    &gt; The network should resist concentration
                  </h3>
                  <p className='font-rubik text-syft-muted text-base'>
                    Intelligence gets better as more Spaces join. But the architecture matters.
                    We're building on open protocols so that no single entity-including us-controls
                    the whole. The infrastructure belongs to everyone who participates.
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
          className='border-syft-border rounded-xl border bg-white p-8 shadow-sm md:p-12'
        >
          <div className='mb-8 flex items-center gap-3'>
            <h2 className='font-rubik text-syft-primary text-3xl font-medium'>Roadmap</h2>
          </div>

          <div className='before:bg-syft-border relative space-y-12 before:absolute before:top-4 before:bottom-4 before:left-[19px] before:w-[2px]'>
            {/* Upcoming / Current */}
            <div className='relative pl-12'>
              <div className='border-syft-green absolute top-1 left-0 z-10 flex h-10 w-10 items-center justify-center rounded-full border-4 bg-white'>
                <div className='bg-syft-green h-2 w-2 rounded-full'></div>
              </div>
              <h3 className='font-rubik text-syft-primary mb-4 text-xl font-medium'>
                In Progress & Upcoming
              </h3>
              <ul className='space-y-3'>
                {[
                  'Self-forming collectives + Syft Collectives',
                  'Full launch Payments',
                  'CLI Client (Syft Space equivalent)',
                  'Extended analytics in Syft Space',
                  'Connecting local models in Syft Space'
                ].map((item, index) => (
                  <li key={index} className='text-syft-muted font-rubik flex items-start gap-3'>
                    <div className='bg-syft-green mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full' />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Q2 */}
            <div className='relative pl-12'>
              <div className='border-syft-purple absolute top-1 left-0 z-10 flex h-10 w-10 items-center justify-center rounded-full border-4 bg-white'>
                <div className='bg-syft-purple h-2 w-2 rounded-full'></div>
              </div>
              <h3 className='font-rubik text-syft-primary mb-4 text-xl font-medium'>
                Targeting Q2
              </h3>
              <ul className='space-y-3'>
                {[
                  'Manual approval policy',
                  'Collectively shared policies',
                  'Output privacy policies',
                  'Syft for Research (using non-public data sources beyond querying)',
                  'SyftBox & Syft Client integration'
                ].map((item, index) => (
                  <li key={index} className='text-syft-muted font-rubik flex items-start gap-3'>
                    <div className='bg-syft-purple mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full' />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className='border-syft-border mt-12 border-t pt-8 text-center'>
            <p className='font-rubik text-syft-muted mb-6'>
              The future of collective intelligence is built by its users.
            </p>
            <button className='font-rubik bg-syft-primary hover:bg-syft-secondary text-syft-background h-12 rounded-xl px-8 text-base shadow-sm transition-all hover:shadow-md'>
              Shape the Roadmap
              <ArrowRight size={16} className='ml-2 inline' />
            </button>
          </div>
        </motion.div>

        {/* FAQ Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className='mt-16 mb-24'
        >
          <h2 className='font-rubik text-syft-primary mb-8 text-3xl font-medium'>FAQ</h2>

          <div className='space-y-4'>
            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                What's the difference between SyftHub and the Syft protocol?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  The Syft protocol is the underlying infrastructure-how Syft Spaces communicate,
                  how queries are routed, how attribution flows. SyftHub is a directory built on top
                  of that protocol. It helps you find and understand Spaces. You don't need SyftHub
                  to use Syft, but it makes discovery easier.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                Who can run a Syft Space?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  Anyone. A newspaper, a research lab, a hospital, an individual with a dataset. If
                  you have knowledge you want to make queryable-on your terms-you can run a Space.
                  The protocol is open.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                How is this different from DRM?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <div className='space-y-3'>
                  <p className='font-rubik text-syft-muted leading-relaxed'>
                    DRM tries to stop copying. ABC doesn't need to-because data never leaves your
                    Space in the first place.
                  </p>
                  <p className='font-rubik text-syft-muted leading-relaxed'>
                    DRM is static: you set it once and hope it holds. ABC is live: you can change
                    terms, revoke access, price different uses differently, all in real time.
                  </p>
                  <p className='font-rubik text-syft-muted leading-relaxed'>
                    DRM is adversarial-it treats users as threats. ABC is generative-it assumes you
                    want your knowledge to be useful, you just want to control how and to whom. In
                    short: DRM tries to stop the flow of information. ABC makes the flow
                    accountable.
                  </p>
                </div>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                How does attribution actually work?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  When you query the network, your request is routed to specific Syft Spaces. Each
                  Space that contributes to the answer is tracked. The response comes back with
                  provenance attached-not as metadata you have to trust, but as a structural
                  property of how the system works.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                Can Spaces charge for access?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  Yes. Each Space sets its own terms. Some may be free for research and paid for
                  commercial use. Some may be open to everyone. Some may require approval. The
                  protocol supports all of these models.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                What stops someone from just copying the answers?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <div className='space-y-3'>
                  <p className='font-rubik text-syft-muted leading-relaxed'>
                    If someone queries a Space and gets an answer, they have that answer-just like
                    if you ask an expert a question, you have their response. What they don't have
                    is the underlying dataset, the ability to re-query at will, or the context that
                    makes future queries valuable. The knowledge stays at the source.
                  </p>
                  <p className='font-rubik text-syft-muted leading-relaxed'>
                    For cases where even the response itself is sensitive, we're launching secure
                    enclave aggregation in Q2-end-to-end encryption so that answers from multiple
                    sources can be combined without anyone in the middle seeing the contents.
                  </p>
                </div>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                Is this only for text? What about images, code, structured data?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  The architecture is modality-agnostic. If it can be embedded and queried, it can
                  live in a Space. However, the protocol does not support handling other formats
                  today. Whilst it is on our roadmap, please get involved in the community and tell
                  us if we should do it faster.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                Who builds this?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  SyftHub and the Syft protocol are built by OpenMined, a non-profit focused on
                  privacy-preserving AI and equitable access to information. The code is open
                  source. The protocol is open. We're building infrastructure, not a platform we
                  control.
                </p>
              </div>
            </details>

            <details className='border-syft-border rounded-lg border'>
              <summary className='font-rubik text-syft-primary hover:bg-syft-surface cursor-pointer px-6 py-4 text-lg transition-colors'>
                How do I set up a Syft Space?
              </summary>
              <div className='border-syft-border border-t px-6 py-4'>
                <p className='font-rubik text-syft-muted leading-relaxed'>
                  Check the protocol documentation for technical details, or reach out if you're an
                  organization exploring deployment.
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
          className='mb-24'
        >
          <h2 className='font-rubik text-syft-primary mb-6 text-2xl font-medium'>Read More</h2>

          <div className='space-y-4'>
            <a
              href='https://openmined.org/attribution-based-control/'
              target='_blank'
              rel='noopener noreferrer'
              className='border-syft-border hover:bg-syft-surface block rounded-lg border p-4 transition-colors'
            >
              <div className='font-rubik text-syft-primary text-lg hover:underline'>
                Attribution-Based Control Framework
              </div>
              <div className='font-rubik text-syft-muted mt-1 text-base'>openmined.org</div>
            </a>

            <a
              href='https://ifp.org/unlocking-a-million-times-more-data-for-ai/'
              target='_blank'
              rel='noopener noreferrer'
              className='border-syft-border hover:bg-syft-surface block rounded-lg border p-4 transition-colors'
            >
              <div className='font-rubik text-syft-primary text-lg hover:underline'>
                Unlocking a Million Times More Data for AI
              </div>
              <div className='font-rubik text-syft-muted mt-1 text-base'>ifp.org</div>
            </a>

            <a
              href='https://www.noemamag.com/the-progress-paradox/'
              target='_blank'
              rel='noopener noreferrer'
              className='border-syft-border hover:bg-syft-surface block rounded-lg border p-4 transition-colors'
            >
              <div className='font-rubik text-syft-primary text-lg hover:underline'>
                The Progress Paradox
              </div>
              <div className='font-rubik text-syft-muted mt-1 text-base'>noemamag.com</div>
            </a>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
