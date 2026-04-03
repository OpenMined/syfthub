import React, { useMemo } from 'react';

import { useQuery } from '@tanstack/react-query';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Database from 'lucide-react/dist/esm/icons/database';
import Download from 'lucide-react/dist/esm/icons/download';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { Button } from './ui/button';

interface ParticipateViewProperties {
  /** Custom title for the header (defaults to "Start your first node") */
  title?: string;
  /** Optional callback to go back */
  onBack?: () => void;
}

// ─── GitHub release types ────────────────────────────────────────────────────

interface GitHubAsset {
  name: string;
  browser_download_url: string;
}

interface GitHubRelease {
  tag_name: string;
  assets: GitHubAsset[];
}

// ─── OS detection ────────────────────────────────────────────────────────────

type DetectedOS = 'macos' | 'windows' | 'linux' | 'unknown';

function detectOS(): DetectedOS {
  if (typeof navigator === 'undefined') return 'unknown';
  const ua = navigator.userAgent;
  // Exclude iOS/iPadOS — they have "Mac OS X" in UA but can't run the desktop app
  if (/iPad|iPhone|iPod/.test(ua)) return 'unknown';
  if (ua.includes('Mac OS X') || ua.includes('Macintosh')) return 'macos';
  if (ua.includes('Windows NT')) return 'windows';
  if (ua.includes('Linux') && !ua.includes('Android')) return 'linux';
  return 'unknown';
}

// ─── Asset selection ─────────────────────────────────────────────────────────

interface DownloadOption {
  url: string;
  label: string;
  /** true → solid card button; false → ghost/outlined button */
  primary: boolean;
}

function selectDownloads(assets: GitHubAsset[], os: DetectedOS): DownloadOption[] {
  const nonSig = assets.filter((a) => !a.name.endsWith('.sig'));

  if (os === 'macos') {
    const universal = nonSig.find((a) => a.name.endsWith('.dmg') && a.name.includes('universal'));
    if (universal) {
      return [{ url: universal.browser_download_url, label: 'Download for macOS', primary: true }];
    }
    const arm = nonSig.find(
      (a) => a.name.endsWith('.dmg') && (a.name.includes('aarch64') || a.name.includes('arm64'))
    );
    const intel = nonSig.find(
      (a) => a.name.endsWith('.dmg') && (a.name.includes('x64') || a.name.includes('x86_64'))
    );
    const opts: DownloadOption[] = [];
    if (arm) opts.push({ url: arm.browser_download_url, label: 'Apple Silicon', primary: true });
    if (intel)
      opts.push({
        url: intel.browser_download_url,
        label: 'Intel Mac',
        primary: opts.length === 0
      });
    return opts;
  }

  if (os === 'windows') {
    const exe = nonSig.find((a) => a.name.endsWith('.exe'));
    const msi = nonSig.find((a) => a.name.endsWith('.msi'));
    const opts: DownloadOption[] = [];
    if (exe)
      opts.push({ url: exe.browser_download_url, label: 'Download for Windows', primary: true });
    if (msi)
      opts.push({ url: msi.browser_download_url, label: '.msi', primary: opts.length === 0 });
    return opts;
  }

  if (os === 'linux') {
    const deb = nonSig.find((a) => a.name.endsWith('.deb'));
    const rpm = nonSig.find((a) => a.name.endsWith('.rpm'));
    const opts: DownloadOption[] = [];
    if (deb)
      opts.push({ url: deb.browser_download_url, label: '.deb (Debian / Ubuntu)', primary: true });
    if (rpm)
      opts.push({ url: rpm.browser_download_url, label: '.rpm (Fedora / RHEL)', primary: !deb });
    return opts;
  }

  return [];
}

// ─── GitHub API fetch ─────────────────────────────────────────────────────────

const RELEASES_PAGE = 'https://github.com/OpenMined/syft-space/releases';

async function fetchLatestRelease(): Promise<GitHubRelease> {
  const res = await fetch('https://api.github.com/repos/OpenMined/syft-space/releases/latest', {
    headers: { Accept: 'application/vnd.github+json' }
  });
  if (!res.ok) throw new Error(`GitHub API ${res.status}`);
  return res.json() as Promise<GitHubRelease>;
}

// ─── Download section ─────────────────────────────────────────────────────────

