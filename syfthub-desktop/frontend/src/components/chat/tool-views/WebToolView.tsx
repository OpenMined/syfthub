/**
 * WebToolView — renders a URL fetch as a header chip + a scrollable
 * text-summary body. Hand-rolled rather than pulling in the heavier
 * link-preview component (which expects Open Graph metadata we don't have
 * from a generic fetch_url call).
 */

import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import type { ToolView } from '@/lib/tool-display';

type WebView = Extract<ToolView, { kind: 'web' }>;

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function formatDuration(ms?: number): string | null {
  if (ms == null) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function WebToolView({ view }: { view: WebView }) {
  const isRunning = view.status === 'running';
  const isError = view.status === 'error';
  const duration = formatDuration(view.durationMs);
  const host = view.url ? safeHostname(view.url) : '';

  return (
    <div className='border-border bg-card overflow-hidden rounded-lg border'>
      <div className='bg-card flex items-center justify-between border-b px-3 py-2'>
        <div className='flex items-center gap-2 overflow-hidden'>
          <Globe className='text-muted-foreground h-4 w-4 shrink-0' aria-hidden='true' />
          <span className='text-foreground truncate font-mono text-xs' title={view.url}>
            {host || view.url || '(no url)'}
          </span>
        </div>
        <div className='flex items-center gap-3'>
          {duration && (
            <span className='text-muted-foreground font-mono text-xs tabular-nums'>
              {duration}
            </span>
          )}
          {view.url && (
            <a
              href={view.url}
              target='_blank'
              rel='noopener noreferrer'
              className='text-muted-foreground hover:text-foreground'
              aria-label='Open in browser'
            >
              <ExternalLink className='h-4 w-4' aria-hidden='true' />
            </a>
          )}
        </div>
      </div>
      <div className='p-3'>
        {isError ? (
          <div className='border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-2 text-sm'>
            {view.errorText || 'Fetch failed'}
          </div>
        ) : view.summary ? (
          <div className='text-foreground max-h-60 overflow-auto whitespace-pre-wrap break-words font-mono text-xs'>
            {view.summary}
          </div>
        ) : (
          <div className='text-muted-foreground flex items-center gap-1.5 text-xs italic'>
            {isRunning && <Loader2 className='h-3 w-3 animate-spin' aria-hidden='true' />}
            <span>{isRunning ? 'Fetching…' : 'No content'}</span>
          </div>
        )}
      </div>
    </div>
  );
}
