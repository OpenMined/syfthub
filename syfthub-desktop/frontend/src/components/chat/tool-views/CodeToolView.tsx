/**
 * CodeToolView — renders a file read/write tool call as a syntax-highlighted
 * block. Backs onto the tool-ui CodeBlock display component.
 *
 * Read:  args.path → header,    result body → content.
 * Write: args.path → header,    args.content → content (the body the agent
 *        wanted to write; we show that instead of the success message).
 */

import FileText from 'lucide-react/dist/esm/icons/file-text';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Pencil from 'lucide-react/dist/esm/icons/pencil';

import { CodeBlock } from '@/components/tool-ui/code-block';
import type { ToolView } from '@/lib/tool-display';

type CodeView = Extract<ToolView, { kind: 'code' }>;

export function CodeToolView({ view }: { view: CodeView }) {
  const stableId = view.toolCallId ?? `code-${view.toolName}`;
  const isRunning = view.status === 'running';
  const isError = view.status === 'error';
  const Icon = view.operation === 'write' ? Pencil : FileText;

  return (
    <div className='space-y-1'>
      <div className='text-muted-foreground flex items-center gap-1.5 px-1 text-xs'>
        <Icon className='h-3 w-3' aria-hidden='true' />
        <span className='font-mono'>
          {view.operation === 'write' ? 'write ' : 'read '}
          {view.path || '(unknown path)'}
        </span>
      </div>
      {isError ? (
        <div className='border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-2 text-sm'>
          {view.errorText || 'Tool error'}
        </div>
      ) : view.content ? (
        <CodeBlock
          id={stableId}
          code={view.content}
          language={view.language ?? 'text'}
          filename={view.path || undefined}
          lineNumbers='visible'
          maxCollapsedLines={20}
        />
      ) : (
        <div className='text-muted-foreground bg-muted/40 rounded-md border px-2 py-1 text-xs italic'>
          {isRunning ? 'Reading…' : 'No content'}
        </div>
      )}
      {isRunning && (
        <div className='text-muted-foreground flex items-center gap-1.5 px-1 text-xs'>
          <Loader2 className='h-3 w-3 animate-spin' aria-hidden='true' />
          <span>Running…</span>
        </div>
      )}
    </div>
  );
}