function DownloadSection() {
  const os = useMemo(() => detectOS(), []);

  const { data: release, isLoading } = useQuery({
    queryKey: ['syft-space-release'],
    queryFn: fetchLatestRelease,
    staleTime: 1000 * 60 * 60, // 1 hour — releases don't change often
    retry: 1
  });

  const downloads = release ? selectDownloads(release.assets, os) : [];
  const version = release?.tag_name;

  const primaryBtnClass =
    'font-inter bg-card text-foreground hover:bg-accent flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors';
  const ghostBtnClass =
    'font-inter border border-primary-foreground/30 text-primary-foreground/80 hover:border-primary-foreground/60 hover:text-primary-foreground flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm transition-colors';

  return (
    <div>
      <div className='flex flex-wrap items-center gap-3'>
        {isLoading ? (
          // Skeleton state — same size as the real button to avoid layout shift
          <div className={`${primaryBtnClass} pointer-events-none opacity-50`}>
            <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
            Checking for latest release…
          </div>
        ) : downloads.length === 0 ? (
          // Fallback: unknown OS or fetch error → link to releases page
          <a
            href={RELEASES_PAGE}
            target='_blank'
            rel='noopener noreferrer'
            className={primaryBtnClass}
          >
            <ExternalLink className='h-4 w-4' aria-hidden='true' />
            View all releases
          </a>
        ) : (
          <>
            {downloads.map((dl) => (
              <a
                key={dl.url}
                href={dl.url}
                target='_blank'
                rel='noopener noreferrer'
                className={dl.primary ? primaryBtnClass : ghostBtnClass}
              >
                <Download className='h-4 w-4' aria-hidden='true' />
                {dl.label}
              </a>
            ))}

            {/* Always offer an escape hatch to the full releases page */}
            <a
              href={RELEASES_PAGE}
              target='_blank'
              rel='noopener noreferrer'
              className='font-inter text-primary-foreground/50 hover:text-primary-foreground/80 flex items-center gap-1 self-center text-xs transition-colors'
              aria-label='All releases on GitHub'
            >
              <ExternalLink className='h-3 w-3' aria-hidden='true' />
              All releases
            </a>
          </>
        )}
      </div>

      <p className='font-inter text-primary-foreground/60 mt-4 text-xs'>
        {version ? `${version} • ` : ''}Requires Docker Desktop
      </p>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ParticipateView({
  title = 'Start your first node',
  onBack
}: Readonly<ParticipateViewProperties>) {
  return (
    <div className='bg-background min-h-screen'>
      {/* Sticky Header */}
      <div className='border-border bg-background/95 sticky top-0 z-30 flex w-full items-center justify-between border-b px-6 py-4 backdrop-blur-sm'>
        <div className='flex items-center gap-4'>
          {onBack ? (
            <Button variant='ghost' size='sm' onClick={onBack} className='p-2' aria-label='Go back'>
              <ArrowLeft className='h-5 w-5' aria-hidden='true' />
            </Button>
          ) : null}
          <h2 className='font-rubik text-foreground text-xl font-medium'>{title}</h2>
          <div className='text-muted-foreground hidden font-mono text-xs opacity-60 sm:block'>
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
              Bring your local capabilities — context, knowledge, models, and soon more — into a
              shared directory for collective intelligence, while keeping full ownership and
              privacy.
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
                <h3 className='font-inter text-foreground mb-2 font-medium'>
                  Bring Your Capabilities
                </h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Connect local knowledge or models. You define the access policies, privacy budget,
                  and metadata.
                </p>
              </div>

              <div className='border-border bg-card hover:border-input rounded-xl border p-6 shadow-sm transition-colors'>
                <div className='bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-lg'>
                  <Shield className='h-6 w-6 text-[#53bea9]' />
                </div>
                <h3 className='font-inter text-foreground mb-2 font-medium'>Stay in Control</h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Your data never leaves your machine. Queries are executed locally within your
                  privacy constraints.
                </p>
              </div>

              <div className='border-border bg-card hover:border-input rounded-xl border p-6 shadow-sm transition-colors'>
                <div className='bg-accent mb-4 flex h-12 w-12 items-center justify-center rounded-lg'>
                  <Globe className='h-6 w-6 text-[#937098]' />
                </div>
                <h3 className='font-inter text-foreground mb-2 font-medium'>Join the Directory</h3>
                <p className='font-inter text-muted-foreground text-sm leading-relaxed'>
                  Your node becomes discoverable on SyftHub, letting others query and attribute your
                  contributions to collective intelligence.
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
                  Syft Space is your local control center for contributing to the directory. Bring
                  your knowledge or models, manage permissions, and go live in a few minutes.
                </p>

                <DownloadSection />
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
        </div>
      </main>
    </div>
  );
}
