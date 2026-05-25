/**
 * Tool display dispatch — maps an agent.tool_call (+ optional agent.tool_result)
 * pair onto a tagged-union viewmodel. The chat surface renders each kind with a
 * dedicated component; `generic` is the catch-all collapsible from prompt-kit.
 *
 * The protocol stays minimal: every kind is derived from the existing
 * { tool_name, arguments, result, status } fields plus an optional producer hint
 * (`agent.tool_call.display`). When the hint is absent, KNOWN_TOOL_KINDS maps
 * well-known names (Claude Code's Bash/Read/Edit/Grep/Glob/WebFetch, basic-agent's
 * run_command/read_file/write_file/fetch_url) onto a kind so third-party agents
 * light up without producer changes.
 */

import type { AgentEntry } from '@/hooks/use-agent-workflow';

// ── Tagged-union viewmodel ───────────────────────────────────────────────────

export type ToolStatus = 'running' | 'success' | 'error';

interface ToolViewBase {
  toolCallId?: string;
  toolName: string;
  status: ToolStatus;
  durationMs?: number;
  errorText?: string;
}

export type ToolView =
  | (ToolViewBase & {
      kind: 'terminal';
      command: string;
      stdout: string;
      stderr: string;
      cwd?: string;
      exitCode: number;
    })
  | (ToolViewBase & {
      kind: 'code';
      // The path/operation the agent acted on (read or wrote).
      path: string;
      operation: 'read' | 'write';
      content: string;
      language?: string;
    })
  | (ToolViewBase & {
      kind: 'diff';
      path: string;
      before: string;
      after: string;
    })
  | (ToolViewBase & {
      kind: 'web';
      url: string;
      summary: string;
    })
  | (ToolViewBase & {
      kind: 'generic';
      input?: Record<string, unknown>;
      output?: unknown;
    });

export type ToolKind = ToolView['kind'];

// ── Known-tool lookup ────────────────────────────────────────────────────────

/** Producer-agnostic name → kind table. The lookup is the fallback path when
 *  the producer did not set agent.tool_call.display. Names listed here are the
 *  exact strings the relevant agents emit. */
const KNOWN_TOOL_KINDS: Record<string, ToolKind> = {
  // basic-agent (~/.config/syfthub/endpoints/basic-agent/runner.py)
  run_command: 'terminal',
  read_file:   'code',
  write_file:  'code',
  fetch_url:   'web',
  // Claude Code (verbatim from claude --output-format stream-json)
  Bash:        'terminal',
  Grep:        'terminal',
  Glob:        'terminal',
  Read:        'code',
  Write:       'code',
  Edit:        'diff',
  WebFetch:    'web',
};

export function resolveToolKind(toolName: string, displayHint?: string): ToolKind {
  if (displayHint && isHintableKind(displayHint)) return displayHint;
  return KNOWN_TOOL_KINDS[toolName] ?? 'generic';
}

/** Hintable kinds = every kind except 'generic'. A producer that emits
 *  display='generic' should not force the JSON-dump fallback when the tool
 *  name is recognised — fall through to the lookup table instead. */
type HintableKind = Exclude<ToolKind, 'generic'>;

function isHintableKind(value: string): value is HintableKind {
  return value === 'terminal' || value === 'code' || value === 'diff' || value === 'web';
}

// ── Pairing ──────────────────────────────────────────────────────────────────

/**
 * Pair each tool_call entry with its matching tool_result. Hybrid pairing:
 *   1. id-based: when both call and result carry a non-empty tool_call_id,
 *      match by id. This handles agents that emit results out of order or
 *      interleaved with new calls (e.g. parallel tool use in a single
 *      assistant turn) — Claude Code's primary mode.
 *   2. oldest-unpaired fallback: when a result has no usable id (or its id
 *      doesn't match any call), bind it to the earliest unpaired call. This
 *      restores the old nearest-following semantics for producers that ship
 *      empty ids, partial streams, or non-claude tools.
 *
 * Returns:
 *   - callToResult: tool_call entry index → tool_result entry index
 *   - consumedResults: tool_result indices that are owned by a call (skip standalone)
 */
