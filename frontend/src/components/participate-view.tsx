import React from 'react';

import { Cpu, Database, Download, Globe, Share2, Shield } from 'lucide-react';

interface ParticipateViewProperties {
  onAuthRequired?: () => void;
}

export function ParticipateView({
  onAuthRequired: _onAuthRequired
}: Readonly<ParticipateViewProperties>) {
  return (
    <div className='mx-auto flex min-h-screen max-w-[1600px] flex-col'>
      {/* Sticky Header */}
      <div className='sticky top-0 z-30 w-full border-b border-[#ecebef] bg-[#fcfcfd]/95 px-6 py-4 backdrop-blur-sm'>
        <h2 className='font-rubik text-xl font-medium text-[#272532]'>
          Participate in the Network
        </h2>
      </div>

      {/* Main Content */}
      <main className='w-full min-w-0 flex-1'>
        <div className='mx-auto max-w-4xl space-y-12 px-6 py-8'>
          {/* Intro Text */}
          <div>
            <p className='font-inter max-w-2xl text-lg leading-relaxed text-[#5e5a72]'>
              Publish data sources, models, and collectives to the Federated AI Network while
              maintaining full control and privacy.
            </p>
          </div>

          {/* How it works cards */}
          <section>
            <h2 className='font-rubik mb-6 text-lg font-medium text-[#272532]'>How it works</h2>
            <div className='grid gap-6 md:grid-cols-3'>
              <div className='rounded-xl border border-[#ecebef] bg-white p-6 shadow-sm transition-colors hover:border-[#b4b0bf]'>
                <div className='mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-[#f1f0f4]'>
                  <Database className='h-6 w-6 text-[#6976ae]' />
                </div>
                <h3 className='font-inter mb-2 font-medium text-[#272532]'>Publish Assets</h3>
                <p className='font-inter text-sm leading-relaxed text-[#5e5a72]'>
                  Connect your data sources or models. You define the access policies, privacy
                  budget, and metadata.
                </p>
              </div>

              <div className='rounded-xl border border-[#ecebef] bg-white p-6 shadow-sm transition-colors hover:border-[#b4b0bf]'>
                <div className='mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-[#f1f0f4]'>
                  <Shield className='h-6 w-6 text-[#53bea9]' />
                </div>
                <h3 className='font-inter mb-2 font-medium text-[#272532]'>Stay in Control</h3>
                <p className='font-inter text-sm leading-relaxed text-[#5e5a72]'>
                  Your data never leaves your server. Users submit queries which are executed
                  locally within your privacy constraints.
                </p>
              </div>

              <div className='rounded-xl border border-[#ecebef] bg-white p-6 shadow-sm transition-colors hover:border-[#b4b0bf]'>
                <div className='mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-[#f1f0f4]'>
                  <Globe className='h-6 w-6 text-[#937098]' />
                </div>
                <h3 className='font-inter mb-2 font-medium text-[#272532]'>Join the Network</h3>
                <p className='font-inter text-sm leading-relaxed text-[#5e5a72]'>
                  Your endpoints become discoverable on SyftHub, allowing researchers and developers
                  to attribute and query them.
                </p>
              </div>
            </div>
          </section>

          {/* Install Syft Space */}
          <section className='relative overflow-hidden rounded-2xl bg-[#272532] p-8 text-white shadow-lg'>
            <div className='relative z-10 flex flex-col items-start justify-between gap-8 md:flex-row md:items-center'>
              <div className='max-w-lg'>
                <h2 className='font-rubik mb-3 text-2xl font-medium'>Install Syft Space</h2>
                <p className='font-inter mb-6 text-sm leading-relaxed text-gray-300'>
                  Syft Space is your local control center for the Federated AI Network. Bring your
                  data or models, manage permissions, and publish your sources securely in a few
                  minutes
                </p>

                <div className='flex flex-wrap gap-4'>
                  <button className='font-inter flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-[#272532] transition-colors hover:bg-gray-100'>
                    <Download className='h-4 w-4' />
                    Download for macOS
                  </button>
                  <button className='font-inter flex items-center gap-2 rounded-lg border border-[#4a465d] bg-[#353243] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#4a465d]'>
                    Download for Windows
                  </button>
                </div>
                <p className='font-inter mt-4 text-xs text-gray-400'>
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
                    <div className='font-inter rounded bg-[#53bea9] px-3 py-1 text-xs font-medium text-[#272532]'>
                      Active Node
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Developers */}
          <section className='border-t border-[#ecebef] pt-12 pb-12'>
            <div className='flex flex-col items-start justify-between gap-8 md:flex-row'>
              <div>
                <h2 className='font-rubik mb-2 text-lg font-medium text-[#272532]'>
                  For Developers
                </h2>
                <p className='font-inter mb-4 max-w-md text-sm text-[#5e5a72]'>
                  Integrate SyftHub endpoints into your applications using our SDKs or the Model
                  Context Protocol (MCP).
                </p>
                <a
                  href='#'
                  className='font-inter inline-flex items-center gap-1 text-sm font-medium text-[#6976ae] hover:underline'
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
                <div className='w-40 rounded-xl border border-[#ecebef] bg-white p-4 transition-colors hover:border-[#b4b0bf]'>
                  <Cpu className='mb-3 h-6 w-6 text-[#272532]' />
                  <div className='font-inter font-medium text-[#272532]'>Python SDK</div>
                  <div className='font-inter mt-1 text-xs text-[#5e5a72]'>pip install syft</div>
                </div>
                <div className='w-40 rounded-xl border border-[#ecebef] bg-white p-4 transition-colors hover:border-[#b4b0bf]'>
                  <Share2 className='mb-3 h-6 w-6 text-[#272532]' />
                  <div className='font-inter font-medium text-[#272532]'>MCP Server</div>
                  <div className='font-inter mt-1 text-xs text-[#5e5a72]'>npx syft-mcp</div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
