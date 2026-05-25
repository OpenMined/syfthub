/**
 * DiffToolView — renders a string-replace style edit (Claude Code's Edit tool
 * or any equivalent) as a minimal unified diff. Hand-rolled rather than
 * depending on @pierre/diffs / React 19's use() hook — we just need clear
 * before/after rendering, not a full diff engine.
 *
 * Wire mapping:
 *   args.old_string → view.before  (rendered with `-` prefix, red background)
 *   args.new_string → view.after   (rendered with `+` prefix, green background)
 *   args.file_path  → view.path    (header)
 */

import GitCompare from 'lucide-react/dist/esm/icons/git-compare';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import type { ToolView } from '@/lib/tool-display';
import { cn } from '@/lib/utils';

type DiffView = Extract<ToolView, { kind: 'diff' }>;

function splitLines(s: string): string[] {
  if (!s) return [];
  // Normalize CRLF (Windows) and stray CR (old Mac) so each line is clean,
  // then strip trailing newlines to avoid rendering a phantom empty line.
  const trimmed = s.replace(/\r\n/g, '\n').replace(/\r/g, '').replace(/\n+$/, '');
  return trimmed.split('\n');
}

function DiffLine({ marker, text }: { marker: '-' | '+' | ' '; text: string }) {
  const bg = marker === '-'
    ? 'bg-red-500/10 text-red-700 dark:text-red-300'
    : marker === '+'
      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
      : '';
  return (
    <div className={cn('flex font-mono text-xs leading-5', bg)}>
      <span className='text-muted-foreground select-none px-2 tabular-nums'>{marker}</span>
      <span className='whitespace-pre-wrap break-words pr-2'>{text || ' '}</span>
    </div>
  );
}

export function DiffToolView({ view }: { view: DiffView }) {
  const isRunning = view.status === 'running';
  const isError = view.status === 'error';
  const beforeLines = splitLines(view.before);
  const afterLines = splitLines(view.after);
  const hasContent = beforeLines.length > 0 || afterLines.length > 0;

  return (
    <div className='border-border bg-card overflow-hidden rounded-lg border'>
      <div className='bg-card flex items-center justify-between border-b px-3 py-2'>
        <div className='flex items-center gap-2 overflow-hidden'>
          <GitCompare className='text-muted-foreground h-4 w-4 shrink-0' aria-hidden='true' />
          <span className='text-foreground truncate font-mono text-xs'>
            edit {view.path || '(unknown path)'}
          </span>
        </div>
        {isRunning && (
          <span className='text-muted-foreground flex items-center gap-1 text-xs'>
            <Loader2 className='h-3 w-3 animate-spin' aria-hidden='true' />
            Running…
          </span>
        )}
      </div>
      {isError ? (
        <div className='border-destructive/30 bg-destructive/10 text-destructive m-2 rounded-md border p-2 text-sm'>
          {view.errorText || 'Edit failed'}
        </div>
      ) : hasContent ? (
        <div className='max-h-80 overflow-auto py-1'>
          {beforeLines.map((line, i) => (
            <DiffLine key={`b-${i}`} marker='-' text={line} />
          ))}
          {afterLines.map((line, i) => (
            <DiffLine key={`a-${i}`} marker='+' text={line} />
          ))}
        </div>
      ) : (
        <div className='text-muted-foreground px-3 py-2 text-xs italic'>
          {isRunning ? 'Editing…' : 'No changes'}
        </div>
      )}
    </div>
  );
}
