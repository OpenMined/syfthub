import { useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, Shield, ShieldCheck, X } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import {
  ClearEndpointEgressKey,
  GetEndpointEgressKeyStatus,
  GetEndpointSandbox,
  ListMCPServers,
  SetEndpointEgressKey,
  SetEndpointSandbox,
} from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';
import { useAppStore } from '../../stores/appStore';

// Draft is the editable shape; arrays are always defined (Go nil → JSON null).
type Draft = {
  exposeEnv: string[];
  exposeResources: string[];
  exposeMcp: string[];
  workspaceScope: string;
  workspacePath: string;
  cpuCores: number;
  memoryMb: number;
  timeoutSeconds: number;
  tmpfsMb: number;
};

function normalize(r: main.SandboxSettings): Draft {
  return {
    exposeEnv: r.exposeEnv ?? [],
    exposeResources: r.exposeResources ?? [],
    exposeMcp: r.exposeMcp ?? [],
    workspaceScope: r.workspaceScope || '',
    workspacePath: r.workspacePath || '',
    cpuCores: r.cpuCores || 0,
    memoryMb: r.memoryMb || 0,
    timeoutSeconds: r.timeoutSeconds || 0,
    tmpfsMb: r.tmpfsMb || 0,
  };
}

// Derived from normalize so the field defaults live in exactly one place.
const EMPTY: Draft = normalize(main.SandboxSettings.createFrom({}));

/**
 * SandboxModal edits an endpoint's `sandbox:` frontmatter as a single
 * transactional form (draft → Save), organized into three tabs by question:
 * what the endpoint can reach (Access), what it can see and write
 * (Environment), and how much it can consume (Limits — persisted but not yet
 * enforced, clearly badged). Only meaningful in container mode.
 */
