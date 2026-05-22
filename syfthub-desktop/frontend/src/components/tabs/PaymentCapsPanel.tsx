import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Loader2, RotateCcw, ShieldAlert } from 'lucide-react';
import type { PaymentRecord } from './WalletTab';

// Defaults shown in empty rows. These mirror the Go-side defaultSoftCap /
// defaultHardCap constants in payment_caps.go ("0.10" / "1.00"); we hard-code
// them here as the panel's UI fallback so a not-yet-configured row still
// renders sensible numbers.
const DEFAULT_SOFT_CAP = '0.10';
const DEFAULT_HARD_CAP = '1.00';

// PaymentCap mirrors the Go-side `PaymentCap` struct in payment_caps.go.
// The canonical TS definition lives in wailsjs/go/main/App.d.ts after a
// `wails build` regenerates the bindings; the local copy here lets a plain
// `npm run build` type-check before that happens.
export interface PaymentCap {
  endpoint_slug: string;
  soft_cap: string;
  hard_cap: string;
  currency: string;
  updated_at: number;
}

// PaymentCapsConfig is the full config blob returned by GetPaymentCaps.
export interface PaymentCapsConfig {
  defaults: PaymentCap;
  per_endpoint: Record<string, PaymentCap>;
}

interface PaymentCapsPanelProps {
  // Recent payment records from the wallet ledger — used to seed the row set
  // with endpoints the user has actually paid, even before they have a
  // dedicated per-endpoint override saved.
  recentRecords: PaymentRecord[];
}

// hasWailsMethod feature-detects a Wails-bound method on window.go.main.App.
// Returns true only when the binding actually exists and is callable.
function hasWailsMethod(name: string): boolean {
  const w = window as unknown as {
    go?: { main?: { App?: Record<string, unknown> } };
  };
  const app = w.go?.main?.App;
  return Boolean(app && typeof app[name] === 'function');
}

// callWailsMethod invokes a Wails-bound method by name. Throws synchronously
// when the binding is missing so the caller can degrade explicitly.
async function callWailsMethod<T>(name: string, ...args: unknown[]): Promise<T> {
  const w = window as unknown as {
    go?: { main?: { App?: Record<string, (...a: unknown[]) => Promise<T>> } };
  };
  const fn = w.go?.main?.App?.[name];
  if (typeof fn !== 'function') {
    throw new Error(`Wails method ${name} is not bound`);
  }
  return fn(...args);
}

// Row holds the editable state for a single endpoint cap. Local edits live
// here until Save flushes them through SetPaymentCap, so changing the soft
// input does not trigger a wails round-trip on every keystroke.
interface Row {
  slug: string;
  label?: string;
  soft: string;
  hard: string;
  // saving / error / savedAt mirror the per-row async state used by the
  // table buttons. savedAt drives the transient "Saved" affordance.
  saving?: boolean;
  error?: string;
  savedAt?: number;
}

// slugsFromRecords dedupes the endpoint slugs the user has paid recently.
// We key on "owner/slug" (the Go-side EndpointSlug format) so the row keys
// match what SetPaymentCap stores.
function slugsFromRecords(records: PaymentRecord[]): Map<string, string | undefined> {
  const out = new Map<string, string | undefined>();
  for (const r of records) {
    const slug = composeSlug(r.endpoint_owner, r.endpoint_slug);
    if (!slug) continue;
    if (out.has(slug)) continue;
    out.set(slug, r.endpoint_label);
  }
  return out;
}

// composeSlug rebuilds the "owner/slug" key used by the caps store. Returns
// an empty string when both pieces are missing — caller treats that as "skip".
function composeSlug(owner: string, slug: string): string {
  const o = (owner || '').trim();
  const s = (slug || '').trim();
  if (!o && !s) return '';
  if (!o) return s;
  if (!s) return o;
  return `${o}/${s}`;
}