export function pairToolEntries(
  entries: AgentEntry[],
): { callToResult: Map<number, number>; consumedResults: Set<number> } {
  const callToResult = new Map<number, number>();
  const consumedResults = new Set<number>();
  const callIdxById = new Map<string, number>();
  const pairedCalls = new Set<number>();
  const callOrder: number[] = [];

  const getId = (e: AgentEntry): string => {
    const data = (e.data ?? {}) as Record<string, unknown>;
    return typeof data.tool_call_id === 'string' ? data.tool_call_id : '';
  };

  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    const id = getId(e);
    if (e.kind === 'tool_call') {
      callOrder.push(i);
      if (id) callIdxById.set(id, i);
      continue;
    }
    if (e.kind !== 'tool_result') continue;
    // 1. id-based match
    let matched: number | undefined;
    if (id) {
      const byId = callIdxById.get(id);
      if (byId !== undefined && !pairedCalls.has(byId)) matched = byId;
    }
    // 2. oldest-unpaired fallback (works for empty-id streams)
    if (matched === undefined) {
      for (const idx of callOrder) {
        if (!pairedCalls.has(idx)) { matched = idx; break; }
      }
    }
    if (matched !== undefined) {
      callToResult.set(matched, i);
      pairedCalls.add(matched);
      consumedResults.add(i);
    }
  }

  return { callToResult, consumedResults };
}

// ── ViewModel construction ───────────────────────────────────────────────────

/**
 * Session lifecycle as the consumer cares about it for tool-view rendering.
 *   - 'running'     → session is still streaming events
 *   - 'completed'   → session.completed arrived; any unpaired call is treated
 *                     as silently successful (the result event was lost or
 *                     batched after the terminal event; marking it as failed
 *                     would lie about the agent's actual outcome)
 *   - 'interrupted' → session.cancelled / session.failed (or the user stopped
 *                     the run); unpaired calls render as 'Tool call interrupted'
 */
export type SessionPhase = 'running' | 'completed' | 'interrupted';

/**
 * Build a ToolView from a paired (call, result) entry. When `resultEntry` is
 * absent, `sessionPhase` decides how to render the call — see SessionPhase.
 */
export function buildToolView(
  callEntry: AgentEntry,
  resultEntry: AgentEntry | undefined,
  sessionPhase: SessionPhase,
): ToolView {
  const call = (callEntry.data ?? {}) as Record<string, unknown>;
  const toolName = String(call.tool_name ?? 'tool');
  const args = (call.arguments ?? {}) as Record<string, unknown>;
  const toolCallId = typeof call.tool_call_id === 'string' ? call.tool_call_id : undefined;
  const displayHint = typeof call.display === 'string' ? call.display : undefined;
  const kind = resolveToolKind(toolName, displayHint);

  // Status truth table:
  //   resultEntry present       →  derive from result.status (defaults success)
  //   no result, phase=running  →  'running'
  //   no result, phase=completed→  'success' (no result event, but the agent
  //                                  ended cleanly — assume the tool finished)
  //   no result, phase=interrupted → 'error' ('Tool call interrupted')
  const status: ToolStatus = resultEntry
    ? (((resultEntry.data ?? {}) as Record<string, unknown>).status === 'error' ? 'error' : 'success')
    : sessionPhase === 'running'
      ? 'running'
      : sessionPhase === 'interrupted'
        ? 'error'
        : 'success';

  const result = resultEntry
    ? ((resultEntry.data ?? {}) as Record<string, unknown>)
    : undefined;
  const resultValue = result?.result;
  const resultText = resultValue == null
    ? ''
    : typeof resultValue === 'string' ? resultValue : safeStringify(resultValue);
  // Use `||` (not `??`) so an empty `error` field or empty result text falls
  // through to the 'Tool error' / 'Tool call interrupted' placeholder.
  const errorText = status === 'error'
    ? (resultEntry
        ? (stringOrEmpty(result?.error) || resultText || 'Tool error')
        : 'Tool call interrupted')
    : undefined;
  const durationMs = typeof result?.duration_ms === 'number' ? result.duration_ms : undefined;

  const base: ToolViewBase = { toolCallId, toolName, status, durationMs, errorText };

  switch (kind) {
    case 'terminal':
      return {
        ...base,
        kind: 'terminal',
        command: deriveTerminalCommand(toolName, args),
        stdout: status === 'error' ? '' : resultText,
        stderr: status === 'error' ? (errorText ?? resultText) : '',
        cwd: stringArg(args, 'cwd'),
        exitCode: status === 'error' ? 1 : 0,
      };

    case 'code': {
      const path = stringArg(args, 'path') || stringArg(args, 'file_path') || '';
      // Detect write semantics by the presence of a `content`/`text` arg
      // rather than a hard-coded tool-name allowlist. Any producer-emitted
      // code-display tool that writes a body will pass that body as an arg.
      const writeBody = stringArg(args, 'content') || stringArg(args, 'text');
      const operation: 'read' | 'write' = writeBody ? 'write' : 'read';
      // For writes, surface the body the agent intended to write;
      // for reads, the file body comes back in the result.
      const content = operation === 'write' ? writeBody : resultText;
      return {
        ...base,
        kind: 'code',
        path,
        operation,
        content,
        language: inferLanguageFromPath(path),
      };
    }

    case 'diff': {
      const path = stringArg(args, 'path') || stringArg(args, 'file_path') || '';
      const before = stringArg(args, 'old_string');
      const after = stringArg(args, 'new_string');
      return { ...base, kind: 'diff', path, before, after };
    }

    case 'web': {
      const url = stringArg(args, 'url');
      return { ...base, kind: 'web', url, summary: resultText };
    }

    default:
      return {
        ...base,
        kind: 'generic',
        input: Object.keys(args).length > 0 ? args : undefined,
        output: result == null ? undefined
          : typeof resultValue === 'string'
            ? { result: resultValue }
            : (resultValue as Record<string, unknown> | undefined),
      };
  }
}