export function SandboxModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const slug = useAppStore((s) => s.selectedEndpointSlug);
  const containerEnabled = useAppStore((s) => s.config?.containerEnabled ?? false);

  const [s, setS] = useState<Draft>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('access');

  // Host-side egress key (OpenAI-compatible agents). `keySet` reflects whether a
  // key is stored on the host; `keyInput` is a pending new value to save. The
  // stored key is never read back into the UI.
  const [keySet, setKeySet] = useState(false);
  const [keyInput, setKeyInput] = useState('');

  // Host MCP servers available to expose. Names/status only — never secrets.
  const [mcpServers, setMcpServers] = useState<main.MCPServerInfo[]>([]);

  useEffect(() => {
    if (!open || !slug) return;
    setError('');
    setTab('access');
    setKeyInput('');
    setLoading(true);
    Promise.all([GetEndpointSandbox(slug), GetEndpointEgressKeyStatus(slug), ListMCPServers()])
      .then(([sandbox, hasKey, servers]) => {
        setS(normalize(sandbox));
        setKeySet(hasKey);
        setMcpServers(servers || []);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [open, slug]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setS((p) => ({ ...p, [k]: v }));
  const toggleMcp = (name: string) =>
    set('exposeMcp', s.exposeMcp.includes(name) ? s.exposeMcp.filter((n) => n !== name) : [...s.exposeMcp, name]);

  // Union of registry servers and any already-selected names (so a selection
  // whose server was removed/disabled is still visible and unselectable).
  const mcpRows = Array.from(new Set([...mcpServers.map((m) => m.name), ...s.exposeMcp])).sort();

  const handleSave = async () => {
    if (!slug) return;
    setSaving(true);
    setError('');
    try {
      // Persist a newly-entered egress key first (blank input leaves the
      // stored key untouched; clearing is an explicit action below). The key
      // write does not reload by itself — the sandbox save below triggers the
      // single endpoint reload that picks both changes up.
      if (keyInput.trim()) {
        await SetEndpointEgressKey(slug, keyInput.trim());
      }
      await SetEndpointSandbox(slug, main.SandboxSettings.createFrom({ ...s }));
      onOpenChange(false);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const clearKey = async () => {
    if (!slug) return;
    try {
      await ClearEndpointEgressKey(slug);
      setKeySet(false);
      setKeyInput('');
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
        <DialogHeader className="px-6 pt-6">
          <DialogTitle className="flex items-center gap-2">
            <Shield className="w-4 h-4" /> Sandbox
          </DialogTitle>
          <DialogDescription>
            How this endpoint's code is isolated when it runs in a container.
          </DialogDescription>
        </DialogHeader>

        {!containerEnabled && (
          <div className="mx-6 mt-3 flex items-start gap-1.5 rounded-md bg-chart-3/10 px-3 py-2 text-xs text-chart-3">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>These settings apply only in container mode. Enable it in Settings for them to take effect.</span>
          </div>
        )}

        {loading ? (
          <div className="flex h-[348px] items-center justify-center">
            <Spinner className="w-5 h-5" />
          </div>
        ) : (
          <Tabs value={tab} onValueChange={setTab} className="min-h-0 px-6 pt-4">
            <TabsList className="w-full">
              <TabsTrigger value="access" className="flex-1">Access</TabsTrigger>
              <TabsTrigger value="environment" className="flex-1">Environment</TabsTrigger>
              <TabsTrigger value="limits" className="flex-1">Limits</TabsTrigger>
            </TabsList>

            <div className="h-[300px] overflow-y-auto py-4">
              <TabsContent value="access" className="space-y-5">
                <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <ShieldCheck className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-primary" />
                  No direct internet — the model API and tool calls are brokered by the host, so
                  credentials never enter the container.
                </p>

                <Field
                  label="Model API key"
                  hint="OpenAI-compatible agents only; stored on the host. Claude agents use your host login — leave blank."
                >
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={keySet ? '•••••••• (set — leave blank to keep)' : 'sk-…'}
                      className="h-8 flex-1 font-mono text-xs"
                    />
                    {keySet && (
                      <button
                        type="button"
                        onClick={clearKey}
                        className="px-2 py-1 rounded text-xs text-muted-foreground hover:text-destructive hover:bg-secondary/60"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </Field>

                <Field label="MCP tools" hint="Host tool servers this endpoint may call.">
                  {mcpRows.length === 0 ? (
                    <p className="text-xs text-muted-foreground/70">
                      No MCP servers configured. Add them in Settings → MCP Servers, then enable the
                      ones this endpoint should use.
                    </p>
                  ) : (
                    <div className="space-y-1.5">
                      {mcpRows.map((name) => {
                        const info = mcpServers.find((m) => m.name === name);
                        const known = !!info;
                        const enabled = info?.enabled ?? false;
                        const checked = s.exposeMcp.includes(name);
                        // A selectable row requires the server to exist and be enabled
                        // host-side; otherwise it's shown for context but locked.
                        const locked = !known || !enabled;
                        return (
                          <label
                            key={name}
                            className={`flex items-center gap-2 text-sm ${locked && !checked ? 'opacity-50' : ''}`}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={locked}
                              onChange={() => toggleMcp(name)}
                              className="h-3.5 w-3.5 accent-primary"
                            />
                            <span className="font-mono text-foreground">{name}</span>
                            {known && (
                              <span className="rounded bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                                {info!.transport}
                              </span>
                            )}
                            {!known ? (
                              <span className="text-xs text-destructive/80">not configured</span>
                            ) : !enabled ? (
                              <span className="text-xs text-muted-foreground/70">disabled — enable in Settings</span>
                            ) : info!.authMode === 'oauth' && info!.authStatus !== 'connected' ? (
                              <span className="text-xs text-chart-3">
                                {info!.authStatus === 'expired' ? 'reconnect in Settings' : 'not connected — Connect in Settings'}
                              </span>
                            ) : null}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </Field>
              </TabsContent>

              <TabsContent value="environment" className="space-y-5">
                <Field label="Environment variables" hint="Which .env vars the handler sees. Empty = all.">
                  <TagInput value={s.exposeEnv} onChange={(v) => set('exposeEnv', v)} placeholder="API_KEY" />
                </Field>

                <Field
                  label="Read-only resources"
                  hint="Extra non-code files from the endpoint folder, mounted read-only (relative paths)."
                >
                  <TagInput
                    value={s.exposeResources}
                    onChange={(v) => set('exposeResources', v)}
                    placeholder="prompts/"
                  />
                </Field>

                <Field label="Workspace" hint="Writable scratch space for the handler.">
                  <Segmented
                    value={s.workspaceScope || 'per_session'}
                    onChange={(v) => set('workspaceScope', v)}
                    options={[
                      { value: 'per_session', label: 'Per session' },
                      { value: 'per_user', label: 'Per user' },
                      { value: 'shared', label: 'Shared' },
                    ]}
                  />
                </Field>
              </TabsContent>

              <TabsContent value="limits" className="space-y-4">
                <div className="flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2">
                  <span className="mt-0.5 flex-shrink-0 rounded bg-secondary px-1.5 py-0.5 text-[10px] text-secondary-foreground">
                    not enforced yet
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Saved to the endpoint config, but the runner doesn't apply them yet — global
                    container limits apply instead.
                  </p>
                </div>

                <Field label="Workspace folder" hint='Default: "workspace".'>
                  <Input
                    value={s.workspacePath}
                    onChange={(e) => set('workspacePath', e.target.value)}
                    placeholder="workspace"
                    className="h-8 font-mono text-xs"
                  />
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="CPU cores">
                    <NumInput value={s.cpuCores} onChange={(v) => set('cpuCores', v)} step={0.5} />
                  </Field>
                  <Field label="Memory (MB)">
                    <NumInput value={s.memoryMb} onChange={(v) => set('memoryMb', v)} />
                  </Field>
                  <Field label="Timeout (s)">
                    <NumInput value={s.timeoutSeconds} onChange={(v) => set('timeoutSeconds', v)} />
                  </Field>
                  <Field label="tmpfs (MB)">
                    <NumInput value={s.tmpfsMb} onChange={(v) => set('tmpfsMb', v)} />
                  </Field>
                </div>
              </TabsContent>
            </div>
          </Tabs>
        )}

        {error && <p className="px-6 pb-2 text-xs text-destructive break-words">{error}</p>}

        <DialogFooter className="border-t border-border/60 px-6 py-3.5">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || loading}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── small local primitives ──────────────────────────────────────────────────

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div>
        <label className="text-sm text-foreground">{label}</label>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string; disabled?: boolean }[];
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-md border border-input bg-background p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
            value === o.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
          } ${o.disabled ? 'cursor-not-allowed opacity-40' : ''}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const t = draft.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft('');
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-1 focus-within:ring-ring/50">
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-secondary-foreground"
        >
          {tag}
          <button
            type="button"
            aria-label={`Remove ${tag}`}
            onClick={() => onChange(value.filter((x) => x !== tag))}
            className="text-muted-foreground hover:text-destructive"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add();
          } else if (e.key === 'Backspace' && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={add}
        placeholder={value.length ? '' : placeholder}
        className="min-w-[80px] flex-1 bg-transparent font-mono text-sm text-foreground placeholder:text-muted-foreground outline-none"
      />
    </div>
  );
}

function NumInput({
  value,
  onChange,
  step,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <Input
      type="number"
      min={0}
      step={step ?? 1}
      value={value || ''}
      onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
      className="h-8 text-xs"
    />
  );
}