// buildRows combines (a) the slugs the user has paid, (b) the per-endpoint
// overrides currently persisted on disk, and (c) the global defaults. The
// global defaults are NOT a row — they're applied as the fallback values for
// any row that has no override stored yet.
function buildRows(
  paidSlugs: Map<string, string | undefined>,
  config: PaymentCapsConfig | null
): Row[] {
  const defaults = config?.defaults;
  const soft = defaults?.soft_cap || DEFAULT_SOFT_CAP;
  const hard = defaults?.hard_cap || DEFAULT_HARD_CAP;
  const overrides = config?.per_endpoint || {};

  // Union of paid + overridden slugs so the user sees both "configured but
  // never used" and "used but never configured" endpoints.
  const allSlugs = new Set<string>();
  for (const s of paidSlugs.keys()) allSlugs.add(s);
  for (const s of Object.keys(overrides)) allSlugs.add(s);

  const rows: Row[] = [];
  for (const slug of allSlugs) {
    const override = overrides[slug];
    rows.push({
      slug,
      label: paidSlugs.get(slug),
      soft: override?.soft_cap || soft,
      hard: override?.hard_cap || hard,
    });
  }
  rows.sort((a, b) => a.slug.localeCompare(b.slug));
  return rows;
}

// PaymentCapsPanel exposes the per-endpoint cap surface. When the U11 Wails
// methods are not yet bound (no GetPaymentCaps/SetPaymentCap on App), the
// panel degrades to a placeholder rather than throwing.
export function PaymentCapsPanel({ recentRecords }: PaymentCapsPanelProps) {
  const capsBoundGet = hasWailsMethod('GetPaymentCaps');
  const capsBoundSet = hasWailsMethod('SetPaymentCap');
  const capsBoundReset = hasWailsMethod('ResetPaymentCap');

  const paidSlugs = useMemo(() => slugsFromRecords(recentRecords), [recentRecords]);

  const [config, setConfig] = useState<PaymentCapsConfig | null>(null);
  const [rows, setRows] = useState<Row[]>(() => buildRows(paidSlugs, null));
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Reload the caps config whenever the binding becomes available or the
  // panel mounts. Failures are surfaced inline so the placeholder rows still
  // render the user's recent endpoints.
  useEffect(() => {
    if (!capsBoundGet) {
      setRows(buildRows(paidSlugs, null));
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    callWailsMethod<PaymentCapsConfig>('GetPaymentCaps')
      .then((cfg) => {
        if (cancelled) return;
        setConfig(cfg);
        setRows(buildRows(paidSlugs, cfg));
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof Error ? err.message : 'Failed to load caps'
        );
        setRows(buildRows(paidSlugs, null));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // paidSlugs is intentionally listed so a new payment immediately appends
    // a fresh row; we still rebuild from the latest cached config so any
    // in-flight edits are not blown away.
  }, [capsBoundGet, paidSlugs]);

  const updateRow = (slug: string, patch: Partial<Row>) => {
    setRows((prev) =>
      prev.map((r) => (r.slug === slug ? { ...r, ...patch } : r))
    );
  };

  const onSave = async (row: Row) => {
    if (!capsBoundSet) {
      updateRow(row.slug, { error: 'Caps not yet enabled' });
      return;
    }
    const softNum = Number.parseFloat(row.soft);
    const hardNum = Number.parseFloat(row.hard);
    if (!Number.isFinite(softNum) || softNum < 0) {
      updateRow(row.slug, { error: 'Invalid soft cap' });
      return;
    }
    if (!Number.isFinite(hardNum) || hardNum < 0) {
      updateRow(row.slug, { error: 'Invalid hard cap' });
      return;
    }
    if (softNum > hardNum) {
      updateRow(row.slug, { error: 'Soft cap must be ≤ hard cap' });
      return;
    }
    updateRow(row.slug, { saving: true, error: undefined });
    // Currency defaults to the global config's currency; the Go side will
    // also fall back via effectiveCap so this is belt-and-suspenders.
    const currency = config?.defaults?.currency || '';
    try {
      await callWailsMethod('SetPaymentCap', {
        endpoint_slug: row.slug,
        soft_cap: row.soft,
        hard_cap: row.hard,
        currency,
        updated_at: 0,
      } as PaymentCap);
      updateRow(row.slug, { saving: false, savedAt: Date.now() });
      // Refresh the cached config so future reloads see the new override.
      try {
        const cfg = await callWailsMethod<PaymentCapsConfig>('GetPaymentCaps');
        setConfig(cfg);
      } catch {
        // Non-fatal — the user's edit landed; the cached config will
        // refresh on next panel open.
      }
    } catch (err) {
      updateRow(row.slug, {
        saving: false,
        error: err instanceof Error ? err.message : 'Failed to save',
      });
    }
  };

  const onReset = async (row: Row) => {
    // Server-side reset clears the per-endpoint override and falls back to
    // defaults. When the binding isn't there, just clear the local edits.
    if (capsBoundReset) {
      updateRow(row.slug, { saving: true, error: undefined });
      try {
        await callWailsMethod('ResetPaymentCap', row.slug);
        const cfg = capsBoundGet
          ? await callWailsMethod<PaymentCapsConfig>('GetPaymentCaps')
          : null;
        if (cfg) setConfig(cfg);
        const defaults = cfg?.defaults;
        updateRow(row.slug, {
          saving: false,
          soft: defaults?.soft_cap || DEFAULT_SOFT_CAP,
          hard: defaults?.hard_cap || DEFAULT_HARD_CAP,
          savedAt: Date.now(),
        });
      } catch (err) {
        updateRow(row.slug, {
          saving: false,
          error: err instanceof Error ? err.message : 'Failed to reset',
        });
      }
      return;
    }
    updateRow(row.slug, {
      soft: config?.defaults?.soft_cap || DEFAULT_SOFT_CAP,
      hard: config?.defaults?.hard_cap || DEFAULT_HARD_CAP,
      error: undefined,
    });
  };

  // Empty-state when the backend isn't wired AND the user has no payments
  // yet to derive rows from — there's nothing to render but a hint.
  if (!capsBoundSet && rows.length === 0) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-border bg-card/40 p-4 text-sm text-muted-foreground">
        <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-chart-3" />
        <div>
          <p className="font-medium text-foreground">Caps not yet enabled</p>
          <p className="mt-1">
            Per-endpoint payment caps will appear here once you have made at
            least one payment and the caps backend is wired up.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {!capsBoundSet && (
        <div className="flex items-start gap-3 rounded-lg border border-chart-3/30 bg-chart-3/10 p-3 text-xs text-foreground">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-chart-3" />
          <p>
            Saving caps is not yet enabled. Edits below are preview only and
            will be discarded.
          </p>
        </div>
      )}
      {loadError && (
        <p className="text-xs text-destructive">{loadError}</p>
      )}
      {loading && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading caps…
        </div>
      )}
      {config && (
        <p className="text-xs text-muted-foreground">
          Defaults: {config.defaults.soft_cap} soft / {config.defaults.hard_cap}{' '}
          hard
        </p>
      )}
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No endpoints with recorded payments yet.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Endpoint</th>
                <th className="px-3 py-2 text-left font-medium">Soft cap ($)</th>
                <th className="px-3 py-2 text-left font-medium">Hard cap ($)</th>
                <th className="px-3 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.slug} className="border-t border-border">
                  <td className="px-3 py-2">
                    <div className="font-medium text-foreground">
                      {row.label || row.slug}
                    </div>
                    {row.label && row.label !== row.slug && (
                      <div className="text-xs text-muted-foreground">
                        {row.slug}
                      </div>
                    )}
                    {row.error && (
                      <div className="mt-1 text-xs text-destructive">
                        {row.error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <Input
                      type="text"
                      inputMode="decimal"
                      value={row.soft}
                      onChange={(e) =>
                        updateRow(row.slug, {
                          soft: e.target.value,
                          error: undefined,
                        })
                      }
                      className="h-8 w-24"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <Input
                      type="text"
                      inputMode="decimal"
                      value={row.hard}
                      onChange={(e) =>
                        updateRow(row.slug, {
                          hard: e.target.value,
                          error: undefined,
                        })
                      }
                      className="h-8 w-24"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onReset(row)}
                        disabled={row.saving}
                        title="Reset to defaults"
                      >
                        <RotateCcw className="h-3 w-3" />
                        Reset
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={row.saving}
                        onClick={() => onSave(row)}
                      >
                        {row.saving ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : null}
                        Save
                      </Button>
                    </div>
                    {row.savedAt && !row.saving && !row.error && (
                      <div className="mt-1 text-right text-[10px] text-chart-2">
                        Saved
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
