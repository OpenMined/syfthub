import { AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react';
import { useAppStore, type LoadPhase, type LoadProgressEntry } from '@/stores/appStore';

const PHASE_LABELS: Record<LoadPhase, string> = {
  pending: 'Queued',
  resolving_image: 'Resolving image…',
  pulling_image: 'Pulling image (this may take a while)…',
  building_image: 'Building image (this may take a few minutes)…',
  verifying_image: 'Verifying sandbox…',
  materializing: 'Preparing sandbox…',
  starting_container: 'Starting container…',
  ready: 'Ready',
  failed: 'Failed',
};

function isActive(phase: LoadPhase): boolean {
  return phase !== 'ready' && phase !== 'failed';
}

function PhaseIcon({ phase }: { phase: LoadPhase }) {
  if (phase === 'ready') {
    return <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" aria-label="Ready" />;
  }
  if (phase === 'failed') {
    return <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0" aria-label="Failed" />;
  }
  return <Loader2 className="w-4 h-4 text-primary animate-spin flex-shrink-0" aria-label="In progress" />;
}

function ProgressRow({ entry }: { entry: LoadProgressEntry }) {
  const label = PHASE_LABELS[entry.phase] ?? entry.phase;
  return (
    <li className="flex items-start gap-3 py-2">
      <PhaseIcon phase={entry.phase} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground truncate">
          {entry.name || entry.slug}
        </div>
        <div className="text-xs text-muted-foreground truncate">
          {entry.phase === 'failed' && entry.error ? entry.error : label}
        </div>
      </div>
    </li>
  );
}

/**
 * LoadProgress is the overlay shown while the SDK is loading endpoints —
 * primarily on startup when container endpoints are being built or pulled
 * (operations that can take several minutes). The overlay auto-dismisses
 * when every endpoint reaches the 'ready' phase; it stays up after
 * failures so the user can read the error and dismiss manually.
 */
export function LoadProgress() {
  const progress = useAppStore((s) => s.loadProgress);
  const dismiss = useAppStore((s) => s.dismissLoadProgress);

  const entries = Object.values(progress.entries);
  if (entries.length === 0) return null;

  const total = progress.total || entries.length;
  const readyCount = entries.filter((e) => e.phase === 'ready').length;
  const failedCount = entries.filter((e) => e.phase === 'failed').length;
  const activeCount = entries.filter((e) => isActive(e.phase)).length;
  const anyFailed = failedCount > 0;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background/95 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="load-progress-title"
    >
      <div className="max-w-md w-full mx-4 bg-card border border-border/60 rounded-lg shadow-2xl">
        <div className="p-6 pb-3">
          <div className="flex items-start gap-3">
            {activeCount > 0 ? (
              <Loader2 className="w-6 h-6 text-primary animate-spin flex-shrink-0 mt-0.5" />
            ) : anyFailed ? (
              <AlertCircle className="w-6 h-6 text-destructive flex-shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 className="w-6 h-6 text-green-500 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <h2 id="load-progress-title" className="text-lg font-semibold text-foreground">
                {activeCount > 0 ? 'Starting endpoints…' : anyFailed ? 'Endpoints loaded with errors' : 'Endpoints loaded'}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {readyCount} of {total} ready
                {failedCount > 0 ? `, ${failedCount} failed` : ''}
                {activeCount > 0 && ' — first run can take a few minutes while container images build.'}
              </p>
            </div>
            {activeCount === 0 && (
              <button
                onClick={dismiss}
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Dismiss"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        </div>
        <ul className="px-6 pb-4 max-h-80 overflow-y-auto divide-y divide-border/40">
          {entries.map((e) => (
            <ProgressRow key={e.slug} entry={e} />
          ))}
        </ul>
      </div>
    </div>
  );
}
