/**
 * TerminalToolView — renders a tool_call/tool_result pair as a shell-style
 * surface. Backs onto the tool-ui `Terminal` display component installed via
 * the shadcn registry. Used for run_command / Bash / Grep / Glob today.
 *
 * The viewmodel feeds three salient fields to the component:
 *   - command  →  shown in the header bar
 *   - stdout   →  body, success path
 *   - stderr   →  body, error path
 *   - exitCode →  0 or 1 (we don't carry the real exit yet; status drives it)
 */

import { Terminal } from '@/components/tool-ui/terminal';
import type { ToolView } from '@/lib/tool-display';

import { RunningSpinner } from './RunningSpinner';

type TerminalView = Extract<ToolView, { kind: 'terminal' }>;

export function TerminalToolView({ view }: { view: TerminalView }) {
  const stableId = view.toolCallId ?? `terminal-${view.toolName}`;
  const isRunning = view.status === 'running';

  return (
    <div className='space-y-1'>
      <Terminal
        id={stableId}
        command={view.command}
        stdout={view.stdout || undefined}
        stderr={view.stderr || undefined}
        exitCode={view.exitCode}
        durationMs={view.durationMs}
        cwd={view.cwd}
        maxCollapsedLines={20}
        defaultExpanded={false}
      />
      {isRunning && <RunningSpinner />}
    </div>
  );
}
