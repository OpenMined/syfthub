/**
 * ToolDispatcher — routes a ToolView to its renderer. Each kind has a
 * dedicated component; the `generic` branch falls back to the existing
 * prompt-kit Tool component (the collapsible JSON dump) so any tool not in
 * KNOWN_TOOL_KINDS — and not carrying a producer display hint — keeps
 * working untouched.
 */

import { Tool, type ToolPart } from '@/components/prompt-kit/tool';
import { CodeToolView } from '@/components/chat/tool-views/CodeToolView';
import { DiffToolView } from '@/components/chat/tool-views/DiffToolView';
import { TerminalToolView } from '@/components/chat/tool-views/TerminalToolView';
import { WebToolView } from '@/components/chat/tool-views/WebToolView';
import type { ToolView } from '@/lib/tool-display';

export function ToolDispatcher({ view }: { view: ToolView }) {
  switch (view.kind) {
    case 'terminal':
      return <TerminalToolView view={view} />;
    case 'code':
      return <CodeToolView view={view} />;
    case 'diff':
      return <DiffToolView view={view} />;
    case 'web':
      return <WebToolView view={view} />;
    case 'generic':
    default:
      return <Tool toolPart={toGenericToolPart(view)} className='mt-0' />;
  }
}

/** Adapt any ToolView back to the legacy ToolPart shape that prompt-kit's
 *  collapsible Tool component already understands. Kept side-by-side with the
 *  modern renderers so a single switch covers both. */
function toGenericToolPart(view: ToolView): ToolPart {
  const state: ToolPart['state'] = view.status === 'running'
    ? 'input-streaming'
    : view.status === 'error'
      ? 'output-error'
      : 'output-available';

  // For non-generic kinds that fall through here (code, diff, web pre-Phase-2),
  // surface as much of the structured viewmodel as the generic renderer can
  // hold. The generic renderer formats arbitrary k/v pairs.
  const { input, output } = projectToInputOutput(view);
  return {
    type: view.toolName,
    state,
    input,
    output,
    toolCallId: view.toolCallId,
    errorText: view.errorText,
  };
}

function projectToInputOutput(view: ToolView): {
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
} {
  switch (view.kind) {
    case 'generic':
      return {
        input: view.input,
        output: typeof view.output === 'object' && view.output !== null
          ? (view.output as Record<string, unknown>)
          : view.output != null ? { result: view.output } : undefined,
      };
    case 'code':
      return {
        input: { path: view.path, operation: view.operation },
        output: view.content ? { content: view.content } : undefined,
      };
    case 'diff':
      return {
        input: { path: view.path },
        output: { before: view.before, after: view.after },
      };
    case 'web':
      return {
        input: { url: view.url },
        output: view.summary ? { summary: view.summary } : undefined,
      };
    default:
      return {};
  }
}
