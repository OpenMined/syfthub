import { motion } from 'framer-motion';
import { Shield, Lock, Globe, Map, ArrowRight, CheckCircle2, Clock, Terminal } from 'lucide-react';

/**
 * About page - Information about SyftHub and how it works.
 */
export default function AboutPage() {
  return (
    <div className="min-h-screen bg-syft-background font-mono">
      {/* Sticky Header */}
      <div className="sticky top-0 z-30 flex w-full items-center border-b border-syft-border bg-syft-background/95 px-6 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <h2 className="font-rubik text-xl font-medium text-syft-primary">About</h2>
          <div className="font-mono text-xs text-syft-muted hidden sm:block opacity-60">
            ~/about
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-12 md:py-16">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-16"
        >
          <h1 className="font-rubik text-4xl md:text-5xl font-bold text-syft-primary mb-6">
            Building the <span className="bg-gradient-to-r from-syft-secondary via-syft-purple to-syft-green bg-clip-text text-transparent">Internet of Value</span> for Data
          </h1>
          <p className="font-inter text-xl text-syft-muted max-w-2xl">
            We are redesigning how the world accesses information—moving from a model of copying data to a model of accessing insights.
          </p>
          
          {/* ASCII art style decoration */}
          <div className="mt-8 font-mono text-syft-muted text-xs">
            <pre>{`
    ╔═══════════════════════════════════════╗
    ║  DECENTRALIZED • SOVEREIGN • OPEN     ║
    ╚═══════════════════════════════════════╝
            `}</pre>
          </div>
        </motion.div>

        <div className="space-y-16 mb-24">
          <motion.section 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex flex-col md:flex-row gap-8 items-start border border-syft-border bg-white p-8 rounded-none shadow-[4px_4px_0px_0px_rgba(39,37,50,1)]"
          >
            <div className="flex-shrink-0 p-3 bg-syft-surface rounded-none border border-syft-border text-syft-secondary">
              <Globe size={32} />
            </div>
            <div>
              <h2 className="font-rubik text-2xl font-bold text-syft-primary mb-4">[0x01] The Data Dilemma</h2>
              <p className="font-inter text-lg text-syft-muted leading-relaxed">
                For decades, the internet has thrived on the free flow of information, but this model fails when it comes to sensitive data. Whether it's medical records, financial transactions, or proprietary research, the most valuable knowledge is locked away in silos to protect privacy and intellectual property. We are faced with a zero-sum choice: share data and lose control, or keep it hidden and limit human progress.
              </p>
            </div>
          </motion.section>

          <motion.section 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="flex flex-col md:flex-row gap-8 items-start border border-syft-border bg-white p-8 rounded-none shadow-[4px_4px_0px_0px_rgba(147,112,152,1)]"
          >
            <div className="flex-shrink-0 p-3 bg-syft-surface rounded-none border border-syft-border text-syft-purple">
              <Lock size={32} />
            </div>
            <div>
              <h2 className="font-rubik text-2xl font-bold text-syft-primary mb-4">[0x02] Remote Execution, Not Data Transfer</h2>
              <p className="font-inter text-lg text-syft-muted leading-relaxed">
                SyftHub fundamentally changes this equation through an open standard for <span className="font-mono bg-syft-surface px-1 py-0.5 border border-syft-border">Remote Procedure Calls (RPC)</span>. Instead of moving data to the algorithm, we send the algorithm to the data. This allows data owners to grant granular permission for specific questions to be answered without ever exposing the raw underlying data. It is a transition from "copying" to "visiting" information.
              </p>
            </div>
          </motion.section>

          <motion.section 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="flex flex-col md:flex-row gap-8 items-start border border-syft-border bg-white p-8 rounded-none shadow-[4px_4px_0px_0px_rgba(100,187,98,1)]"
          >
            <div className="flex-shrink-0 p-3 bg-syft-surface rounded-none border border-syft-border text-syft-green">
              <Shield size={32} />
            </div>
            <div>
              <h2 className="font-rubik text-2xl font-bold text-syft-primary mb-4">[0x03] A Sovereign Collective</h2>
              <p className="font-inter text-lg text-syft-muted leading-relaxed">
                We envision a future where every institution, researcher, and individual holds the keys to their own digital sovereignty. By federating access through a decentralized protocol, we are building a global collective intelligence that is robust, private, and open. No single entity controls the network; instead, it is governed by trust, cryptographic verification, and the community of nodes that power it.
              </p>
            </div>
          </motion.section>
        </div>

        {/* Roadmap Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="bg-white rounded-xl p-8 md:p-12 border border-syft-border shadow-sm"
        >
          <div className="flex items-center gap-3 mb-8">
            <div className="p-3 bg-syft-surface rounded-xl border border-syft-border text-syft-secondary">
               <Map size={24} />
            </div>
            <h2 className="font-rubik text-3xl font-bold text-syft-primary">Roadmap</h2>
          </div>

          <div className="space-y-12 relative before:absolute before:left-[19px] before:top-4 before:bottom-4 before:w-[2px] before:bg-syft-border">
            
            {/* Upcoming / Current */}
            <div className="relative pl-12">
              <div className="absolute left-0 top-1 w-10 h-10 bg-white border-4 border-syft-green rounded-full flex items-center justify-center z-10">
                <CheckCircle2 size={16} className="text-syft-green" />
              </div>
              <h3 className="font-rubik text-xl font-bold text-syft-primary mb-4">In Progress & Upcoming</h3>
              <ul className="space-y-3">
                {[
                  "Self-forming collectives + Syft Collectives",
                  "Full launch Payments",
                  "CLI Client (Syft Space equivalent)",
                  "Extended analytics in Syft Space",
                  "Provisioning of local models in Syft Space"
                ].map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-syft-muted font-inter">
                    <div className="w-1.5 h-1.5 rounded-full bg-syft-green mt-2.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Q2 */}
            <div className="relative pl-12">
              <div className="absolute left-0 top-1 w-10 h-10 bg-white border-4 border-syft-purple rounded-full flex items-center justify-center z-10">
                <Clock size={16} className="text-syft-purple" />
              </div>
              <h3 className="font-rubik text-xl font-bold text-syft-primary mb-4">Targeting Q2</h3>
              <ul className="space-y-3">
                {[
                  "Manual approval policy",
                  "Collectively shared policies",
                  "Output privacy policies",
                  "Syft for Research (using non-public data sources beyond querying)",
                  "SyftBox & Syft Client integration"
                ].map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-syft-muted font-inter">
                    <div className="w-1.5 h-1.5 rounded-full bg-syft-purple mt-2.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="mt-12 pt-8 border-t border-syft-border text-center">
             <p className="font-inter text-syft-muted mb-6">The future of collective intelligence is built by its users.</p>
             <button className="font-inter rounded-xl bg-syft-primary hover:bg-syft-secondary text-syft-background px-8 h-12 text-base shadow-sm hover:shadow-md transition-all">
               Shape the Roadmap
               <ArrowRight size={16} className="ml-2 inline" />
             </button>
          </div>
        </motion.div>

      </div>
    </div>
  );
}