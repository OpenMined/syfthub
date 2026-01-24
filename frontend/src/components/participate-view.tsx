import React from 'react';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Download from 'lucide-react/dist/esm/icons/download';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Share2 from 'lucide-react/dist/esm/icons/share-2';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { Button } from './ui/button';

interface ParticipateViewProperties {
  /** Custom title for the header (defaults to "Participate in the Network") */
  title?: string;
  /** Optional callback to go back */
  onBack?: () => void;
}

export function ParticipateView({
  title = 'Participate in the Network',
  onBack
}: Readonly<ParticipateViewProperties>) {
  return (
    <div className='bg-syft-background min-h-screen'>
      {/* Sticky Header */}
      <div className='border-syft-border bg-syft-background/95 sticky top-0 z-30 flex w-full items-center justify-between border-b px-6 py-4 backdrop-blur-sm'>
        <div className='flex items-center gap-4'>
          {onBack ? (
            <Button variant='ghost' size='sm' onClick={onBack} className='p-2' aria-label='Go back'>
              <ArrowLeft className='h-5 w-5' aria-hidden='true' />
            </Button>
          ) : null}
          <h2 className='font-rubik text-syft-primary text-xl font-medium'>{title}</h2>
          <div className='text-syft-muted hidden font-mono text-xs opacity-60 sm:block'>
            ~/participate
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className='w-full min-w-0 flex-1'>
        <div className='mx-auto max-w-5xl space-y-8 px-6 py-8'>
          {/* Intro Text */}
          <div>
            <p className='font-inter text-muted-foreground max-w-2xl text-lg leading-relaxed'>
              Publish data sources, models, and collectives to the Federated AI Network while
              maintaining full control and privacy.
            </p>
          </div>

          {/* How it works cards */}
          <section>
            <h2 className='font-rubik text-foreground mb-6 text-lg font-medium'>How it works</h2>
            <div className='grid gap-6 md:grid-cols-3'>
              <div className='border-border bg-card hover:border-input rounded-xl border p-6 shadow-sm transition-colors'>
                <div className='bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-lg'>
                  <Database className='text-secondary h-6 w-6' />
                </div>
                <h3 className='font-inter text-foreground mb-2 font-medium'>Publish Assets</h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Connect your data sources or models. You define the access policies, privacy
                  budget, and metadata.
                </p>
              </div>

              <div className='border-border bg-card hover:border-input rounded-xl border p-6 shadow-sm transition-colors'>
                <div className='bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-lg'>
                  <Shield className='h-6 w-6 text-[#53bea9]' />
                </div>
                <h3 className='font-inter text-foreground mb-2 font-medium'>Stay in Control</h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Your data never leaves your server. Users submit queries which are executed
                  locally within your privacy constraints.
                </p>
              </div>

              <div className='border-border bg-card hover:border-input rounded-xl border p-6 shadow-sm transition-colors'>
                <div className='bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-lg'>
                  <Globe className='h-6 w-6 text-[#937098]' />
                </div>
                <h3 className='font-inter text-foreground mb-2 font-medium'>Join the Network</h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Your endpoints become discoverable on SyftHub, allowing researchers and developers
                  to attribute and query them.
                </p>
              </div>
            </div>
          </section>

          {/* Install Syft Space */}
          <section className='bg-primary text-primary-foreground relative overflow-hidden rounded-2xl p-8 shadow-lg'>
            <div className='relative z-10 flex flex-col items-start justify-between gap-8 md:flex-row md:items-center'>
              <div className='max-w-lg'>
                <h2 className='font-rubik mb-3 text-2xl font-medium'>Install Syft Space</h2>
                <p className='font-inter text-primary-foreground/80 mb-6 text-sm leading-relaxed'>
                  Syft Space is your local control center for the Federated AI Network. Bring your
                  data or models, manage permissions, and publish your sources securely in a few
                  minutes
                </p>

                <div className='flex flex-wrap gap-4'>
                  <button
                    type='button'
                    className='font-inter bg-card text-foreground hover:bg-accent flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors'
                  >
                    <Download className='h-4 w-4' aria-hidden='true' />
                    Download for macOS
                  </button>
                  <button
                    type='button'
                    className='font-inter flex items-center gap-2 rounded-lg border border-[#4a465d] bg-[#353243] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#4a465d]'
                  >
                    Download for Windows
                  </button>
                </div>
                <p className='font-inter text-primary-foreground/60 mt-4 text-xs'>
                  v0.8.2 • Requires Docker Desktop
                </p>
              </div>

              {/* Abstract visual */}
              <div className='relative hidden md:block'>
                <div className='flex h-48 w-64 flex-col gap-3 rounded-lg border border-[#4a465d] bg-[#353243] p-4 shadow-xl'>
                  <div className='flex items-center gap-2 border-b border-[#4a465d] pb-3'>
                    <div className='h-3 w-3 rounded-full bg-[#ff5f57]' />
                    <div className='h-3 w-3 rounded-full bg-[#febc2e]' />
                    <div className='h-3 w-3 rounded-full bg-[#28c840]' />
                  </div>
                  <div className='space-y-2'>
                    <div className='h-2 w-3/4 rounded bg-[#4a465d]' />
                    <div className='h-2 w-1/2 rounded bg-[#4a465d]' />
                    <div className='h-2 w-5/6 rounded bg-[#4a465d]' />
                  </div>
                  <div className='mt-auto flex justify-end'>
                    <div className='font-inter text-foreground rounded bg-[#53bea9] px-3 py-1 text-xs font-medium'>
                      Active Node
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Developers */}
          <section className='border-border border-t pt-12 pb-12'>
            <div className='flex flex-col items-start justify-between gap-8 md:flex-row'>
              <div>
                <h2 className='font-rubik text-foreground mb-2 text-lg font-medium'>
                  For Developers
                </h2>
                <p className='font-inter text-muted-foreground mb-4 max-w-md text-sm'>
                  Integrate SyftHub endpoints into your applications using our SDKs or the Model
                  Context Protocol (MCP).
                </p>
                <a
                  href='#'
                  className='font-inter text-secondary inline-flex items-center gap-1 text-sm font-medium hover:underline'
                >
                  Read the documentation
                  <svg
                    width='16'
                    height='16'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    strokeWidth='2'
                    strokeLinecap='round'
                    strokeLinejoin='round'
                  >
                    <path d='M5 12h14M12 5l7 7-7 7' />
                  </svg>
                </a>
              </div>

              <div className='flex gap-4'>
                <a
                  href='https://pypi.org/project/syfthub-sdk/'
                  target='_blank'
                  rel='noopener noreferrer'
                  className='border-border bg-card hover:border-input w-40 rounded-xl border p-4 transition-colors'
                >
                  <Cpu className='text-foreground mb-3 h-6 w-6' />
                  <div className='font-inter text-foreground font-medium'>Python SDK</div>
                  <div className='font-inter text-muted-foreground mt-1 text-xs'>
                    pip install syfthub-sdk
                  </div>
                </a>
                <a
                  href='https://www.npmjs.com/package/@syfthub/sdk'
                  target='_blank'
                  rel='noopener noreferrer'
                  className='border-border bg-card hover:border-input w-40 rounded-xl border p-4 transition-colors'
                >
                  <Share2 className='text-foreground mb-3 h-6 w-6' />
                  <div className='font-inter text-foreground font-medium'>TypeScript SDK</div>
                  <div className='font-inter text-muted-foreground mt-1 text-xs'>
                    npm i @syfthub/sdk
                  </div>
                </a>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