// ── helpers ──────────────────────────────────────────────────────────────────

function stringArg(args: Record<string, unknown>, key: string): string {
  const v = args[key];
  return typeof v === 'string' ? v : '';
}

/** Coerce a value to a string, but return '' for non-string / null /
 *  undefined inputs so callers can use `||` to fall through to a placeholder. */
function stringOrEmpty(v: unknown): string {
  if (typeof v === 'string') return v;
  if (v == null) return '';
  return safeStringify(v);
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Synthesize a friendly command line for tools that don't carry one literally.
 * Bash/run_command emit the command verbatim; Grep/Glob need shaping so the
 * Terminal header reads like a real shell prompt.
 */
function deriveTerminalCommand(toolName: string, args: Record<string, unknown>): string {
  const raw = stringArg(args, 'command');
  if (raw) return raw;

  if (toolName === 'Grep') {
    const pattern = stringArg(args, 'pattern');
    const path = stringArg(args, 'path') || '.';
    const glob = stringArg(args, 'glob');
    const type = stringArg(args, 'type');
    const flags = [
      type && `--type=${type}`,
      glob && `--glob="${glob}"`,
    ].filter(Boolean).join(' ');
    return `rg ${flags ? flags + ' ' : ''}"${pattern}" ${path}`.trim();
  }

  if (toolName === 'Glob') {
    const pattern = stringArg(args, 'pattern');
    const path = stringArg(args, 'path') || '.';
    return `find ${path} -name "${pattern}"`;
  }

  // Last-resort: render the tool name + a compact arg list. Better than a
  // blank header, and the user can still see the args.
  const argSummary = Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : safeStringify(v)}`)
    .join(' ');
  return argSummary ? `${toolName} ${argSummary}` : toolName;
}

const LANG_BY_EXT: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
  py: 'python', go: 'go', rs: 'rust', java: 'java', kt: 'kotlin',
  rb: 'ruby', sh: 'bash', bash: 'bash', zsh: 'bash',
  json: 'json', yaml: 'yaml', yml: 'yaml', toml: 'toml',
  md: 'markdown', html: 'html', css: 'css', scss: 'scss',
  sql: 'sql', c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp',
};

function inferLanguageFromPath(path: string): string | undefined {
  const m = /\.([a-zA-Z0-9]+)$/.exec(path);
  if (!m) return undefined;
  return LANG_BY_EXT[m[1].toLowerCase()];
}
